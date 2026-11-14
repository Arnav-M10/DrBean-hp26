#!/usr/bin/env python3
"""Dr. Bean doctor. See launcher.py. Usage: scripts/dev/doctor.py [--json]"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import launcher  # noqa: E402

sys.exit(launcher.main(["doctor", *sys.argv[1:]]))
