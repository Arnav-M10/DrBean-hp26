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
