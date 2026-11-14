"""Elementary arithmetic and literal-byte oracles; no legacy fixture reuse."""

from fractions import Fraction
import unittest

from counterdex.errors import AdapterError
from counterdex.exact import (
    artifact_digest, canonical_bytes, normalize_rational, parse_rational,
    rational_text, semantic_digest, strict_json_loads,
)


class ExactScalarTests(unittest.TestCase):
    def test_equivalent_lexemes_are_exact(self):
        for spelling in ("0.10", ".1", "1e-1", "100E-3", "+01/10", "-1/-10"):
            self.assertEqual(parse_rational(spelling), Fraction(1, 10))
            self.assertEqual(normalize_rational(spelling), "1/10")
        self.assertEqual(normalize_rational("-0.000e+256"), "0/1")
        self.assertEqual(normalize_rational("2."), "2/1")
        self.assertEqual(normalize_rational("2/-4"), "-1/2")

    def test_large_values_do_not_round_through_float(self):
        self.assertEqual(normalize_rational("9007199254740993"), "9007199254740993/1")
        self.assertEqual(parse_rational("1e256"), Fraction(10**256, 1))
        self.assertEqual(parse_rational("1e-256"), Fraction(1, 10**256))
        for value in ("1e256", "1e-256", "0." + "0" * 252 + "1"):
            normalized = normalize_rational(value)
            self.assertEqual(normalize_rational(normalized), normalized)
        normalized = "1/" + "9" * 1022
        self.assertEqual(normalize_rational(normalized), normalized)
        with self.assertRaises(AdapterError):
            parse_rational("1/" + "9" * 1023)

    def test_rejected_input_forms(self):
        for value in (0.1, True, 1, None, Fraction(1, 2), "", " 1", "1 ", "1_000",
                      "1/0", "NaN", "Infinity", "-inf", "1e257", "1e-257", "1e",
                      "1.2/3", "1//2", "1 / 2", "١", "1" * 257):
            with self.subTest(value=type(value).__name__ if not isinstance(value, str) else value[:20]):
                with self.assertRaises(AdapterError) as caught:
                    parse_rational(value, "/future_allowance")
                self.assertEqual(caught.exception.code, "invalid_input")
                self.assertEqual(caught.exception.field_paths, ("/future_allowance",))

    def test_rational_serialization_is_bounded(self):
        self.assertEqual(rational_text(Fraction(0, 9)), "0/1")
        with self.assertRaises(AdapterError):
            rational_text(Fraction(2**4096, 1))
        with self.assertRaises(AdapterError):
            rational_text(2)


