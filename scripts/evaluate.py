#!/usr/bin/env python3
"""Compatibility inventory entry point (corpus integrity + imported evidence). Never dispatches anything.

Scope since the five-workstream split: this script is NOT a second qualification system.
The authoritative evaluation, lanes, append-only attempts and release gates live in
``evaluation/`` (``python3.11 evaluation/cli.py inventory|gate``). This script keeps two jobs:

1. corpus integrity of ``fixtures/intake`` (bytes, size, decodability) — the corpus lane;
2. a compatibility view of *imported* evidence JSONL from older tooling. Every imported
   row is an ``imported_claim``: a supplied ``status: passed`` never becomes qualification.
   References written as ``<repo-relative path>#sha256=<hex>`` are checked; a missing file or
   mismatched digest leaves the row ``unresolved`` with a concrete reason. Duplicate
   ``attempt_id`` values are counted once and reported; rows without an id stay distinct.

Qualification fields are copied from the harness gates when available and otherwise stay
``not_qualified_by_this_offline_report``. Live Gemini stays not run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
LANES = {'deterministic_control', 'live_model_controlled_tools', 'live_intake', 'live_full_stack'}
MATRIX = (
    ('source_intake', 'Chosen image clean intake / ambiguous decimal', ('clean', 'ambiguous_decimal'), 'Source/oracle; actual attempt; unaccepted proposal; reviewed values.'),
    ('grounding', 'OCR self-match / source locator', ('ocr_self_match', 'wrong_locator'), 'Visual transcription remains unreviewed; invalid source/locator denied.'),
    ('allowance_meaning', 'SD / absent future allowance', ('standard_deviation', 'missing_future_allowance'), 'No implicit conversion or historical-allowance reuse.'),
    ('source_conflicts', 'Existing field conflict / missing units', ('conflicting_note', 'missing_units'), 'Typed value preserved; focused blocking clarification.'),
    ('adaptive_execution', 'Real framework evidence-dependent decisions', ('matching_outside_candidate', 'no_outside_candidate'), 'Actual framework inventory and subsequent permitted choice.'),
    ('tool_authority', 'Unapproved job / forbidden tool', ('unapproved_scenario', 'forbidden_tool'), 'Typed denial; no extra reservation; attempts counted.'),
    ('explanation', 'Scope / wrong-problem artifact', ('conditional_scope', 'wrong_problem_binding'), 'Matched factual references; no interval-proof claim.'),
    ('design_authority', 'Separate design approval / missing second evidence', ('baseline_approval_reuse', 'missing_second_candidate'), 'No design job without its exact separate scope.'),
    ('design_arithmetic', 'Positive margin / equality and partial grid', ('positive_margin', 'zero_margin_partial_grid'), 'Owner01 exact adapter verification; every time retained.'),
    ('durability', 'Duplicate / restart after reservation', ('duplicate_submission', 'restart_before_dispatch'), 'Real canonical database race/restart; stable reservation.'),
    ('followup', 'Actual observation / hypothetical reading', ('actual_observation', 'hypothetical_fork'), 'Reviewed immutable lineage; new plan/approval; origin retained.'),
    ('failure_replay', 'Provider failure / replay gates', ('provider_unavailable', 'native_replay'), 'Honest fallback, attempt ledger; fresh supported verifier.'),
)
LIMITS = {
    'intake_invocations': 4,
    'intake_provider_requests': 8,
    'controlled_agent_invocations': 4,
    'controlled_agent_provider_requests': 16,
    'full_stack_invocations': 2,
    'full_stack_provider_requests': 8,
    'total_invocations': 10,
    'total_provider_requests': 32,
    'scientific_jobs': 2,
    'input_tokens': 64000,
    'output_tokens': 16000,
    'monetary_ceiling': None,
}


def inspect_corpus(directory: Path) -> list[dict[str, Any]]:
    manifest = json.loads((directory / 'oracle.json').read_text(encoding='utf-8'))
    checks = []
    for case in manifest['cases']:
        filename = case['file']
        if Path(filename).name != filename or not filename.endswith('.png'):
            raise ValueError('Invalid fixture path')
        path = directory / filename
        raw = path.read_bytes()
        errors = []
        if hashlib.sha256(raw).hexdigest() != case['sha256']:
            errors.append('source_digest_mismatch')
        if len(raw) != case['size_bytes'] or len(raw) > 5 * 1024 * 1024:
            errors.append('source_size_mismatch')
        try:
            with Image.open(path) as image:
                if image.format != 'PNG' or image.size != (case['width'], case['height']):
                    errors.append('source_metadata_mismatch')
                if image.width * image.height > 12000000:
                    errors.append('pixel_budget_exceeded')
                image.verify()
        except (OSError, ValueError):
            errors.append('invalid_image')
        checks.append({'case_id': case['case_id'], 'lane': 'corpus_integrity', 'status': 'failed' if errors else 'passed', 'errors': errors, 'oracle_review_status': case['oracle_review_status']})
    return checks


def validate_reference(reference: Any, root: Path = ROOT) -> dict[str, Any]:
    """'path#sha256=<hex>' is verified against the repository; anything else is an unvalidated label."""
    if not isinstance(reference, str) or not reference.strip():
        return {'reference': reference, 'state': 'invalid', 'reason': 'empty or non-string reference'}
    if '#sha256=' not in reference:
        return {'reference': reference, 'state': 'unvalidated', 'reason': 'opaque label; nothing to verify'}
    rel, digest = reference.split('#sha256=', 1)
    candidate = (root / rel).resolve()
    if root.resolve() not in candidate.parents or not candidate.is_file():
        return {'reference': reference, 'state': 'missing_file', 'reason': f'{rel} is not a file in this repository'}
    actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
    if actual != digest.lower():
        return {'reference': reference, 'state': 'digest_mismatch', 'reason': f'{rel} has sha256 {actual[:12]}...'}
    return {'reference': reference, 'state': 'verified', 'reason': None}


def harness_gates() -> dict[str, Any]:
    """Authoritative qualification lives in the evaluation harness; read it, never recompute it."""
    import sys
    sys.path.insert(0, str(ROOT / 'evaluation'))
    try:
        from drbean_eval import gates, runner
        state = runner.git_state(str(ROOT))
        result = gates.compute(str(ROOT / 'evaluation'), str(ROOT / 'evaluation' / 'results'), state['commit'],
                               state['dirty'], str(ROOT / 'evaluation' / 'findings.json'))
        return {'overall': result['overall'], 'tested_commit': result['tested_commit'],
                'gates': {g['gate']: g['status'] for g in result['gates']}}
    except Exception as error:  # the inventory must still work without the harness
        return {'overall': 'unavailable', 'error': f'{type(error).__name__}'}


def read_attempts(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    attempts = []
    known = {(name, variant) for name, _, variants, _ in MATRIX for variant in variants}
    for line_number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip():
            continue
        item = json.loads(line)
        if not isinstance(item, dict) or (item.get('case_id'), item.get('variant_id')) not in known:
            raise ValueError(f'Unknown case/variant on evidence line {line_number}')
        if item.get('lane') not in LANES:
            raise ValueError(f'Unknown evidence lane on line {line_number}')
        if item.get('status') not in {'passed', 'failed', 'inconclusive', 'blocked'}:
            raise ValueError(f'Invalid evidence status on line {line_number}')
        if not isinstance(item.get('evidence_refs'), list) or not item['evidence_refs']:
            raise ValueError(f'Evidence references required on line {line_number}')
        # All attempts remain in the denominator, including repeated failed cases.
        for field in ('provider_requests', 'input_tokens', 'output_tokens', 'scientific_jobs', 'duration_ms'):
            value = item.get(field)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f'Invalid {field} on line {line_number}')
        if item['lane'] == 'deterministic_control' and (item.get('provider_requests', 0) or item.get('scientific_jobs', 0)):
            raise ValueError('Deterministic evidence cannot claim live provider/science work')
        item = dict(item, evidence_class='imported_claim', line=line_number,
                    reference_checks=[validate_reference(ref) for ref in item['evidence_refs']])
        attempts.append(item)
    return attempts


def deduplicate(attempts: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """Same attempt_id counted once (usage never doubled); rows without an id are distinct attempts."""
    seen, unique, duplicates = set(), [], []
    for attempt in attempts:
        key = attempt.get('attempt_id')
        if key is not None and key in seen:
            duplicates.append(str(key))
            continue
        if key is not None:
            seen.add(key)
        unique.append(attempt)
    return unique, duplicates


def total_if_known(attempts: list[dict[str, Any]], field: str) -> int | None:
    if any(attempt.get(field) is None for attempt in attempts):
        return None
    return sum(attempt[field] for attempt in attempts)


def build_report(directory: Path, attempts: list[dict[str, Any]] | None = None,
                 include_harness: bool = False) -> dict[str, Any]:
    attempts, duplicates = deduplicate(attempts or [])
    corpus = inspect_corpus(directory)
    live = [attempt for attempt in attempts if attempt['lane'] != 'deterministic_control']
    rows = []
    for name, title, variants, required in MATRIX:
        for variant in variants:
            matching = [attempt for attempt in attempts if attempt['case_id'] == name and attempt['variant_id'] == variant]
            broken = [check for attempt in matching for check in attempt.get('reference_checks', [])
                      if check['state'] in ('missing_file', 'digest_mismatch', 'invalid')]
            status = 'not_run' if not matching else 'unresolved' if broken else 'evidence_imported'
            rows.append({'case_id': name, 'name': title, 'variant_id': variant, 'required_evidence': required,
                         'status': status, 'evidence_class': 'imported_claim' if matching else None,
                         'unresolved_reasons': [check['reason'] for check in broken], 'attempts': matching})
    counts = Counter(attempt['status'] for attempt in attempts)
    durations = [attempt['duration_ms'] for attempt in live if attempt.get('duration_ms') is not None]
    requests = total_if_known(live, 'provider_requests')
    input_tokens = total_if_known(live, 'input_tokens') if live else None
    output_tokens = total_if_known(live, 'output_tokens') if live else None
    jobs = total_if_known(live, 'scientific_jobs')
    exceeded = []
    for name, actual, cap in [('total_provider_requests', requests, 32), ('input_tokens', input_tokens, 64000), ('output_tokens', output_tokens, 16000), ('scientific_jobs', jobs, 2)]:
        if actual is not None and actual > cap:
            exceeded.append(name)
    return {
        'schema_version': 'dr-bean-evaluation-report-v1',
        'contract': 'DB-SC-1',
        'policy': 'GF-2',
        'generated_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'runner_network_calls': 0,
        'corpus_checks': corpus,
        'matrix_scope': 'Backend mapping of the supplied acceptance table; Owner04 agreement pending. Not a claim that 24 application or live traces ran.',
        'matrix': rows,
        'summary': {'planned_cases': 12, 'planned_variants': 24, 'corpus_integrity_passed': sum(x['status'] == 'passed' for x in corpus), 'imported_attempt_count': len(attempts), 'live_attempt_count': len(live), 'statuses': dict(counts), 'duplicate_records': duplicates, 'unresolved_rows': sum(row['status'] == 'unresolved' for row in rows)},
        'scope': 'compatibility inventory; authoritative lanes and gates: python3.11 evaluation/cli.py inventory',
        'harness_gates': harness_gates() if include_harness else {'overall': 'not_requested'},
        'shared_live_allocation': LIMITS,
        'observed_imported_usage': {'provider_requests': requests, 'input_tokens': input_tokens, 'output_tokens': output_tokens, 'scientific_jobs': jobs, 'cost': None, 'allocation_exceeded': exceeded},
        'live_latency_ms': {'sample_count': len(durations), 'median': median(durations) if durations else None, 'min': min(durations) if durations else None, 'max': max(durations) if durations else None},
        'human_review': {'correction_count': None, 'locator_usefulness': None, 'task_completion_time_ms': None, 'unintended_acceptance_count': None},
        'qualification': {'live_gemini': 'not_qualified_by_this_offline_report', 'live_deepagents': 'not_qualified_by_this_offline_report', 'checked_science': 'not_qualified_by_this_offline_report', 'native_replay': 'not_qualified_by_this_offline_report', 'browser_replay': 'unsupported_until_separately_qualified'},
        'next_gates': ['Independent owner review of source oracle and matrix mapping.', 'Record account/audience/region/data-use decision and approved monetary ceiling before live calls.', 'Configure chosen model and run authorized actual SDK/framework capability probes within one shared ledger.', 'Obtain Owner01 matching adapter evidence and fresh replay; attach real provider/tool/review records.', 'Have another owner compare actual explanation prose to the factual envelope.'],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', type=Path, default=ROOT / 'fixtures' / 'intake')
    parser.add_argument('--attempts', type=Path, help='Optional retained evidence JSONL; never replaces earlier attempts.')
    parser.add_argument('--output', type=Path, help='Write the JSON report here; otherwise print to stdout.')
    args = parser.parse_args()
    report = build_report(args.corpus, read_attempts(args.attempts), include_harness=True)
    encoded = json.dumps(report, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding='utf-8')
    else:
        print(encoded, end='')
    return 1 if any(row['status'] == 'failed' for row in report['corpus_checks']) or report['observed_imported_usage']['allocation_exceeded'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
