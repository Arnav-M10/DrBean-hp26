"""Dr. Bean evaluation egress guard. Loaded only into processes the harness launches.

Put this directory first on PYTHONPATH and set DRBEAN_EGRESS_GUARD_LOG to a file.
Python then imports it at startup (site.py), in the API, the worker and every
spawned scientific child that inherits that environment.

What it does, and nothing else:

* Installs an audit hook that refuses DNS lookups and socket connections to any
  non-loopback address, and records each refusal. Local HTTP between the harness,
  API and worker keeps working; AF_UNIX sockets and socket pairs are untouched.
* Wraps ``google.genai.client.Client.__init__`` after that module loads, so that
  constructing a network-capable Gemini client is recorded and refused. Importing
  the SDK, its types and schemas stays allowed. LangChain's Gemini chat model
  builds this same client, so it is covered too.
* Records which provider-credential variable *names* are present at startup. It
  never reads, logs or transmits a value.

Every event is one JSON line: {"pid", "kind", ...}. The harness treats any
``egress_blocked`` or ``provider_client_blocked`` event as an external-model
attempt (a P0 finding), even though the guard prevented any packet or charge.
"""
from __future__ import annotations

import ipaddress
import json
import os
import sys
import time
import traceback

_LOG: str | None = None
_CREDENTIAL_NAMES = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_GENAI_API_KEY",
                     "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "LANGSMITH_API_KEY", "LANGCHAIN_API_KEY")
_LOOPBACK_NAMES = {"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"}


def _record(kind: str, **fields) -> None:
    if not _LOG:
        return
    stack = [f"{frame.filename.rsplit('/', 2)[-1]}:{frame.lineno}:{frame.name}"
             for frame in traceback.extract_stack()[-12:-2]]
    event = {"pid": os.getpid(), "ppid": os.getppid(), "at": time.time(), "kind": kind,
             "argv0": (sys.argv[0] if sys.argv else "")[-80:], "stack": stack, **fields}
    try:
        with open(_LOG, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True, default=str) + "\n")
    except OSError:
        pass


def _loopback(host) -> bool:
    if host is None:
        return True  # getaddrinfo(None, port) resolves the local wildcard
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    host = str(host).strip("[]").split("%", 1)[0].lower()
    if host in _LOOPBACK_NAMES or host == "":
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or address.is_unspecified


def _address_host(address):
    if isinstance(address, tuple) and address:
        return address[0]
    return None  # AF_UNIX path or abstract address: local by construction


class EgressDenied(ConnectionRefusedError):
    pass


def _audit(event: str, args) -> None:
    if event == "socket.getaddrinfo" or event == "socket.gethostbyname" or event == "socket.gethostbyaddr":
        host = args[0] if args else None
        if not _loopback(host):
            _record("egress_blocked", event=event, host=str(host)[:200])
            raise EgressDenied(f"drbean egress guard: external lookup of {str(host)[:80]!r} denied")
    elif event in ("socket.connect", "socket.sendto", "socket.sendmsg"):
        address = args[1] if len(args) > 1 else None
        host = _address_host(address)
        if host is not None and not _loopback(host):
            _record("egress_blocked", event=event, host=str(host)[:200],
                    port=address[1] if isinstance(address, tuple) and len(address) > 1 else None)
            raise EgressDenied(f"drbean egress guard: external connection to {str(host)[:80]!r} denied")


def _wrap_client(module) -> None:
    client = getattr(module, "Client", None)
    if client is None or getattr(client.__init__, "_drbean_guarded", False):
        return
    original = client.__init__

    def guarded_init(self, *args, **kwargs):
        _record("provider_client_blocked", client="google.genai.Client",
                vertexai=bool(kwargs.get("vertexai")), api_key_supplied=kwargs.get("api_key") is not None)
        raise RuntimeError("drbean egress guard: constructing a network-capable Gemini client is denied "
                           "in the offline placeholder lane")

    guarded_init._drbean_guarded = True  # type: ignore[attr-defined]
    guarded_init._drbean_original = original  # type: ignore[attr-defined]
    client.__init__ = guarded_init


def _relax_nproc(module) -> None:
    """DIAGNOSTIC ONLY (opt-in): lift the per-user RLIMIT_NPROC cap that blocks spawning on macOS (F-MAC-NPROC).

    Never active unless DRBEAN_DIAGNOSTIC_OVERRIDES contains relax_nproc. Every other guard stays as configured.
    Runs recorded with it are diagnostic evidence about downstream behaviour, never acceptance.
    """
    original = getattr(module, "apply_limits", None)
    if original is None or getattr(original, "_drbean_relaxed", False):
        return

    def relaxed(**kwargs):
        kwargs["processes"] = 1_000_000  # apply_limits caps this at the inherited hard limit
        _record("diagnostic_override_applied", override="relax_nproc", module=module.__name__)
        return original(**kwargs)

    relaxed._drbean_relaxed = True  # type: ignore[attr-defined]
    module.apply_limits = relaxed


