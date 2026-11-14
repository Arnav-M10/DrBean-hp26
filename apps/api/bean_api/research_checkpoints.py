"""Bounded, non-executable JSON checkpoint storage in the application database.

Only explicitly named SDK value types are reconstructed. There is no pickle,
module import from stored data, browser-selected thread or filesystem backend.
Every history read and write revalidates the private worker's lease/fence.
"""
from __future__ import annotations

import base64
import json
import math

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.base import BaseCheckpointSaver, CheckpointTuple, WRITES_IDX_MAP
from langgraph.types import Interrupt, Send

CODEC_VERSION = "research-json.v1"
MAX_BYTES = 1024 * 1024
MESSAGES = {cls.__name__: cls for cls in (AIMessage, HumanMessage, SystemMessage, ToolMessage)}


class ResearchJSON:
    def dumps(self, value):
        remaining = [100_000]
        def encode(item, depth=0):
            remaining[0] -= 1
            if depth > 64 or remaining[0] < 0:
                raise ValueError("Checkpoint nesting or item limit exceeded")
            if item is None or type(item) in (str, bool, int):
                return item
            if type(item) is float:
                if not math.isfinite(item):
                    raise ValueError("Non-finite checkpoint value")
                return item
            if type(item) is dict:
                if not all(type(key) is str for key in item):
                    raise ValueError("Checkpoint dictionaries require string keys")
                return ["dict", [[key, encode(v, depth+1)] for key, v in item.items()]]
            if type(item) in (list, tuple, set, frozenset):
                return [type(item).__name__, [encode(v, depth+1) for v in item]]
            if type(item) in MESSAGES.values():
                return ["message", type(item).__name__, encode(item.model_dump(mode="python"), depth+1)]
            if type(item) is Interrupt:
                return ["interrupt", encode(item.value, depth+1), item.id]
            if type(item) is Send:
                return ["send", item.node, encode(item.arg, depth+1)]
            if type(item) is bytes and len(item) <= 64 * 1024:
                return ["bytes", base64.b64encode(item).decode("ascii")]
            raise ValueError("Unsupported checkpoint value type: " + type(item).__name__)
        raw = json.dumps(encode(value), ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
        if len(raw) > MAX_BYTES:
            raise ValueError("Checkpoint exceeds its one MiB bound")
        return raw

    def loads(self, raw):
        if len(raw) > MAX_BYTES:
            raise ValueError("Checkpoint exceeds its one MiB bound")
        remaining = [100_000]
        def decode(item, depth=0):
            remaining[0] -= 1
            if depth > 64 or remaining[0] < 0:
                raise ValueError("Checkpoint nesting or item limit exceeded")
            if item is None or type(item) in (str, bool, int):
                return item
            if type(item) is float and math.isfinite(item):
                return item
            if type(item) is not list or len(item) < 2:
                raise ValueError("Invalid checkpoint encoding")
            tag = item[0]
            if tag == "dict" and len(item) == 2:
                result = {}
                for key, value in item[1]:
                    if type(key) is not str or key in result:
                        raise ValueError("Invalid checkpoint dictionary")
                    result[key] = decode(value, depth+1)
                return result
            if tag in {"list", "tuple", "set", "frozenset"} and len(item) == 2:
                return {"list": list, "tuple": tuple, "set": set, "frozenset": frozenset}[tag](decode(v, depth+1) for v in item[1])
            if tag == "message" and len(item) == 3 and item[1] in MESSAGES:
                return MESSAGES[item[1]](**decode(item[2], depth+1))
            if tag == "interrupt" and len(item) == 3 and type(item[2]) is str:
                return Interrupt(value=decode(item[1], depth+1), id=item[2])
            if tag == "send" and len(item) == 3 and type(item[1]) is str:
                return Send(item[1], decode(item[2], depth+1))
            if tag == "bytes" and len(item) == 2:
                content = base64.b64decode(item[1], validate=True)
                if len(content) <= 64 * 1024:
                    return content
            raise ValueError("Unknown checkpoint encoding tag")
        return decode(json.loads(raw))


class ResearchCheckpointer(BaseCheckpointSaver):
    def __init__(self, service, context):
        super().__init__()
        self.service, self.context, self.codec = service, context, ResearchJSON()

    def _identity(self, config):
        values = config.get("configurable", {})
        if values.get("thread_id") != self.context.thread_id:
            raise ValueError("Checkpoint thread does not belong to this private runtime")
        namespace = values.get("checkpoint_ns", "")
        if type(namespace) is not str or len(namespace) > 256:
            raise ValueError("Invalid checkpoint namespace")
        checkpoint_id = values.get("checkpoint_id")
        if checkpoint_id is not None and (type(checkpoint_id) is not str or len(checkpoint_id) > 128):
            raise ValueError("Invalid checkpoint ID")
        return self.context.thread_id, namespace, checkpoint_id

    def _config(self, namespace, checkpoint_id):
        return {"configurable": {"thread_id": self.context.thread_id, "checkpoint_ns": namespace, "checkpoint_id": checkpoint_id}}

    def _tuple(self, conn, row):
        if row["codec_version"] != CODEC_VERSION:
            raise ValueError("Incompatible checkpoint codec")
        writes = [(w["task_id"], w["channel"], self.codec.loads(w["value"])) for w in conn.execute(
            "SELECT * FROM research_checkpoint_writes WHERE thread_id=? AND namespace=? AND checkpoint_id=? ORDER BY task_id,write_index",
            (self.context.thread_id, row["namespace"], row["checkpoint_id"]))]
        return CheckpointTuple(self._config(row["namespace"], row["checkpoint_id"]),
            self.codec.loads(row["checkpoint"]), self.codec.loads(row["metadata"]),
            self._config(row["namespace"], row["parent_id"]) if row["parent_id"] else None, writes)

    def get_tuple(self, config):
        thread, namespace, checkpoint_id = self._identity(config)
        with self.service.store.read() as conn:
            self.service.assert_lease(conn, self.context)
            row = conn.execute("SELECT * FROM research_checkpoint_blobs WHERE thread_id=? AND namespace=? " +
                ("AND checkpoint_id=?" if checkpoint_id else "ORDER BY checkpoint_id DESC LIMIT 1"),
                (thread, namespace, checkpoint_id) if checkpoint_id else (thread, namespace)).fetchone()
            return self._tuple(conn, row) if row else None

    def put(self, config, checkpoint, metadata, new_versions):
        thread, namespace, parent_id = self._identity(config)
        raw, metadata_raw = self.codec.dumps(checkpoint), self.codec.dumps(metadata)
        if len(raw) + len(metadata_raw) > MAX_BYTES:
            raise ValueError("Checkpoint and metadata exceed their combined bound")
        with self.service.store.transaction() as conn:
            self.service.assert_lease(conn, self.context)
            conn.execute("INSERT INTO research_checkpoint_blobs VALUES (?,?,?,?,?,?,?) ON CONFLICT(thread_id,namespace,checkpoint_id) DO NOTHING",
                (thread, namespace, checkpoint["id"], parent_id, CODEC_VERSION, raw, metadata_raw))
        return self._config(namespace, checkpoint["id"])

    def put_writes(self, config, writes, task_id, task_path=""):
        thread, namespace, checkpoint_id = self._identity(config)
        encoded = [(channel, self.codec.dumps(value)) for channel, value in writes]
        if len(encoded) > 128 or sum(len(raw) for _, raw in encoded) > MAX_BYTES:
            raise ValueError("Checkpoint writes exceed their combined bound")
        with self.service.store.transaction() as conn:
            self.service.assert_lease(conn, self.context)
            for index, (channel, raw) in enumerate(encoded):
                write_index = WRITES_IDX_MAP.get(channel, index)
                query = "INSERT OR REPLACE" if write_index < 0 else "INSERT OR IGNORE"
                conn.execute(query + " INTO research_checkpoint_writes VALUES (?,?,?,?,?,?,?)",
                    (thread, namespace, checkpoint_id, task_id, write_index, channel, raw))

    def list(self, config, *, filter=None, before=None, limit=None):
        if config is None:
            raise ValueError("Private runtime config is required")
        thread, namespace, _ = self._identity(config)
        before_id = self._identity(before)[2] if before else None
        with self.service.store.read() as conn:
            self.service.assert_lease(conn, self.context)
            rows = list(conn.execute("SELECT * FROM research_checkpoint_blobs WHERE thread_id=? AND namespace=? ORDER BY checkpoint_id DESC LIMIT ?",
                (thread, namespace, min(max(limit or 100, 1), 100))))
            values = [self._tuple(conn, row) for row in rows if not before_id or row["checkpoint_id"] < before_id]
        yield from (value for value in values if all(value.metadata.get(k) == v for k, v in (filter or {}).items()))

    async def aget_tuple(self, config):
        return self.get_tuple(config)

    async def aput(self, config, checkpoint, metadata, new_versions):
        return self.put(config, checkpoint, metadata, new_versions)

    async def aput_writes(self, config, writes, task_id, task_path=""):
        self.put_writes(config, writes, task_id, task_path)

    async def alist(self, config, *, filter=None, before=None, limit=None):
        for value in self.list(config, filter=filter, before=before, limit=limit):
            yield value
