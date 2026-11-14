"""Controlled denied-signal regression, not a native Darwin acceptance test."""
import json

import pytest

from bean_api import science


@pytest.mark.parametrize("alive", [False, True])
def test_genuine_cleanup_denial_remains_visible_and_pipe_handles_close(monkeypatch, alive):
    class Pipe:
        closed = False

        def __init__(self, messages=()):
            self.messages = iter(messages)

        def poll(self, *args):
            return True

        def recv_bytes(self, **kwargs):
            return json.dumps(next(self.messages)).encode()

        def close(self):
            self.closed = True

    receiver = Pipe([{"_worker_control": "session_started"}, {"result": "completed"}])
    sender, lifeline, parent_lifeline = Pipe(), Pipe(), Pipe()

    class Process:
        pid = 12345
        closed = False

        def start(self):
            pass

        def is_alive(self):
            return alive

        def join(self, **kwargs):
            pass

        def close(self):
            assert not alive  # closing a live multiprocessing handle masks the original error
            self.closed = True

    process = Process()

    class Context:
        pipes = iter([(receiver, sender), (lifeline, parent_lifeline)])

        def Pipe(self, **kwargs):
            return next(self.pipes)

        def Process(self, **kwargs):
            return process

    def denied(process):
        assert parent_lifeline.closed  # the guard loses authority even if killpg fails
        raise PermissionError("genuine controlled signal denial")

    monkeypatch.setattr(science.multiprocessing, "get_context", lambda _: Context())
    monkeypatch.setattr(science, "_kill_owned_session", denied)
    with pytest.raises(PermissionError, match="genuine controlled signal denial"):
        science.run_bounded(science.UnavailableAdapter(), "investigate", ({}, {}, {}), wall_seconds=3)
    assert receiver.closed and sender.closed and lifeline.closed and parent_lifeline.closed
    assert process.closed is (not alive)
