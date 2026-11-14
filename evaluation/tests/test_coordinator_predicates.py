"""Frozen coordinator-sprint predicates (DB-COORDINATOR-3OWNER-1): structure, commitment and baseline coverage.

Standard library only. These are harness self-tests: they prove the predicates are well formed and unedited,
not that any product behaviour exists.
"""
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / "evaluation" / "coordinator"
OBSERVATIONS = ROOT / "evaluation" / "results" / "coordinator"   # evidence-only path: updates keep harness identity
GROUPS = {"scientific", "coordinator_journey", "coordinator_graph", "authority_privacy", "durability", "metering",
          "general_files", "release"}
FIELDS = {"id", "group", "blocking", "behavior_owner", "statement", "observable", "pass", "lanes"}


def load(name):
    return json.loads((FOLDER / name).read_text(encoding="utf-8"))


class FrozenPredicates(unittest.TestCase):
    def setUp(self):
        self.data = load("predicates.v1.json")
        self.frozen = load("FROZEN.json")

    def test_every_predicate_is_complete_and_unique(self):
        ids = [item["id"] for item in self.data["predicates"]]
        self.assertEqual(len(ids), len(set(ids)))
        lanes = set(self.data["lanes"])
        for item in self.data["predicates"]:
            self.assertEqual(set(item), FIELDS, item["id"])
            self.assertIn(item["group"], GROUPS, item["id"])
            self.assertIn(item["behavior_owner"], {"A", "B", "C"}, item["id"])
            self.assertIsInstance(item["blocking"], bool)
            self.assertTrue(item["lanes"] and set(item["lanes"]) <= lanes, item["id"])
            for key in ("statement", "observable", "pass"):
                self.assertTrue(item[key].strip(), item["id"])

    def test_commitment_matches_the_frozen_file(self):
        canonical = json.dumps(self.data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), self.frozen["canonical_sha256"],
                         "predicates.v1.json was edited after freezing; publish predicates.v2.json instead")
        self.assertEqual(self.frozen["predicate_count"], len(self.data["predicates"]))
        self.assertEqual(self.frozen["blocking_count"], sum(item["blocking"] for item in self.data["predicates"]))
        self.assertEqual(self.frozen["frozen_against_main"], self.data["frozen_against"]["main"])

    def test_status_vocabulary_is_the_declared_one(self):
        self.assertEqual(set(self.data["status_vocabulary"]),
                         {"passed", "failed", "not_available", "not_run", "historical_only", "author_check"})

    def test_baseline_observations_cover_every_predicate_with_declared_statuses(self):
        baselines = sorted(OBSERVATIONS.glob("baseline-*.json"))
        if not baselines:
            self.skipTest("no baseline observation recorded yet")
        ids = {item["id"] for item in self.data["predicates"]}
        vocabulary = set(self.data["status_vocabulary"])
        for path in baselines:
            baseline = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(baseline["predicates_canonical_sha256"], self.frozen["canonical_sha256"], path.name)
            observed = {row["id"]: row for row in baseline["observations"]}
            self.assertEqual(set(observed), ids, path.name)
            for row in observed.values():
                self.assertIn(row["status"], vocabulary, f"{path.name}:{row['id']}")
                self.assertTrue(row["basis"].strip(), f"{path.name}:{row['id']}")
                for reference in row.get("evidence", []):
                    self.assertTrue((ROOT / reference.split("::")[0]).exists(), f"{path.name}:{row['id']}: {reference}")


if __name__ == "__main__":
    unittest.main()
