"""Unit tests for the harness's own oracles, ledger and sanitizer. Standard library only."""
import json
import os
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from fractions import Fraction as F

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(ROOT)
sys.path.insert(0, ROOT)

from drbean_eval import admission, contract, manifest, oracles, sanitize  # noqa: E402
from drbean_eval.budget import BudgetLedger, BudgetStop  # noqa: E402


class RationalAndCanonicalJson(unittest.TestCase):
    def test_canonical_rational_grammar(self):
        for good in ("0/1", "1/1", "-1/2", "17/100", "534984763/100000000"):
            self.assertTrue(contract.is_canonical_rational(good), good)
        for bad in ("0/2", "-0/1", "+1/2", "2/4", "1/0", "1/-2", "01/2", "1/02", "0.5", "1", " 1/2", 0.5, None):
            self.assertFalse(contract.is_canonical_rational(bad), bad)

    def test_decimal_conversion_is_exact(self):
        self.assertEqual(contract.decimal_to_rational("0.10"), "1/10")
        self.assertEqual(contract.decimal_to_rational("5.34984763"), "534984763/100000000")
        self.assertEqual(contract.decimal_to_rational("-0.0"), "0/1")
        self.assertEqual(contract.decimal_to_rational("0.1"), "1/10")  # not 3602879701896397/36028797018963968
        # Oracle revision 2 follows the authoritative API grammar (bean_api.canonical.parse_decimal):
        # a sign, a bare leading or trailing point and a bounded decimal exponent are admitted.
        self.assertEqual(contract.decimal_to_rational(".5"), "1/2")
        self.assertEqual(contract.decimal_to_rational("5."), "5/1")
        self.assertEqual(contract.decimal_to_rational("+5"), "5/1")
        self.assertEqual(contract.decimal_to_rational("1e3"), "1000/1")
        self.assertEqual(contract.decimal_to_rational("1.5E-2"), "3/200")
        for bad in ("NaN", "0x10", "1/2", "", ".", "e5", "+", "1e129", "1e1000", "1e0001", " 1", "1 ", "0.5\n"):
            with self.assertRaises(contract.ContractError, msg=repr(bad)):
                contract.decimal_to_rational(bad)

    def test_canonical_json_profile(self):
        self.assertEqual(contract.canonical_json({"b": [1, None, True], "a": "x"}), b'{"a":"x","b":[1,null,true]}')
        self.assertEqual(contract.canonical_json("é\n\t\"\\/ \x01"),
                         '"é\\n\\t\\"\\\\/ \\u0001"'.encode("utf-8"))
        self.assertEqual(contract.canonical_json(["b", "a"]), b'["b","a"]')  # arrays keep declared order
        for bad in (1.5, -1, 2 ** 53, {"é": 1}, {1: 2}, "\ud800", float("nan")):
            with self.assertRaises(contract.ContractError):
                contract.canonical_json(bad)

    def test_strict_parse_rejects_instead_of_repairing(self):
        self.assertEqual(contract.parse_strict(b'{"a":"1/2","n":3}'), {"a": "1/2", "n": 3})
        for bad in (b'{"a":1,"a":2}', b'{"a":0.5}', b'{"a":NaN}', b'{"a":1e2}', b'\xff', b'{"a":-1}',
                    b'{"a":"\x01"}', b"[" * 100 + b"]" * 100, b'{"a":9007199254740992}'):
            with self.assertRaises(contract.ContractError, msg=bad[:20]):
                contract.parse_strict(bad)

    def test_identity_prefix_and_kinds(self):
        import hashlib
        body = {"value": "1/2"}
        want = hashlib.sha256(b'dr-bean:plan:v1\n{"value":"1/2"}').hexdigest()
        self.assertEqual(contract.identity("plan", body), want)
        self.assertNotEqual(contract.identity("problem", body), want)
        with self.assertRaises(contract.ContractError):
            contract.identity("approval", body)

    def test_error_body_shape(self):
        good = {"code": "x", "message": "m", "field_paths": [], "retryable": False, "current_revision_id": None,
                "request_id": "r"}
        self.assertEqual(contract.check_error_body(good), [])
        self.assertTrue(contract.check_error_body({**good, "provider_payload": "leak"}))
        self.assertTrue(contract.check_error_body({k: v for k, v in good.items() if k != "request_id"}))

    def test_web_exact_parser_agrees_with_oracle(self):
        """Cross-language check available today: Owner 03's parseExact against this oracle."""
        if not shutil.which("node"):
            self.skipTest("node is not installed")
        samples = ["0.10", "17/100", "5.34984763", "0.3", "12", "0.25", "1/2", "2/4", "-0.50", "0", "100/10",
                   "0.1", "123456789012345678901234567890.000000000000000000000000000001"]
        script = ("import {parseExact} from './apps/web/exact.mjs';"
                  f"console.log(JSON.stringify({json.dumps(samples)}.map(parseExact)))")
        out = subprocess.run(["node", "--input-type=module", "-e", script], cwd=REPO, capture_output=True,
                             text=True, check=True).stdout
        for sample, got in zip(samples, json.loads(out)):
            self.assertTrue(contract.is_canonical_rational(got), f"{sample} -> {got}")
            if "/" in sample:
                n, d = sample.split("/")
                self.assertEqual(contract.to_fraction(got), F(int(n), int(d)))
            else:
                self.assertEqual(got, contract.decimal_to_rational(sample))


