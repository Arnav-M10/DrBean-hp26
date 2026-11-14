"""File-backed pytest launcher rejecting Python socket connect/connect_ex.

This observes the test process and Python-spawn imports of this launcher. It is
not a firewall or a claim about arbitrary native/subprocess network operations.
"""
import socket
import sys


def deny_connect(*args, **kwargs):
    raise AssertionError("Offline test attempted socket connect/connect_ex")


socket.socket.connect = deny_connect
socket.socket.connect_ex = deny_connect


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main(sys.argv[1:]))
