"""Fork segments: a parallel branch's records kept byte for byte, verified from their fork point.

Two branches can append to the same hash-chained history; the merge keeps the integrated chain in
attempts.jsonl and moves the other side's records unchanged into forks/. Nothing is rewritten, so
every tamper the main chain detects must also be detected inside a fork. Synthetic records only.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from drbean_eval import history  # noqa: E402


def chain(records, start):
    """Serialize records as a chain whose first prev is ``start``; returns the encoded lines."""
    lines, previous = [], start
    for record in records:
        line = json.dumps({**record, "prev_record_sha256": previous}, sort_keys=True).encode()
        lines.append(line)
        previous = history.line_digest(line)
    return lines


class HistoryForks(unittest.TestCase):
    def setUp(self):
        self.results = tempfile.mkdtemp(prefix="drbean-forks-")
        self.addCleanup(shutil.rmtree, self.results, ignore_errors=True)
        common = chain([{"attempt_id": f"att_common_{i}", "entry_id": "E"} for i in range(3)], history.GENESIS)
        self.fork_point = history.line_digest(common[-1])
        main = common + chain([{"attempt_id": "att_main_1", "entry_id": "E"}], self.fork_point)
        self.write("attempts.jsonl", main)
        os.makedirs(os.path.join(self.results, "forks"))
        self.fork_lines = chain([{"attempt_id": f"att_fork_{i}", "entry_id": "E"} for i in range(2)], self.fork_point)

    def write(self, name, lines):
        with open(os.path.join(self.results, name), "wb") as handle:
            handle.write(b"\n".join(lines) + b"\n")

    def test_a_fork_from_a_main_line_verifies(self):
        self.write("forks/side.jsonl", self.fork_lines)
        self.assertEqual(history.verify(self.results), [])

    def test_a_fork_that_starts_nowhere_on_the_main_chain_is_refused(self):
        self.write("forks/side.jsonl", chain([{"attempt_id": "att_fork_x", "entry_id": "E"}], "f" * 64))
        self.assertTrue(any("fork segment does not start" in p for p in history.verify(self.results)))

    def test_editing_or_deleting_inside_a_fork_breaks_its_chain(self):
        edited = json.loads(self.fork_lines[0])
        edited["status"] = "passed"
        self.write("forks/side.jsonl", [json.dumps(edited, sort_keys=True).encode(), self.fork_lines[1]])
        self.assertTrue(any("forks/side.jsonl" in p and "chain break" in p for p in history.verify(self.results)))
        self.write("forks/side.jsonl", self.fork_lines[1:])  # first line deleted: no longer starts on main
        self.assertTrue(history.verify(self.results))

    def test_unchained_records_and_duplicate_ids_are_refused(self):
        unchained = json.dumps({"attempt_id": "att_fork_u", "entry_id": "E"}).encode()
        self.write("forks/side.jsonl", [self.fork_lines[0], unchained])
        self.assertTrue(any("unchained record" in p for p in history.verify(self.results)))
        self.write("forks/side.jsonl", chain([{"attempt_id": "att_main_1", "entry_id": "E"}], self.fork_point))
        self.assertTrue(any("duplicate attempt_id att_main_1" in p for p in history.verify(self.results)))

    def test_fork_traces_are_digest_checked(self):
        os.makedirs(os.path.join(self.results, "traces"))
        with open(os.path.join(self.results, "traces", "t.json"), "w", encoding="utf-8") as handle:
            handle.write("{}")
        record = {"attempt_id": "att_fork_t", "entry_id": "E", "trace": "traces/t.json",
                  "trace_sha256": history.file_digest(os.path.join(self.results, "traces", "t.json"))}
        self.write("forks/side.jsonl", chain([record], self.fork_point))
        self.assertEqual(history.verify(self.results), [])
        with open(os.path.join(self.results, "traces", "t.json"), "a", encoding="utf-8") as handle:
            handle.write(" ")
        self.assertTrue(any("forks/side.jsonl" in p and "changed" in p for p in history.verify(self.results)))

    def test_the_repository_fork_is_exactly_this_branchs_divergent_records(self):
        fork = os.path.join(ROOT, "results", "forks", "claude-adversarial-validation-1ae19ff-d6503da.jsonl")
        with open(fork, "rb") as handle:
            records = [json.loads(line) for line in handle if line.strip()]
        self.assertEqual(len(records), 14)
        self.assertEqual({r["tested_commit"][:7] for r in records}, {"1ae19ff", "d6503da"})
        self.assertEqual(history.verify(os.path.join(ROOT, "results")), [])


if __name__ == "__main__":
    unittest.main()
