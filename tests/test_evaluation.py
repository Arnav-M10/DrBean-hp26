from __future__ import annotations

import importlib.util
import json
import shutil
from fractions import Fraction
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('evaluate', ROOT / 'scripts' / 'evaluate.py')
assert SPEC and SPEC.loader
evaluate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluate)


def test_corpus_integrity_and_exact_oracle():
    checks = evaluate.inspect_corpus(ROOT / 'fixtures' / 'intake')
    assert len(checks) == 8
    assert all(c['status'] == 'passed' for c in checks)
    oracle = json.loads((ROOT / 'fixtures' / 'intake' / 'oracle.json').read_text())
    for case in oracle['cases']:
        assert case['accepted_data_mutation_before_review'] is False
        assert case['approval_created_by_intake'] is False
        assert case['scientific_outcome'] is None
        for field in case['expected_fields']:
            assert Fraction(field['original_value']) == Fraction(field['candidate_exact'])
    ambiguous = next(c for c in oracle['cases'] if c['case_id'] == 'ambiguous_decimal')
    assert ambiguous['ambiguity']['possible_visual_readings'] == ['0.05', '0.5']
    assert ambiguous['ambiguity']['candidate_requires_human_review'] is True


def test_changed_source_bytes_are_detected(tmp_path):
    corpus = tmp_path / 'corpus'
    shutil.copytree(ROOT / 'fixtures' / 'intake', corpus)
    with (corpus / 'clean.png').open('ab') as handle:
        handle.write(b'changed')
    check = next(c for c in evaluate.inspect_corpus(corpus) if c['case_id'] == 'clean')
    assert check['status'] == 'failed'
    assert 'source_digest_mismatch' in check['errors']


def test_empty_report_does_not_claim_model_or_science_success():
    report = evaluate.build_report(ROOT / 'fixtures' / 'intake')
    assert len(report['matrix']) == 24
    assert all(c['status'] == 'not_run' for c in report['matrix'])
    assert report['runner_network_calls'] == 0
    assert report['observed_imported_usage']['provider_requests'] == 0
    assert report['observed_imported_usage']['input_tokens'] is None
    assert report['observed_imported_usage']['cost'] is None
    assert report['human_review']['correction_count'] is None
    assert report['live_latency_ms']['sample_count'] == 0


def test_failed_attempts_retained_and_unknown_usage_not_zero(tmp_path):
    path = tmp_path / 'attempts.jsonl'
    base = {'case_id': 'source_intake', 'variant_id': 'clean', 'lane': 'live_intake', 'provider_requests': 1, 'evidence_refs': ['synthetic-example-reference']}
    path.write_text('\n'.join(json.dumps(dict(base, status=status)) for status in ['failed', 'passed']))
    attempts = evaluate.read_attempts(path)
    report = evaluate.build_report(ROOT / 'fixtures' / 'intake', attempts)
    assert report['summary']['imported_attempt_count'] == 2
    assert report['summary']['statuses'] == {'failed': 1, 'passed': 1}
    assert report['observed_imported_usage']['provider_requests'] == 2
    assert report['observed_imported_usage']['input_tokens'] is None
    assert report['observed_imported_usage']['scientific_jobs'] is None
    assert report['matrix'][0]['status'] == 'evidence_imported'
    assert report['qualification']['live_gemini'] == 'not_qualified_by_this_offline_report'


def test_evidence_rejects_fake_deterministic_live_work(tmp_path):
    path = tmp_path / 'attempts.jsonl'
    path.write_text(json.dumps({'case_id': 'source_intake', 'variant_id': 'clean', 'lane': 'deterministic_control', 'provider_requests': 1, 'status': 'passed', 'evidence_refs': ['fixture']}))
    with pytest.raises(ValueError, match='Deterministic'):
        evaluate.read_attempts(path)


