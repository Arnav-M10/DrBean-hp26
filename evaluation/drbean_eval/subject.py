"""Subjects: how the harness reaches the product under test.

The harness never implements the product. A subject either relays normalized
observations that the owning component emitted through its own controlled
test boundary (RecordedSubject), or talks to the published API (HttpSubject).
With nothing configured, every scheduled entry is recorded as unrun.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from . import API_PREFIX


class SubjectUnavailable(Exception):
    """The entry could not be attempted; recorded as unrun with this reason."""


class SubjectRefused(Exception):
    """The provider or product refused; recorded as refused."""


class SubjectTimeout(Exception):
    """The wall bound elapsed; recorded as timed_out (usage may be unknown)."""


class NoSubject:
    name = "none"

    def describe(self) -> dict:
        return {"subject": "none", "reason": "no product under test was configured"}

    def run_entry(self, entry: dict, variant: dict, lane: str) -> dict:
        raise SubjectUnavailable("no subject configured: the backend, Gemini layer and scientific adapter "
                                 "are not present in the tested checkout")


class RecordedSubject:
    """Reads `<dir>/<entry_id>.observation.json` emitted by the owning component.

    The file must attest the lane, tested commit and case digest it was
    produced for. The runner rejects relabelled or stale observations.
    """
    name = "recorded"

    def __init__(self, directory: str):
        self.directory = directory

    def describe(self) -> dict:
        path = os.path.join(self.directory, "subject.json")
        info = {"subject": "recorded", "directory": self.directory}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                info["declared"] = json.load(handle)
        return info

    def run_entry(self, entry: dict, variant: dict, lane: str) -> dict:
        path = os.path.join(self.directory, f"{entry['entry_id']}.observation.json")
        if not os.path.exists(path):
            raise SubjectUnavailable(f"no recorded observation at {path}")
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)


class HttpSubject:
    """Talks to the published `/api/bean/v1` API.

    Only `GET /capabilities` is exercised today: it is the one route whose
    behaviour the shared contract fixes without a frozen body schema. Case
    execution stays unavailable until Owner 02 publishes the request and
    response schemas; the harness does not invent bodies for another owner.
    """
    name = "http"

    def __init__(self, base_url: str, timeout: float = 5.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def capabilities(self) -> dict:
        request = urllib.request.Request(self.base_url + API_PREFIX + "/capabilities", method="GET")
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return {"status": response.status, "body": json.loads(response.read().decode("utf-8"))}

    def describe(self) -> dict:
        info = {"subject": "http", "base_url": self.base_url}
        try:
            info["capabilities"] = self.capabilities()
        except (urllib.error.URLError, OSError, ValueError) as error:
            info["capabilities_error"] = f"{type(error).__name__}: {error}"
        return info

    def run_entry(self, entry: dict, variant: dict, lane: str) -> dict:
        raise SubjectUnavailable("DB-SC-1 request/response schemas for the case routes are not frozen; "
                                 "see docs/issue-ledger.md I-002")


def make_subject(spec: str):
    if spec in ("", "none"):
        return NoSubject()
    kind, _, rest = spec.partition(":")
    if kind == "recorded" and rest:
        return RecordedSubject(rest)
    if kind == "http" and rest:
        return HttpSubject(rest)
    raise ValueError(f"unknown subject spec {spec!r}; use none, recorded:<dir> or http:<base-url>")
