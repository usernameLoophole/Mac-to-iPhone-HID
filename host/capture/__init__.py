"""Keyboard/mouse capture backends, one per OS.

Each backend module provides:
  KEYCODES            {shared key name: OS key code}, names from bridge.KEY_NAMES
  run(on_event)       blocking loop. Calls on_event(kind, *args) and swallows the
                      event if it returns True. kind is one of:
                        "key", name|None, down     "button", name, down
                        "move", dx, dy             "wheel", +1|-1|0
  grab(on)            hide input from the OS and freeze the cursor while forwarding
"""
import sys


def load():
    if sys.platform == "darwin":
        from . import macos as backend
    else:
        sys.exit(f"{sys.platform} is not supported yet (macOS only for now).")
    return backend