class CanonicalJsonTests(unittest.TestCase):
    def test_golden_unicode_and_controls(self):
        value = {"z": "é/😀\u2028\u2029", "a": "\b\f\n\r\t\x00\x1f\"\\", "m": [True, None, 9]}
        expected = ('{"a":"\\b\\f\\n\\r\\t\\u0000\\u001f\\\"\\\\",'
                    '"m":[true,null,9],"z":"é/😀\u2028\u2029"}').encode("utf-8")
        self.assertEqual(canonical_bytes(value), expected)
        self.assertEqual(strict_json_loads(expected), value)
        # Valid escaped surrogate pairs decode to a Unicode scalar, never a pair
        # of surrogate code points in the canonical form.
        self.assertEqual(canonical_bytes(strict_json_loads(b'{"x":"\\ud83d\\ude00"}')),
                         '{"x":"😀"}'.encode("utf-8"))

    def test_unicode_is_not_normalized(self):
        self.assertNotEqual(canonical_bytes({"x": "é"}), canonical_bytes({"x": "e\u0301"}))
        self.assertEqual(canonical_bytes(strict_json_loads(b'{"x":"a\\/b"}')), b'{"x":"a/b"}')

    def test_array_order_is_preserved_and_object_keys_sorted(self):
        self.assertEqual(canonical_bytes({"b": [2, 1], "a": 0}), b'{"a":0,"b":[2,1]}')
        self.assertNotEqual(semantic_digest("problem", {"x": [1, 2]}),
                            semantic_digest("problem", {"x": [2, 1]}))

    def test_semantic_and_artifact_golden_digests(self):
        # SHA-256 standard empty-message vector fixes raw-byte behavior.
        self.assertEqual(artifact_digest(b""),
                         "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
        # Independently obtained from OpenSSL over literal prefix, LF, then {}.
        self.assertEqual(semantic_digest("problem", {}),
                         "299310d1e915641594df8ecc1b60226f258c904e3cfe2367dbffde153f97cb1e")
        self.assertNotEqual(semantic_digest("problem", {}), artifact_digest(b"{}"))
        self.assertNotEqual(semantic_digest("problem", {}), semantic_digest("dataset", {}))
        # Self-hash-looking fields are retained unless a caller's named top-level
        # schema projection excludes them. The helper cannot strip recursively.
        self.assertNotEqual(semantic_digest("report", {"nested": {"digest": "x"}}),
                            semantic_digest("report", {"nested": {}}))

    def test_duplicate_key_detection_happens_before_loss(self):
        for payload in (b'{"a":1,"a":2}', b'{"a":1,"\\u0061":2}',
                        b'{"outer":{"a":1,"a":1}}'):
            with self.assertRaises(AdapterError):
                strict_json_loads(payload)

    def test_invalid_json_and_scalar_types(self):
        for payload in (b'{"x":1.0}', b'{"x":1e0}', b'{"x":-0}', b'{"x":-1}',
                        b'{"x":NaN}', b'{"x":Infinity}', b'{"x":9007199254740992}',
                        b'{"x":100000000000000000000000000000}', b'{"x":"\\ud800"}',
                        b'{"x":"\\udc00"}', b'{"x":"\xff"}', b'{"x":"\x01"}',
                        '{"é":1}'.encode("utf-8"), b'{"":1}', b'{"\\n":1}',
                        b'{"x":}', b'{"x":1} trailing', b'\xef\xbb\xbf{}'):
            with self.subTest(payload=payload):
                with self.assertRaises(AdapterError):
                    strict_json_loads(payload)
        for value in ({"x": 1.0}, {"x": -1}, {"x": float("nan")}, {"x": (1,)},
                      {"x": "\ud800"}, {1: "x"}, {"x": Fraction(1, 2)}):
            with self.assertRaises(AdapterError):
                canonical_bytes(value)
        self.assertEqual(strict_json_loads(b'{"x":9007199254740991}'), {"x": 9007199254740991})

    def test_bounded_parsing_and_canonicalization(self):
        for payload, kwargs in ((b"[]", {"max_bytes": 1}),
                                (b'[[[]]]', {"max_depth": 2}),
                                (b'{"x":[1,2]}', {"max_nodes": 4})):
            with self.assertRaises(AdapterError) as caught:
                strict_json_loads(payload, **kwargs)
            self.assertEqual(caught.exception.code, "resource_exhaustion")
        self.assertEqual(strict_json_loads(b'{"x":[1,2]}', max_nodes=5), {"x": [1, 2]})
        self.assertEqual(strict_json_loads(b'{"x":"[[[[[["}', max_depth=1), {"x": "[[[[[["})
        cyclic = []
        cyclic.append(cyclic)
        with self.assertRaises(AdapterError):
            canonical_bytes(cyclic)
        for kwargs in ({"max_depth": True}, {"max_nodes": 0}, {"max_bytes": 4 * 1024 * 1024 + 1}):
            with self.assertRaises(AdapterError):
                strict_json_loads(b"{}", **kwargs)
        with self.assertRaises(AdapterError):
            canonical_bytes({"x": "x" * (4 * 1024 * 1024)})

    def test_public_error_does_not_echo_input(self):
        with self.assertRaises(AdapterError) as caught:
            parse_rational("private-invalid-value", "/x")
        self.assertNotIn("private-invalid-value", repr(caught.exception.to_dict()))
        self.assertEqual(caught.exception.to_dict()["retryable"], False)


if __name__ == "__main__":
    unittest.main()
