"""Fixed parser-worker parent lifeline, installed before decoding untrusted bytes."""
import os
import signal
import sys
import threading


def install():
    if len(sys.argv) != 3 or sys.argv[1] != "--lifeline-fd":
        raise ValueError("A server-owned parser lifeline is required")
    descriptor = int(sys.argv[2])
    if descriptor < 3:
        raise ValueError("Invalid parser lifeline")
    os.set_inheritable(descriptor, False)

    def watch():
        try:
            while os.read(descriptor, 1):
                pass
        finally:
            os.close(descriptor)
            # EOF includes parent SIGKILL, interpreter crash and explicit
            # cancellation. The fixed worker owns this freshly created session.
            os.killpg(os.getpid(), signal.SIGKILL)

    threading.Thread(target=watch, daemon=True, name="parser-parent-lifeline").start()
