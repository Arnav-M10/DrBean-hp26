"""The design request follows the current (v2) contract, and the published capability gates the reuse probe.

v2 (``capabilities.science.native_design``): the server resolves mandatory baseline history and
prospective reuse is unsupported, so ``source_artifact_ids`` is always empty; the design-authority
scenario separately checks a nonempty reuse request never yields a checked design. Nothing is launched.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from drbean_eval import science_flow as sf  # noqa: E402

PAIR = [{"id": "c-out", "parameter_vector": {"A": "1/1", "ke": "1/20", "ka": "2/1"}, "artifact_ids": ["art_base"]},
        {"id": "c-in", "parameter_vector": {"A": "1/1", "ke": "1/8", "ka": "2/1"}, "artifact_ids": ["art_base"]}]
REVIEW = {"feasible_times": ["6/1", "8/1"], "future_hard_allowance": "1/5", "maximum_horizon": "8/1",
          "allow_construction": True, "allow_continuation": True, "allowance_origin": "hypothetical",
          "allowance_description": "Reviewed future hard allowance"}


def flow(capabilities):
    built = sf.Flow.__new__(sf.Flow)
    built._openapi = {"components": {"schemas": {"DesignRequestBody": {
        "properties": {name: {} for name in ("scientific_profile", "requested_tier", "allowance_origin",
                                             "maximum_horizon", "source_artifact_ids")}}}}}
    built._capabilities = capabilities
    return built


class DesignContract(unittest.TestCase):
    def request(self, capabilities):
        return flow(capabilities).design_request({"id": "run_1"}, {"id": "prob_1", "digest": "d" * 64}, PAIR, REVIEW)

    def test_v2_native_design_sends_no_reuse(self):
        self.assertEqual(self.request({"science": {"native_design": True}})["source_artifact_ids"], [])

    def test_reuse_stays_empty_whatever_the_capabilities_say(self):
        for caps in ({"science": {}}, {"science": {"native_design": False}}, {}):
            self.assertEqual(self.request(caps)["source_artifact_ids"], [], caps)

    def test_everything_else_is_identical_across_contracts(self):
        v2, v1 = self.request({"science": {"native_design": True}}), self.request({})
        self.assertEqual({k: v for k, v in v2.items() if k != "source_artifact_ids"},
                         {k: v for k, v in v1.items() if k != "source_artifact_ids"})

    def test_only_an_explicit_true_selects_v2(self):
        for value in ("true", 1, None, {"available": True}):
            self.assertFalse(flow({"science": {"native_design": value}}).native_design_contract(), value)


if __name__ == "__main__":
    unittest.main()
