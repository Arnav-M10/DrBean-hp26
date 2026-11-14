"""Real worker/process/framework integration using synthetic controlled inputs.

No test calls Gemini or claims a Groundwork proposition. The controlled chat model
runs through the actual deepagents graph and the same durable application ledger.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import os
from pathlib import Path
import time

import pytest

from bean_api.coordinator import run_coordinator as real_coordinator
from bean_api.ledger import ProviderLedger
from bean_api.providers import ProviderConfig
from bean_api.science import UnavailableAdapter
from bean_api.store import Store
from bean_api.worker import Worker
from bean_api.workflow import Workflow
from test_coordinator import EvidenceModel
from test_workflow import completed_pair, design_body, prepared


@pytest.fixture
def flow(tmp_path):
    workflow = Workflow(Store(tmp_path / 'worker.sqlite3'))
    workspace = workflow.create_workspace('alice', 'Synthetic worker integration')
    return workflow, workspace['id']


def queued_design(flow):
    workflow, _ = flow
    _, problem, _, _, historical = completed_pair(flow)
    plan = workflow.create_design_plan('alice', historical['id'], design_body(historical, problem), 'design')
    approval = workflow.approve_design_plan('alice', plan['id'], problem['id'], plan['digest'], 'approve-design')
    job = workflow.start_design_job('alice', plan['id'], approval['id'], 'start-design')
    return plan, approval, job


@dataclass
class UnqualifiedClaimAdapter(UnavailableAdapter):
    """A schema-valid claim still cannot cross an unqualified adapter boundary."""

    def investigate(self, problem, dataset, limits):
        artifact = {'id': 'synthetic-artifact', 'sha256': 'a' * 64, 'byte_size': 1, 'media_type': 'application/json'}
        verification = {'checker_name': 'synthetic-checker', 'checker_version': 'fixture',
                        'artifact_id': artifact['id'], 'artifact_sha256': artifact['sha256'],
                        'proposition': 'Synthetic authority control only', 'verification': 'valid',
                        'expected_binding': 'matches', 'expected_problem_digest': problem['digest'],
                        'observed_problem_digest': problem['digest']}
        return {'scientific_outcome': 'inconclusive', 'verification': 'valid',
                'expected_binding': 'matches', 'replay': 'not_run', 'reason_code': 'synthetic_forged_claim',
                'problem_id': problem['id'], 'problem_digest': problem['digest'],
                'artifacts': [artifact], 'candidates': [], 'verification_record': verification}


@dataclass
class SlowDesignAdapter(UnavailableAdapter):
    pid_path: str = ''

    def design(self, request, historical_evidence):
        Path(self.pid_path).write_text(str(os.getpid()), encoding='ascii')
        while True:
            time.sleep(0.05)


def process_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_real_unavailable_worker_preserves_scientific_axes_and_skips_optional(flow):
    workflow, workspace = flow
    _, _, plan, approval = prepared(flow, optional=True)
    job = workflow.start_run('alice', plan['id'], approval['id'], 'start')
    finished = asyncio.run(Worker(workflow).execute(job))
    assert finished['state'] == 'completed'
    run = workflow.get_run('alice', job['id'])
    children = {child['scenario_id']: child for child in run['scenarios']}
    assert children['baseline']['state'] == 'completed'
    assert children['optional']['state'] == 'skipped'
    evidence = workflow.read_evidence('alice', job['id'], children['baseline']['result_id'])['body']['result']
    assert evidence['scientific_outcome'] == 'unsupported'
    assert evidence['verification'] == 'unsupported'
    assert evidence['expected_binding'] == 'not_supplied'
    assert evidence['reason_code'] == 'groundwork_adapter_not_installed'
    assert run['scientific_reservations'] == 1
    assert ProviderLedger(workflow.store).list_attempts('alice', workspace) == []
    assert Worker(workflow).tick() == 0  # Completed reservation is not redispatched.


def test_unqualified_adapter_cannot_publish_valid_evidence(flow):
    workflow, workspace = flow
    _, _, plan, approval = prepared(flow)
    job = workflow.start_run('alice', plan['id'], approval['id'], 'start')
    finished = asyncio.run(Worker(workflow, adapter=UnqualifiedClaimAdapter()).execute(job))
    assert finished['state'] == 'failed'
    assert finished['error_code'] == 'adapter_not_qualified'
    run = workflow.get_run('alice', job['id'])
    assert run['scenarios'][0]['state'] == 'failed'
    assert run['scenarios'][0]['result_id'] is None
    assert workflow.list_records('alice', workspace, 'evidence') == []


def test_queued_design_expiry_is_checked_before_any_scientific_dispatch(flow, monkeypatch):
    workflow, _ = flow
    _, _, job = queued_design(flow)
    # Advance the service clock without mutating an immutable approval record.
    monkeypatch.setattr('bean_api.workflow.utc_now', lambda: '2099-01-01T00:00:00.000Z')
    dispatched = []
    def forbidden_dispatch(*args, **kwargs):
        dispatched.append(True)
        raise AssertionError('Expired approval reached scientific dispatch')
    monkeypatch.setattr('bean_api.worker.run_bounded', forbidden_dispatch)
    finished = asyncio.run(Worker(workflow).execute(job))
    assert finished['state'] == 'failed'
    assert finished['error_code'] == 'approval_expired'
    assert finished['result_id'] is None
    assert dispatched == []


def test_design_task_cancellation_kills_child_before_terminal_state(flow, tmp_path, monkeypatch):
    workflow, _ = flow
    _, _, job = queued_design(flow)
    pid_path = tmp_path / 'design-child.pid'
    worker = Worker(workflow, adapter=SlowDesignAdapter(str(pid_path)))
    original_finish = workflow.finish_run
    termination_checked = []

    def finish_only_after_termination(actor, job_id, state='completed', **kwargs):
        if job_id == job['id'] and state in {'failed', 'cancelled'}:
            assert pid_path.exists()
            assert not process_alive(int(pid_path.read_text())), 'Job became terminal while child still ran'
            termination_checked.append(True)
        return original_finish(actor, job_id, state, **kwargs)

    monkeypatch.setattr(workflow, 'finish_run', finish_only_after_termination)

    async def exercise():
        task = asyncio.create_task(worker.execute(job))
        try:
            async with asyncio.timeout(8):
                while True:
                    pid_text = pid_path.read_text() if pid_path.exists() else ''
                    if pid_text.isdigit():
                        child_pid = int(pid_text)
                        break
                    if task.done():
                        pytest.fail(f'Design worker ended before launch: {task.result()}')
                    await asyncio.sleep(0.02)
                assert process_alive(child_pid)
                requested = workflow.cancel_run('alice', job['id'], 'cancel')
                assert requested['state'] == 'cancel_requested'
                task.cancel()  # Exercise coroutine cancellation as well as durable cancellation.
                finished = await task
                assert finished['state'] == 'cancelled'
                assert not process_alive(child_pid)
                assert finished['result_id'] is None
        finally:
            if not task.done():
                workflow.cancel_run('alice', job['id'], 'cleanup-cancel')
                task.cancel()
                await task

    asyncio.run(exercise())
    assert termination_checked == [True]


def test_worker_actual_framework_uses_durable_attempts_and_frozen_evidence(flow, monkeypatch):
    workflow, workspace = flow
    _, problem, manual_plan, _ = prepared(flow)
    model = EvidenceModel()
    context_fields = ['problem', 'dataset']
    consent = workflow.create_provider_consent('alice', workspace, {
        'provider': 'gemini', 'model': model.model_name, 'source_asset_ids': [],
        'context_fields': context_fields, 'problem_id': problem['id'], 'accepted': True,
    }, 'provider-consent')
    body = {**manual_plan['body'], 'provider_disclosure': {
        'provider': 'gemini', 'model': model.model_name, 'source_asset_ids': [],
        'context_fields': context_fields, 'permission_id': consent['id'],
    }}
    plan = workflow.create_plan('alice', workspace, body, 'agent-plan')
    approval = workflow.approve_plan('alice', plan['id'], problem['id'], plan['digest'], 'agent-approval')
    job = workflow.start_run('alice', plan['id'], approval['id'], 'start-agent')
    ledger = ProviderLedger(workflow.store)
    config = ProviderConfig(api_key='synthetic-no-network', model=model.model_name,
                            account_gate_passed=True, account_decision_id='controlled-fixture-only')

    async def controlled_coordinator(*args, **kwargs):
        return await real_coordinator(*args, **kwargs, chat_model=model)

    monkeypatch.setattr('bean_api.worker.run_coordinator', controlled_coordinator)
    finished = asyncio.run(Worker(workflow, provider_config=config, ledger=ledger).execute(job))
    assert finished['state'] == 'completed', finished['error_code']
    run = workflow.get_run('alice', job['id'])
    assert run['scientific_reservations'] == 1
    assert run['provider_turns'] == 2
    attempts = ledger.list_attempts('alice', workspace)
    assert len(attempts) == 2
    assert all(attempt['state'] == 'completed' for attempt in attempts)
    assert all(attempt['metadata']['context']['consent_id'] == consent['id'] for attempt in attempts)
    summary = workflow.get('alice', finished['result_id'], 'run_summary')['body']
    assert summary['runtime']['execution_lane'] == 'controlled_model'
    assert summary['runtime']['live_qualified'] is False
    assert summary['explanation']['scientific_authority'] is False
    evidence = workflow.read_evidence('alice', job['id'], run['scenarios'][0]['result_id'])['body']['result']
    assert evidence['problem_id'] == problem['id']
    assert evidence['scientific_outcome'] == 'unsupported'
    event_records = workflow.list_records('alice', workspace, 'agent_event')
    assert any(item['body']['type'] == 'model_request' for item in event_records)
    assert any(item['body']['type'] == 'tool_result' for item in event_records)
    assert Worker(workflow, provider_config=config, ledger=ledger).tick() == 0
    assert len(ledger.list_attempts('alice', workspace)) == 2