class Oracles(unittest.TestCase):
    def test_work_order_numbers(self):
        self.assertEqual(oracles.margin(F(1, 2), F(1, 10), F(1, 5), F(1, 5)), F(-1, 10))
        self.assertEqual(oracles.margin(F(1, 4), F(1, 10)), F(1, 20))
        self.assertEqual(oracles.constructed_margin(F(1, 5)), 0)
        self.assertFalse(oracles.establishes_separation(oracles.constructed_margin(F(1, 5))))
        self.assertTrue(oracles.establishes_separation(oracles.constructed_margin(F(1, 4))))
        with self.assertRaises(ValueError):
            oracles.margin(F(1), F(0))

    def test_datum_rejects_both_endpoints_but_not_the_midpoint(self):
        datum, allowance, t = F(1, 2), F(1, 10), F(1)
        self.assertFalse(oracles.compatible(oracles.constructed_center(F(0), t), datum, allowance))
        self.assertFalse(oracles.compatible(oracles.constructed_center(F(1), t), datum, allowance))
        self.assertTrue(oracles.compatible(oracles.constructed_center(F(1, 2), t), datum, allowance))

    def test_selection_ignores_raw_score(self):
        options = [{"id": "hi", "margin": F(-1, 10), "time": F(1), "candidate_ids": ("a", "b")},
                   {"id": "lo", "margin": F(1, 20), "time": F(2), "candidate_ids": ("a", "b")},
                   {"id": "later", "margin": F(1, 20), "time": F(3), "candidate_ids": ("a", "b")}]
        self.assertEqual(oracles.select_checked(options)["id"], "lo")
        self.assertIsNone(oracles.select_checked(options[:1]))
        self.assertGreater(oracles.raw_score(F(1, 2), F(1, 10)), oracles.raw_score(F(1, 4), F(1, 10)))

    def test_c11_and_c12_fixtures_agree_with_the_oracle(self):
        """The frozen expected values are recomputed, not trusted."""
        case = manifest.load_case(ROOT, "C11")
        for letter in "AB":
            variant = case["variants"][letter]
            eta = contract.to_fraction(variant["input"]["design_request"]["eta"])
            wanted = {a["path"]: a["value"] for a in variant["expected"] if a["path"].endswith(".margin")}
            options = []
            for pair in variant["controlled"]["pair_evaluations"]:
                m = oracles.margin(*(contract.to_fraction(pair[k]) for k in ("delta",)), eta,
                                   contract.to_fraction(pair["e1"]), contract.to_fraction(pair["e2"]))
                self.assertEqual(contract.from_fraction(m),
                                 wanted[f"design.options[option_id={pair['option_id']}].margin"])
                options.append({"id": pair["option_id"], "margin": m, "time": contract.to_fraction(pair["time"]),
                                "candidate_ids": ("a", "b")})
            chosen = oracles.select_checked(options)
            if letter == "A":
                self.assertIsNone(chosen)
            else:
                self.assertEqual(chosen["id"], "low-score")
        datum = manifest.load_case(ROOT, "C12")["variants"]["A"]["input"]["observation_proposal"]
        t, value, allowance = (contract.to_fraction(datum[k]) for k in ("time", "value", "allowance"))
        self.assertFalse(oracles.compatible(0 * t, value, allowance))
        self.assertFalse(oracles.compatible(1 * t, value, allowance))


