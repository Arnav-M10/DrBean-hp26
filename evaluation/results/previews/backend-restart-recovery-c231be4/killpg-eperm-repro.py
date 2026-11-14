"""Darwin: killpg on a session whose only member is an exited, unreaped leader."""
import multiprocessing as mp
import os
import signal
import time


def leader():
    os.setsid()  # own session and process group, as the scientific child does; then exit


def attempt(label, pid):
    try:
        os.killpg(pid, signal.SIGKILL)
        print(f"{label}: no error")
    except PermissionError as e:
        print(f"{label}: PermissionError errno {e.errno}")
    except ProcessLookupError as e:
        print(f"{label}: ProcessLookupError errno {e.errno}")


if __name__ == "__main__":
    ctx = mp.get_context("spawn")
    p = ctx.Process(target=leader)
    p.start()
    time.sleep(1.5)  # leader exited; zombie until joined
    attempt("before join (zombie leader)", p.pid)
    p.join()
    attempt("after join (reaped)", p.pid)