def test_imported_over_budget_usage_is_visible():
    attempts = [{'case_id': 'source_intake', 'variant_id': 'clean', 'lane': 'live_intake', 'status': 'failed', 'provider_requests': 33, 'input_tokens': 64001, 'output_tokens': 16001, 'scientific_jobs': 3, 'evidence_refs': ['over-budget-control']}]
    report = evaluate.build_report(ROOT / 'fixtures' / 'intake', attempts)
    assert set(report['observed_imported_usage']['allocation_exceeded']) == {'total_provider_requests', 'input_tokens', 'output_tokens', 'scientific_jobs'}


@pytest.mark.parametrize('case_id', ['clean', 'ambiguous_decimal', 'missing_units', 'standard_deviation', 'conflicting_note', 'embedded_instruction', 'unsupported_model', 'unreadable'])
def test_synthetic_corpus_passes_real_media_admission(case_id):
    # Admission establishes bounded decodability, never scientific/readability truth.
    from bean_api.intake import inspect_image
    raw = (ROOT / 'fixtures' / 'intake' / (case_id + '.png')).read_bytes()
    metadata = inspect_image(raw, 'image/png')
    assert metadata == {'observed_media_type': 'image/png', 'width': 1200, 'height': 1550}


# --- Compatibility inventory reconciliation (Workstream 5) -------------------------------------

def _rows(tmp_path, items):
    path = tmp_path / 'attempts.jsonl'
    path.write_text('\n'.join(json.dumps(item) for item in items))
    return evaluate.read_attempts(path)


BASE = {'case_id': 'source_intake', 'variant_id': 'clean', 'lane': 'live_intake', 'status': 'passed'}


def test_imported_pass_is_a_claim_and_never_qualification(tmp_path):
    attempts = _rows(tmp_path, [dict(BASE, evidence_refs=['looks-official-but-opaque'])])
    report = evaluate.build_report(ROOT / 'fixtures' / 'intake', attempts)
    row = report['matrix'][0]
    assert row['status'] == 'evidence_imported' and row['evidence_class'] == 'imported_claim'
    assert report['qualification']['live_gemini'] == 'not_qualified_by_this_offline_report'
    assert report['qualification']['checked_science'] == 'not_qualified_by_this_offline_report'
    assert attempts[0]['reference_checks'][0]['state'] == 'unvalidated'


def test_fabricated_file_reference_and_wrong_digest_are_unresolved(tmp_path):
    real = 'fixtures/intake/clean.png'
    wrong = real + '#sha256=' + '0' * 64
    good = real + '#sha256=6363da39c1a7a86e45e5a9d5f17aa87006130cc75c61844f4902be0f118c0b06'
    attempts = _rows(tmp_path, [dict(BASE, evidence_refs=['evaluation/results/traces/att_fake.json#sha256=' + 'a' * 64]),
                                dict(BASE, variant_id='ambiguous_decimal', evidence_refs=[wrong]),
                                dict(BASE, case_id='grounding', variant_id='ocr_self_match', evidence_refs=[good])])
    report = evaluate.build_report(ROOT / 'fixtures' / 'intake', attempts)
    by_variant = {row['variant_id']: row for row in report['matrix']}
    assert by_variant['clean']['status'] == 'unresolved'
    assert 'is not a file' in by_variant['clean']['unresolved_reasons'][0]
    assert by_variant['ambiguous_decimal']['status'] == 'unresolved'
    assert 'sha256' in by_variant['ambiguous_decimal']['unresolved_reasons'][0]
    assert by_variant['ocr_self_match']['status'] == 'evidence_imported'
    assert report['summary']['unresolved_rows'] == 2


def test_duplicate_attempt_ids_are_counted_once_but_repeats_without_ids_stay_distinct(tmp_path):
    one = dict(BASE, attempt_id='att-1', provider_requests=1, evidence_refs=['r'])
    attempts = _rows(tmp_path, [one, one, dict(BASE, provider_requests=1, evidence_refs=['r']),
                                dict(BASE, provider_requests=1, evidence_refs=['r'])])
    report = evaluate.build_report(ROOT / 'fixtures' / 'intake', attempts)
    assert report['summary']['duplicate_records'] == ['att-1']
    assert report['summary']['imported_attempt_count'] == 3
    assert report['observed_imported_usage']['provider_requests'] == 3


