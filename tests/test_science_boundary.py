import multiprocessing
import time

from bean_api.science import UnavailableAdapter, run_bounded


class SlowAdapter:
    def investigate(self, *args):
        time.sleep(10)
        return {"should_not_arrive": True}


def test_unconfigured_science_has_no_checked_capability():
    adapter = UnavailableAdapter()
    assert adapter.capabilities()["implemented"] is False
    result = run_bounded(adapter, "investigate", ({"id": "problem"}, {}, {}), wall_seconds=3)
    assert result["scientific_outcome"] == "unsupported"
    assert result["verification"] == "unsupported"


def test_wall_limit_terminates_owned_process():
    before = {child.pid for child in multiprocessing.active_children()}
    started = time.monotonic()
    result = run_bounded(SlowAdapter(), "investigate", ({}, {}, {}), wall_seconds=1)
    assert result == {"worker_error": "scientific_wall_limit"}
    assert time.monotonic() - started < 4
    assert {child.pid for child in multiprocessing.active_children()} == before


def test_cancel_is_acknowledged_after_process_termination():
    before = {child.pid for child in multiprocessing.active_children()}
    result = run_bounded(SlowAdapter(), "investigate", ({}, {}, {}), wall_seconds=5, cancelled=lambda: True)
    assert result == {"worker_error": "cancelled"}
    assert {child.pid for child in multiprocessing.active_children()} == before
