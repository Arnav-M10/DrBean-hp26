"""Cooperative bounded execution without numerical or provider dependencies."""
from dataclasses import dataclass, field
import math
import time
from typing import Callable

from .errors import AdapterError


@dataclass
class ExecutionContext:
    """Cooperative budget; the caller remains responsible for hard supervision.

    A context starts its clock once and remembers the first stop. Reusing it
    cannot replenish elapsed time or undo an observed cancellation.
    """

    wall_seconds: float = 120
    cancelled: Callable[[], bool] = lambda: False
    clock: Callable[[], float] = time.monotonic
    _started: float = field(init=False, repr=False)
    _stopped: str | None = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        if type(self.wall_seconds) not in (int, float) or not math.isfinite(self.wall_seconds) or not 0 < self.wall_seconds <= 120:
            raise AdapterError("invalid_input", "Execution wall limit must be positive and at most 120 seconds.", ("context/wall_seconds",))
        if not callable(self.cancelled) or not callable(self.clock):
            raise AdapterError("invalid_input", "Execution callbacks must be callable.", ("context",))
        self._started = self.clock()
        if type(self._started) not in (int, float) or not math.isfinite(self._started):
            raise AdapterError("invalid_input", "Execution clock must return finite monotonic seconds.", ("context/clock",))

    def stop_reason(self, wall_limit: float | None = None) -> str | None:
        if self._stopped is not None:
            return self._stopped
        if self.cancelled():
            self._stopped = "cancelled"
            return self._stopped
        now = self.clock()
        limit = self.wall_seconds if wall_limit is None else min(self.wall_seconds, wall_limit)
        if type(now) not in (int, float) or not math.isfinite(now) or now < self._started or now - self._started >= limit:
            self._stopped = "resource_exhaustion"
        return self._stopped
