#!/usr/bin/env python3
"""Explicit browser-test fixture: controlled intake proposal, zero provider dispatch.

Runs only as a test subprocess against its isolated store. It is not an API route
or a scientific result fixture. The browser uses ordinary review/materialization.
"""
import asyncio
import json
from pathlib import Path
import sys

from bean_api.config import Settings
from bean_api.intake import IntakeService, SourceService
from bean_api.store import Store
from bean_api.workflow import Workflow

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))
from test_intake import FakeProvider, request  # noqa: E402


def main():
    actor, workspace, source_id = sys.argv[1:]
    settings = Settings.from_env()
    workflow = Workflow(Store(settings.database_path))
    sources = SourceService(workflow, settings.blob_dir)
    source = workflow.get(actor, source_id, "source_asset")
    provider = FakeProvider(source)
    proposal = asyncio.run(IntakeService(workflow, sources, provider).create(
        actor, workspace, request(source), "browser-controlled-source-proposal"))
    print(json.dumps({"id": proposal["id"], "mode": "controlled_test_double", "provider_calls": 0}))


if __name__ == "__main__":
    main()