def _science_barrier(module) -> None:
    """DIAGNOSTIC ONLY (opt-in): deterministic barrier inside the scientific child, after setsid and limits.

    Wraps CounterdexAdapter.investigate/design so a spawned child waits while the harness-owned barrier file
    exists (at most 120 s). The path is captured at import because the child clears its environment before it
    calls the adapter. Cancellation and kill handling under test remain the product's own code.
    """
    barrier = os.environ.get("DRBEAN_DIAGNOSTIC_BARRIER")
    adapter = getattr(module, "CounterdexAdapter", None)
    if not barrier or adapter is None or getattr(adapter, "_drbean_barrier", False):
        return

    def hold(method):
        def wrapped(self, *args, **kwargs):
            started = time.time()
            if os.path.exists(barrier):
                _record("diagnostic_barrier_wait", method=method.__name__)
                while os.path.exists(barrier) and time.time() - started < 120:
                    time.sleep(0.05)
                _record("diagnostic_barrier_released", method=method.__name__, waited=round(time.time() - started, 3))
            return method(self, *args, **kwargs)
        wrapped.__name__ = method.__name__
        return wrapped

    for name in ("investigate", "design"):
        if hasattr(adapter, name):
            setattr(adapter, name, hold(getattr(adapter, name)))
    adapter._drbean_barrier = True


class _WrapAfterImport:
    """Meta-path finder that patches google.genai.client once Python finishes loading it."""
    targets = {"google.genai.client": _wrap_client}

    def find_spec(self, name, path=None, target=None):
        if name not in self.targets:
            return None
        for finder in sys.meta_path:
            if finder is self or not hasattr(finder, "find_spec"):
                continue
            spec = finder.find_spec(name, path, target)
            if spec is not None and spec.loader is not None and hasattr(spec.loader, "exec_module"):
                loader, patch = spec.loader, self.targets[name]

                class _Loader:
                    def create_module(self, spec):
                        return loader.create_module(spec) if hasattr(loader, "create_module") else None

                    def exec_module(self, module):
                        loader.exec_module(module)
                        patch(module)

                spec.loader = _Loader()
                return spec
        return None


def _watch_credential_reads() -> None:
    """Record when a process reads a provider-credential variable that is present. Name only, never the value.

    Covers os.environ[...] and os.getenv/os.environ.get in this interpreter. It cannot see native code that calls
    getenv(3) directly; the launcher's allowlisted environment is the primary control.
    """
    environ_type = type(os.environ)
    if getattr(environ_type.__getitem__, "_drbean_watched", False):
        return
    original = environ_type.__getitem__

    def watched(self, key):
        value = original(self, key)
        if key in _CREDENTIAL_NAMES:
            _record("credential_read", name=key)
        return value

    watched._drbean_watched = True  # type: ignore[attr-defined]
    environ_type.__getitem__ = watched


def install(log_path: str | None) -> bool:
    """Install once per interpreter. Returns True when this call installed the guard."""
    global _LOG
    if not log_path or getattr(sys, "_drbean_guard_installed", False):
        return False
    _LOG = log_path
    sys._drbean_guard_installed = True  # type: ignore[attr-defined]
    present = sorted(name for name in _CREDENTIAL_NAMES if os.environ.get(name) is not None)
    _record("guard_installed", python=sys.version.split()[0], credential_names_present=present)
    sys.addaudithook(_audit)
    _watch_credential_reads()
    overrides = set(filter(None, os.environ.get("DRBEAN_DIAGNOSTIC_OVERRIDES", "").split(",")))
    if "relax_nproc" in overrides:
        _WrapAfterImport.targets = {**_WrapAfterImport.targets, "bean_api.science": _relax_nproc}
        _record("diagnostic_override_enabled", override="relax_nproc")
    if "science_barrier" in overrides:
        _WrapAfterImport.targets = {**_WrapAfterImport.targets, "bean_api.counterdex_adapter": _science_barrier}
        _record("diagnostic_override_enabled", override="science_barrier")
    sys.meta_path.insert(0, _WrapAfterImport())
    if "google.genai.client" in sys.modules:
        _wrap_client(sys.modules["google.genai.client"])
    return True


install(os.environ.get("DRBEAN_EGRESS_GUARD_LOG"))
