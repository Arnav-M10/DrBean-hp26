"""Every finding id a check can print is documented: an observed finding or a catalog entry.

A failing check names a finding id so a reader of CI output can find its meaning and owner in
evaluation/FINDINGS.md. This test keeps that promise for the harness and the integration suite.
"""
import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(ROOT)
CITED = re.compile(r"\b[FH]-[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*\b")
SOURCES = (os.path.join(ROOT, "drbean_eval"), os.path.join(ROOT, "cli.py"), os.path.join(REPO, "tests", "integration"))


def cited_ids() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for source in SOURCES:
        paths = [source] if os.path.isfile(source) else [
            os.path.join(folder, name) for folder, _, names in os.walk(source) for name in names if name.endswith(".py")]
        for path in paths:
            with open(path, encoding="utf-8") as handle:
                for number, line in enumerate(handle, 1):
                    for match in CITED.findall(line):
                        found.setdefault(match, []).append(f"{os.path.relpath(path, REPO)}:{number}")
    return found


class FindingIdsAreDocumented(unittest.TestCase):
    def test_every_cited_id_is_a_finding_or_catalogued(self):
        with open(os.path.join(ROOT, "findings.json"), encoding="utf-8") as handle:
            data = json.load(handle)
        known = {f["id"] for f in data["findings"]} | set((data.get("check_catalog") or {}).get("ids", {}))
        cited = cited_ids()
        self.assertTrue(cited, "no finding ids found; the scan is broken")
        missing = {key: where[:3] for key, where in cited.items() if key not in known}
        self.assertEqual(missing, {}, "cite only ids recorded in evaluation/findings.json (findings or check_catalog)")

    def test_catalog_does_not_shadow_an_observed_finding(self):
        with open(os.path.join(ROOT, "findings.json"), encoding="utf-8") as handle:
            data = json.load(handle)
        both = {f["id"] for f in data["findings"]} & set((data.get("check_catalog") or {}).get("ids", {}))
        self.assertEqual(both, set(), "an observed finding must not also be listed as merely potential")


if __name__ == "__main__":
    unittest.main()
