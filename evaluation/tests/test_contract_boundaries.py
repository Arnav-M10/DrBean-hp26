"""Golden boundary values for the DB-SC-1 oracle, compared against the authoritative API implementation.

The expectations below are written independently (by hand from the profile), then the
same corpus is run through ``apps/api/bean_api/canonical.py``. That module uses only the
standard library, so it is loaded here by file path without importing the backend app.
Regressions retained from the merged-harness review: trailing newline, JSON -0, depth
64 versus 32, and digit/byte caps.
"""
import importlib.util
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(ROOT)
sys.path.insert(0, ROOT)

from drbean_eval import contract  # noqa: E402

API_CANONICAL = os.path.join(REPO, "apps", "api", "bean_api", "canonical.py")


def api_canonical():
    spec = importlib.util.spec_from_file_location("drbean_api_canonical_under_test", API_CANONICAL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


D256 = "9" * 256
D257 = "9" * 257
RATIONALS = {  # value -> independently expected acceptance
    "1/2": True, "0/1": True, "-1/2": True, "17/100": True,
    "1/2\n": False, "1/2 ": False, " 1/2": False, "1/2\r": False, "-0/1": False, "0/2": False, "2/4": False,
    "+1/2": False, "1/-2": False, "01/2": False, "1/02": False, "1/0": False,
    f"{D256}/1": True, f"-{D256}/1": True, f"1/{D256}": True, f"{D257}/1": False, f"1/{D257}": False,
}
JSON_BYTES = {  # raw wire bytes -> expected acceptance
    b"0": True, b"-0": False, b"[-0]": False, b'{"n":-0}': False, b"-1": False, b"9007199254740991": True,
    b"9007199254740992": False, b"12345678901234567": False, b"0.5": False, b"1e2": False, b"NaN": False,
    b'{"a":1,"a":2}': False, b'"\\ud800"': False, b'"\xff"': False, b"[" * 33 + b"]" * 33: True,
    b"[" * 34 + b"]" * 34: False, b'{"a":' * 32 + b"1" + b"}" * 32: True,
    # 33 nested objects put the scalar leaf at depth 33, past the API's limit of 32.
    b'{"a":' * 33 + b"1" + b"}" * 33: False,
}
DECIMALS = {  # spelling -> expected exact rational (None means rejected)
    "0.10": "1/10", "0.1": "1/10", "-0.0": "0/1", ".5": "1/2", "5.": "5/1", "+5": "5/1", "1e3": "1000/1",
    "1E-3": "1/1000", "1e128": "1" + "0" * 128 + "/1", "1e129": None, "1e-129": None, "1e0001": None,
    "NaN": None, "inf": None, "0x10": None, "1/2": None, "": None, ".": None, " 1": None, "1\n": None,
}


class OracleGoldenBoundaries(unittest.TestCase):
    def test_rational_boundaries(self):
        for value, accepted in RATIONALS.items():
            self.assertEqual(contract.is_canonical_rational(value), accepted, repr(value)[:40])

    def test_json_boundaries(self):
        for raw, accepted in JSON_BYTES.items():
            try:
                contract.parse_strict(raw)
                got = True
            except contract.ContractError:
                got = False
            self.assertEqual(got, accepted, raw[:40])

    def test_json_byte_cap(self):
        big = b'"' + b"a" * (contract.MAX_JSON_BYTES) + b'"'
        with self.assertRaises(contract.ContractError):
            contract.parse_strict(big)

    def test_decimal_boundaries(self):
        for spelling, expected in DECIMALS.items():
            if expected is None:
                with self.assertRaises(contract.ContractError, msg=repr(spelling)):
                    contract.decimal_to_rational(spelling)
            else:
                self.assertEqual(contract.decimal_to_rational(spelling), expected, spelling)


@unittest.skipUnless(os.path.exists(API_CANONICAL), "authoritative canonicalizer not present in this checkout")
class OracleAgreesWithAuthoritativeApi(unittest.TestCase):
    def setUp(self):
        self.api = api_canonical()

    def test_rationals_agree(self):
        for value in RATIONALS:
            try:
                self.api.validate_rational(value)
                api_ok = True
            except ValueError:
                api_ok = False
            self.assertEqual(contract.is_canonical_rational(value), api_ok, repr(value)[:40])

    def test_wire_json_agrees(self):
        for raw in JSON_BYTES:
            try:
                api_value = self.api.parse_json_strict(raw)
                api_ok = True
            except ValueError:
                api_ok = False
            try:
                ours = contract.parse_strict(raw)
                oracle_ok = True
            except contract.ContractError:
                oracle_ok = False
            self.assertEqual(oracle_ok, api_ok, raw[:40])
            if api_ok:
                self.assertEqual(contract.canonical_json(ours), self.api.canonical_bytes(api_value))

    def test_decimals_agree(self):
        for spelling in DECIMALS:
            try:
                api_value = self.api.parse_decimal(spelling)
            except ValueError:
                api_value = None
            try:
                ours = contract.decimal_to_rational(spelling)
            except contract.ContractError:
                ours = None
            self.assertEqual(ours, api_value, repr(spelling))

    def test_identity_agrees(self):
        body = {"rows": [{"time": "1/4", "concentration": "24/5"}], "note": "é "}
        for kind in ("dataset", "problem", "plan", "design-request", "suggestion", "report"):
            self.assertEqual(contract.identity(kind, body), self.api.semantic_digest(kind, body))


if __name__ == "__main__":
    unittest.main()