def test_imported_unknown_usage_stays_unknown_and_failures_are_retained(tmp_path):
    attempts = _rows(tmp_path, [dict(BASE, status='failed', provider_requests=None, evidence_refs=['r']),
                                dict(BASE, status='passed', provider_requests=2, evidence_refs=['r'])])
    report = evaluate.build_report(ROOT / 'fixtures' / 'intake', attempts)
    assert report['observed_imported_usage']['provider_requests'] is None
    assert report['summary']['statuses'] == {'failed': 1, 'passed': 1}


def test_inventory_reads_harness_gates_and_never_dispatches():
    report = evaluate.build_report(ROOT / 'fixtures' / 'intake', [], include_harness=True)
    assert report['runner_network_calls'] == 0
    gates = report['harness_gates']
    assert gates['overall'] in {'passed', 'failed', 'blocked', 'unavailable'}
    if gates['overall'] != 'unavailable':
        assert gates['gates']['live_gemini_qualification'] == 'not_run'


# --- Oracle and endpoint agreement with Owner 2's authoritative admission golden ----------------

GOLDEN = json.loads((ROOT / 'shared' / 'contracts' / 'DB-SC-1' / 'fixtures' / 'admission-golden.json').read_text())


def _oracle():
    import sys
    sys.path.insert(0, str(ROOT / 'evaluation'))
    from drbean_eval import contract
    return contract


def test_evaluation_oracle_agrees_with_admission_golden():
    contract = _oracle()
    for case in GOLDEN['rational_cases']:
        assert contract.is_canonical_rational(case['value']) is case['accepted'], repr(case['value'][:20])
    for case in GOLDEN['json_cases']:
        try:
            contract.parse_strict(case['raw'].encode())
            accepted = True
        except contract.ContractError:
            accepted = False
        assert accepted is case['accepted'], case['raw'][:40]
    for case in GOLDEN['byte_cases']:
        try:
            contract.parse_strict(case['raw'].encode(), max_bytes=case['max_bytes'])
            accepted = True
        except contract.ContractError:
            accepted = False
        assert accepted is case['accepted'], (case['raw'], case['max_bytes'])


def test_api_endpoints_agree_with_admission_golden(tmp_path):
    from fastapi.testclient import TestClient
    from bean_api.config import Settings
    from bean_api.main import PREFIX, create_app
    settings = Settings(database_path=str(tmp_path / 'db.sqlite3'), blob_dir=str(tmp_path / 'blobs'),
                        artifact_dir=str(tmp_path / 'artifacts'), auth_tokens={'alice': 'a' * 40})
    with TestClient(create_app(settings)) as client:
        client.headers['Authorization'] = 'Bearer ' + 'a' * 40
        for case in GOLDEN['json_cases']:  # the strict wire parser runs before any schema validation
            response = client.post(PREFIX + '/exact/decimal', content=case['raw'].encode(),
                                   headers={'Content-Type': 'application/json', 'Idempotency-Key': 'k'})
            wire_rejected = response.status_code == 422 and response.json()['code'] == 'invalid_json'
            assert wire_rejected is (not case['accepted']), (case['raw'][:40], response.status_code)
        workspace = client.post(PREFIX + '/workspaces', json={'name': 'golden'}).json()['id']
        hero = json.loads((ROOT / 'evaluation' / 'cases' / 'science' / 'hero-v2.json').read_text())
        for index, case in enumerate(GOLDEN['rational_cases']):  # a nonnegative time field admits any legal rational
            rows = [dict(row) for row in hero['dataset']['rows']]
            rows[0] = {**rows[0], 'time': case['value']}
            response = client.post(PREFIX + f'/workspaces/{workspace}/datasets', json={**hero['dataset'], 'rows': rows},
                                   headers={'Idempotency-Key': f'golden-{index}'})
            assert (response.status_code == 201) is case['accepted'], (repr(case['value'][:20]), response.status_code)
