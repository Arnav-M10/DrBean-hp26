"""The narrow LangChain demo profile is separate from, and can never stand in for, the frozen coordinator predicates.

Standard library only. Harness self-tests: they prove the profile is well formed, frozen and explicitly non-release,
not that any product behaviour exists.
"""
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / "evaluation" / "coordinator"
OBSERVATIONS = ROOT / "evaluation" / "results" / "coordinator"


def load(name):
    return json.loads((FOLDER / name).read_text(encoding="utf-8"))


def canonical(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                          .encode("utf-8")).hexdigest()


class DemoProfile(unittest.TestCase):
    def setUp(self):
        self.profile = load("demo-profile.langchain-narrow-demo.v1.json")
        self.frozen = load("DEMO-FROZEN.json")
        self.predicates = load("predicates.v1.json")
        self.ids = [item["id"] for item in self.predicates["predicates"]]

    def test_profile_is_frozen_and_the_54_predicates_are_untouched(self):
        self.assertEqual(canonical(self.profile), self.frozen["canonical_sha256"],
                         "the demo profile was edited after freezing; publish a new profile version instead")
        self.assertEqual(self.profile["frozen_predicates"]["canonical_sha256"],
                         load("FROZEN.json")["canonical_sha256"])
        self.assertEqual(canonical(self.predicates), load("FROZEN.json")["canonical_sha256"])
        self.assertEqual(len(self.ids), 54)

    def test_profile_never_claims_release_qualification(self):
        self.assertIs(self.profile["release_qualification"], False)
        self.assertIs(self.frozen["release_qualification"], False)
        self.assertIn("never implies full coordinator release qualification", self.profile["statement"])
        self.assertNotEqual(self.profile["profile"], self.predicates.get("assignment"))

    def test_every_predicate_is_either_related_or_explicitly_deferred(self):
        related = {p for claim in self.profile["claims"] for p in claim["related_predicates"]}
        deferred = {item["id"] for item in self.profile["deferred_predicates"]}
        self.assertEqual(related | deferred, set(self.ids))
        self.assertFalse(related & deferred)
        self.assertTrue(all(item["reason"].strip() for item in self.profile["deferred_predicates"]))

    def test_claims_are_the_ten_demo_claims_with_existing_checks(self):
        self.assertEqual([claim["id"] for claim in self.profile["claims"]], [f"DEMO-{n:02d}" for n in range(1, 11)])
        for claim in self.profile["claims"]:
            self.assertTrue(claim["claim"].strip() and claim["pass"].strip(), claim["id"])
            for check in claim["checks"]:
                self.assertTrue((ROOT / check.split("::")[0]).exists(), f"{claim['id']}: {check}")
        self.assertLessEqual(set(self.profile["browser_claims"]), {claim["id"] for claim in self.profile["claims"]})

    def test_demo_observations_are_separate_from_release_baselines(self):
        claims = {claim["id"] for claim in self.profile["claims"]}
        vocabulary = set(self.profile["status_vocabulary"])
        for path in sorted(OBSERVATIONS.glob("demo-*.json")):
            observation = json.loads(path.read_text(encoding="utf-8"))
            self.assertIs(observation["release_qualification"], False, path.name)
            self.assertEqual(observation["profile_canonical_sha256"], self.frozen["canonical_sha256"], path.name)
            self.assertEqual({row["id"] for row in observation["claims"]}, claims, path.name)
            for row in observation["claims"]:
                self.assertIn(row["status"], vocabulary, f"{path.name}:{row['id']}")
            self.assertIn("open_findings", observation, path.name)
        self.assertFalse(any(path.name.startswith("baseline-demo") for path in OBSERVATIONS.glob("*.json")))


if __name__ == "__main__":
    unittest.main()