class Budget(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.ledger = BudgetLedger(os.path.join(self.dir, "budget.jsonl"))

    def tearDown(self):
        shutil.rmtree(self.dir)

    def open(self, **caps):
        self.ledger.open_cohort("test", "A. Human", "synthetic test allowance", caps)

    def reserve(self, i=100, o=50):
        return self.ledger.reserve("test", "unit", "C01", i, o, "unit-test bound")

    def test_no_cohort_means_no_live_request(self):
        with self.assertRaises(BudgetStop):
            self.reserve()
        self.assertEqual(self.ledger.state()["committed"]["provider_requests"], 0)

    def test_caps_can_only_be_lowered_and_need_a_human(self):
        with self.assertRaises(ValueError):
            self.open(provider_requests=33)
        with self.assertRaises(ValueError):
            self.ledger.open_cohort("x", " ", "note")
        self.open(provider_requests=3)
        with self.assertRaises(BudgetStop):  # never a second cohort automatically
            self.open()

    def test_reserve_then_reconcile_actual_usage(self):
        self.open()
        rid = self.reserve(3000, 700)
        self.assertEqual(self.ledger.state()["committed"], {"provider_requests": 1, "input_tokens": 3000,
                                                            "output_tokens": 700})
        self.ledger.reconcile(rid, 1200, 300, "completed", "req-1")
        self.assertEqual(self.ledger.state()["committed"], {"provider_requests": 1, "input_tokens": 1200,
                                                            "output_tokens": 300})
        with self.assertRaises(ValueError):
            self.ledger.reconcile(rid, 1, 1, "again")

    def test_timeout_is_not_free(self):
        self.open()
        rid = self.reserve(3000, 700)
        self.ledger.mark_unknown(rid, "timeout after dispatch")
        state = self.ledger.state()
        self.assertEqual(state["committed"]["input_tokens"], 3000)
        self.assertEqual(state["unreconciled"], [rid])
        with self.assertRaises(ValueError):
            self.ledger.release_unsent(rid, "pretend it never happened")
        self.ledger.reconcile(rid, 2500, 0, "provider confirmed billing")
        self.assertEqual(self.ledger.state()["unreconciled"], [])

    def test_stops_before_a_request_that_cannot_fit(self):
        self.open(provider_requests=2, input_tokens=5000)
        self.reserve(3000, 100)
        with self.assertRaises(BudgetStop):
            self.reserve(3000, 100)
        self.reserve(2000, 100)
        with self.assertRaises(BudgetStop):
            self.reserve(1, 1)
        events = [json.loads(line)["event"] for line in pathlib.Path(self.ledger.path).read_text().splitlines()]
        self.assertEqual(events.count("budget_stop"), 2)  # stops are retained

    def test_unbounded_request_is_refused(self):
        self.open()
        with self.assertRaises(BudgetStop):
            self.ledger.reserve("t", "p", "C01", 0, 100, "unknown")
        with self.assertRaises(BudgetStop):
            self.ledger.reserve("t", "p", "C01", 100, 100, " ")

    def test_overrun_is_recorded_not_hidden(self):
        self.open()
        rid = self.reserve(100, 50)
        self.assertTrue(self.ledger.reconcile(rid, 150, 50, "completed")["overrun"])

    def test_scheduled_live_maxima_fit_the_cohort_caps(self):
        m = manifest.load(ROOT)
        live = m["schedule"]["live"]
        self.assertEqual(len(live) + len(m["schedule"]["actual_full_stack"]), 10)
        intake = sum(e["lane"] == "live_intake" for e in live)
        self.assertEqual(intake * 2 + (10 - intake) * 4, 32)  # 4*2 + 4*4 + 2*4


class SanitizerAndAdmission(unittest.TestCase):
    def test_redaction_and_dropped_keys(self):
        key = "AIza" + "B" * 35
        mail, query = "a@" + "b.io", "?tok" + "en=abc123&x=1"  # split so the repository scan stays clean
        dirty = {"raw_prompt": "secret prompt", "note": f"key={key} Bear" + f"er abcdefghijklmnop1234 {mail}",
                 "url": "https://x.example/r" + query, "nested": [{"thoughts": "hidden"}]}
        clean = sanitize.sanitize(dirty)
        text = json.dumps(clean)
        self.assertNotIn(key, text)
        self.assertNotIn("secret prompt", text)
        self.assertNotIn("hidden", text)
        self.assertNotIn("abc123", text)
        self.assertNotIn(mail, text)
        self.assertEqual(sanitize.find_leaks(text), [])
        self.assertTrue(sanitize.find_leaks(json.dumps(dirty)))

    def test_sentinels_are_detected(self):
        for sentinel in sanitize.SENTINELS:
            self.assertEqual(sanitize.find_leaks("x " + sentinel)[0]["kind"], "sentinel")

    def test_admission_assets_cross_the_caps(self):
        out = tempfile.mkdtemp()
        try:
            cases = {c["id"]: c for c in admission.generate(out, os.path.join(ROOT, "sources", "c01a.png"))}
            self.assertGreater(cases["ADM-01"]["bytes"], admission.MAX_BYTES)
            for case_id, pixels in (("ADM-02", 4001 * 3000), ("ADM-03", 30000 * 30000)):
                data = pathlib.Path(cases[case_id]["file"]).read_bytes()
                self.assertLess(len(data), admission.MAX_BYTES)
                width, height = struct.unpack(">II", data[16:24])
                self.assertEqual(width * height, pixels)
                self.assertGreater(pixels, admission.MAX_PIXELS)
            good = pathlib.Path(ROOT, "sources", "c01a.png").read_bytes()
            self.assertLess(len(good), admission.MAX_BYTES)
            self.assertLess(struct.unpack(">I", good[16:20])[0] * struct.unpack(">I", good[20:24])[0],
                            admission.MAX_PIXELS)
        finally:
            shutil.rmtree(out)


if __name__ == "__main__":
    unittest.main()
