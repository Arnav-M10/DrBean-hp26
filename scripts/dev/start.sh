#!/usr/bin/env bash
# See scripts/dev/launcher.py for what this does and does not do.
exec python3 "$(dirname "$0")/launcher.py" start "$@"
