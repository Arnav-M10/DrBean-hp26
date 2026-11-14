"""Extract the model's tool calls from a research session's latest checkpoint.

Read-only, isolated temporary store only. Prints each model turn's tool calls
(name and arguments) and each tool result's name and leading characters, so a
live run's actual decisions survive the store's deletion. Inputs in this
sprint are public synthetic data; no credential is stored in checkpoints.

    python evaluation/live/extract_tool_calls.py <db> <session_id>
"""
from __future__ import annotations

import json
import sys

from langchain_core.messages import AIMessage, ToolMessage

from bean_api.research_checkpoints import ResearchJSON
from bean_api.store import Store


def main(db: str, session_id: str) -> int:
    store = Store(db)
    with store.read() as conn:
        row = conn.execute("SELECT b.checkpoint FROM research_checkpoint_blobs b JOIN research_sessions s ON s.thread_id=b.thread_id "
                           "WHERE s.id=? AND b.namespace='' ORDER BY b.checkpoint_id DESC LIMIT 1", (session_id,)).fetchone()
    if row is None:
        print(json.dumps({"turns": [], "note": "no checkpoint"}))
        return 0
    messages = ResearchJSON().loads(row[0])["channel_values"].get("messages", [])
    turns = []
    for message in messages:
        if isinstance(message, AIMessage):
            turns.append({"role": "model", "tool_calls": [{"name": call["name"], "args": call["args"]} for call in message.tool_calls],
                          "text": (message.content if isinstance(message.content, str) else json.dumps(message.content))[:2000]})
        elif isinstance(message, ToolMessage):
            content = message.content if isinstance(message.content, str) else json.dumps(message.content)
            turns.append({"role": "tool", "name": message.name, "status": getattr(message, "status", None), "content_head": content[:600]})
    print(json.dumps({"turns": turns}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:]))
