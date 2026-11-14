"""Counterdex scientific adapter. Expensive/producer entry points load lazily."""
from .errors import AdapterError
from .identity import VERSION as __version__
from .models import normalize_design, normalize_problem, normalize_times
from .resource import ExecutionContext


def create_suggestion(*args, **kwargs):
    from .pipeline import create_suggestion as implementation
    return implementation(*args, **kwargs)


def replay_bundle(*args, **kwargs):
    from .replay import replay_bundle as implementation
    return implementation(*args, **kwargs)


def capabilities():
    from .capabilities import capabilities as implementation
    return implementation()


def create_baseline(*args, **kwargs):
    from .baseline import create_baseline as implementation
    return implementation(*args, **kwargs)


def replay_baseline(*args, **kwargs):
    from .replay_baseline import replay_baseline as implementation
    return implementation(*args, **kwargs)


def replay_packet(*args, **kwargs):
    from .native_packet import replay_packet as implementation
    return implementation(*args, **kwargs)


__all__ = ["AdapterError", "ExecutionContext", "normalize_design", "normalize_problem", "normalize_times",
           "create_suggestion", "replay_bundle", "create_baseline", "replay_baseline", "replay_packet", "capabilities"]
