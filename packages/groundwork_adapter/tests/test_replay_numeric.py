"""Recorded-arithmetic validation is deliberately distinct from fresh science."""
from copy import deepcopy
from decimal import localcontext
import os
import subprocess
import sys
import unittest

from counterdex.errors import AdapterError
from counterdex.models import normalize_design
from counterdex.numerical import compare_grid
from counterdex.replay_numeric import validate_numerical_record
from counterdex.resource import ExecutionContext
from helpers import synthetic_inputs


class RecordedNumericalTests(unittest.TestCase):
    def setUp(self):
        self.problem, self.design = synthetic_inputs()
        self.record = compare_grid(self.problem, self.design)

    def rejected(self, change):
        record = deepcopy(self.record)
        change(record)
        with self.assertRaises(AdapterError):
            validate_numerical_record(record, self.design)

    def test_valid_record(self):
        self.assertIsNone(validate_numerical_record(self.record, self.design))

    def test_exact_field_sets_including_nested_predictions(self):
        for change in (
            lambda r: r.update(certified=True),
            lambda r: r["rows"][0].update(separated=True),
            lambda r: r["rows"][0]["predictions"].update(unselected="1.0"),
            lambda r: r.pop("execution"),
            lambda r: r["rows"][0].pop("tied"),
        ):
            self.rejected(change)

    def test_rejects_modified_arithmetic_ranking_and_count(self):
        for change in (
            lambda r: r["rows"][0].update(gap_approximation="1.0"),
            lambda r: r["rows"][0].update(score_approximation="1.0"),
            lambda r: r["rows"][0].update(ranking_score="1"),
            lambda r: r["rows"][0].update(rank=True),
            lambda r: r["rows"][0].update(tied=True),
            lambda r: r.update(evaluated_count=True),
            lambda r: r.update(selected_time="0/1"),
            lambda r: r.update(ranked_times=list(reversed(r["ranked_times"]))),
            lambda r: r.update(partial=True),
            lambda r: r.update(outcome="checked_pair_separation"),
        ):
            self.rejected(change)

    def test_finite_canonical_diagnostic_strings_required(self):
        for invalid in ("NaN", "Infinity", "-0.0", "1e9999", "1.0 " , "1_000.0", "1.00", "1" * 65, 1.0, True):
            with self.subTest(value=invalid):
                self.rejected(lambda r: r["rows"][0]["predictions"].update({self.design.candidates[0].id: invalid}))

    def test_declared_grid_and_feasibility_must_match(self):
        for change in (
            lambda r: r["rows"].reverse(),
            lambda r: r["rows"].pop(),
            lambda r: r["rows"][0].update(time="6"),
            lambda r: r["rows"][0].update(feasibility_reason="different decision"),
            lambda r: r["rows"][0].update(reason_code="cancelled"),
        ):
            self.rejected(change)

    def test_cancelled_partial_record_and_latched_stop(self):
        calls = []
        def cancelled():
            calls.append(1)
            return len(calls) > 1
        record = compare_grid(self.problem, self.design, ExecutionContext(cancelled=cancelled, clock=lambda: 0))
        self.assertEqual(record["evaluated_count"], 1)
        validate_numerical_record(record, self.design)
        for field, value in (("execution", "completed"), ("partial", False)):
            damaged = deepcopy(record)
            damaged[field] = value
            with self.assertRaises(AdapterError):
                validate_numerical_record(damaged, self.design)
        damaged = deepcopy(record)
        damaged["rows"][1]["predictions"][self.design.candidates[0].id] = "0.0"
        with self.assertRaises(AdapterError):
            validate_numerical_record(damaged, self.design)

    def test_deadline_range_failure_and_infeasibility_records(self):
        clocks = iter((0, 121))
        interrupted = compare_grid(self.problem, self.design, ExecutionContext(clock=lambda: next(clocks)))
        validate_numerical_record(interrupted, self.design)
        self.assertEqual(interrupted["execution"], "interrupted")
        payload = self.design.to_payload()
        payload["grid"][1].update(feasible=False, reason="equipment unavailable")
        design = normalize_design(payload, self.problem)
        validate_numerical_record(compare_grid(self.problem, design), design)
        payload = self.design.to_payload()
        payload["requested_tier"] = "numerical_guidance"
        payload["grid"][1]["time"] = "10000/1"
        design = normalize_design(payload, self.problem)
        failed = compare_grid(self.problem, design)
        self.assertEqual(failed["rows"][1]["status"], "failed")
        validate_numerical_record(failed, design)

    def test_stored_score_ties_and_zero_selection(self):
        payload = self.design.to_payload()
        payload["grid"] = [{"time": t, "feasible": True, "reason": "control"} for t in ("6", "6.00000000000001")]
        design = normalize_design(payload, self.problem)
        tied = compare_grid(self.problem, design)
        self.assertTrue(all(row["tied"] for row in tied["rows"]))
        validate_numerical_record(tied, design)
        payload["grid"] = [{"time": "0", "feasible": True, "reason": "zero control"}]
        design = normalize_design(payload, self.problem)
        zero = compare_grid(self.problem, design)
        self.assertIsNone(zero["selected_time"])
        validate_numerical_record(zero, design)

    def test_validation_ignores_process_decimal_precision(self):
        with localcontext() as context:
            context.prec = 2
            context.Emax = 3
            context.Emin = -3
            validate_numerical_record(self.record, self.design)
            self.assertEqual(compare_grid(self.problem, self.design), self.record)

    def test_coherent_arbitrary_predictions_are_not_fresh_science(self):
        # This is intentional: the validator proves arithmetic consistency only.
        record = deepcopy(self.record)
        for row in record["rows"]:
            row.update(predictions={cid: "1.0" for cid in row["predictions"]},
                       gap_approximation="0.0", score_approximation="0.0", ranking_score="0", rank=1, tied=True)
        record.update(ranked_times=[r["time"] for r in record["rows"]], selected_time=None, outcome="no_useful_suggestion")
        validate_numerical_record(record, self.design)

    def test_replay_import_does_not_import_numerical(self):
        script = "import sys; import counterdex.replay_numeric; assert 'counterdex.numerical' not in sys.modules"
        subprocess.run([sys.executable, "-c", script], check=True, env=os.environ.copy(), capture_output=True)


if __name__ == "__main__":
    unittest.main()
