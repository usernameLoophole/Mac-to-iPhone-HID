#!/usr/bin/env bash
# Start the bridge. Run from Terminal.app (needs Input Monitoring + Accessibility).
exec "$(dirname "$0")/host/.venv/bin/python" "$(dirname "$0")/host/bridge.py" "$@"
