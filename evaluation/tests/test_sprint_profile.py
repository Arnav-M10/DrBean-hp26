"""The sprint checklist is frozen; observations must name its commitment."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


class SprintProfileTests(unittest.TestCase):
    def setUp(self):
        self.profile = json.loads((ROOT / "coordinator" / "sprint-completion.v1.json").read_text(encoding="utf-8"))
        self.frozen = json.loads((ROOT / "coordinator" / "SPRINT-FROZEN.json").read_text(encoding="utf-8"))

    def test_profile_matches_its_commitment(self):
        self.assertEqual(canonical(self.profile), self.frozen["canonical_sha256"],
                         "Edit sprint-completion.v1.json only through a new version with its own commitment.")

    def test_observations_use_only_frozen_items_and_statuses(self):
        ids = {item["id"] for item in self.profile["items"]}
        for path in sorted((ROOT / "results" / "sprint").glob("*.json")):
            observation = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(observation["profile_canonical_sha256"], self.frozen["canonical_sha256"], path.name)
            for item in observation["items"]:
                self.assertIn(item["id"], ids, path.name)
                self.assertIn(item["status"], self.profile["status_vocabulary"], path.name)
                if item["status"] == "PASS":
                    self.assertTrue(item.get("evidence"), f"{path.name} {item['id']}: a PASS needs evidence")
                if item["id"].startswith("LIVE") and item["status"] == "PASS":
                    self.assertGreater(observation["live"]["physical_requests"], 0, path.name)
            if "live" in observation:
                self.assertLessEqual(observation["live"]["sprint_physical_requests_total"], 12, path.name)


if __name__ == "__main__":
    unittest.main()
