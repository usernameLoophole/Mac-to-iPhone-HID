#!/usr/bin/env bash
# One-line installer for Mac-to-iPhone-HID:
#   curl -fsSL https://raw.githubusercontent.com/usernameLoophole/Mac-to-iPhone-HID/main/install.sh | bash
# Re-running it is safe: it updates the clone and skips what's already done.
# Env overrides: INSTALL_DIR (default ~/Mac-to-iPhone-HID), REPO_URL, NONINTERACTIVE=1.
set -euo pipefail

main() {  # everything in a function: a half-downloaded script runs nothing
  REPO_URL="${REPO_URL:-https://github.com/usernameLoophole/Mac-to-iPhone-HID.git}"
  DIR="${INSTALL_DIR:-$HOME/Mac-to-iPhone-HID}"

  say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
  ok()   { printf '\033[1;32m ok\033[0m %s\n' "$*"; }
  die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }
  ask()  {  # ask "question" -> 0 for yes (default yes); reads the terminal even when piped
    [ "${NONINTERACTIVE:-}" = 1 ] && return 1
    { exec 3</dev/tty; } 2>/dev/null || return 1
    printf '%s [Y/n] ' "$1"; read -r a <&3 || a=n; exec 3<&-
    case "$a" in [nN]*) return 1 ;; *) return 0 ;; esac
  }

  [ "$(uname)" = Darwin ] || die "this project runs on macOS."
  export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"  # Homebrew (Apple Silicon / Intel), often missing from PATH

  say "Checking dependencies"
  xcode-select -p >/dev/null 2>&1 || {
    xcode-select --install 2>/dev/null || true
    die "Apple's Command Line Tools (git) are missing. Finish the install window that just opened, then run this again."
  }
  ok "git"

  PY=""
  for c in python3.13 python3.12 python3.11 python3; do
    if command -v "$c" >/dev/null && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
      PY="$(command -v "$c")"; break
    fi
  done
  if [ -z "$PY" ]; then
    command -v brew >/dev/null || die "Python 3.11+ is needed. Install it from https://www.python.org/downloads/ (or Homebrew), then run this again."
    say "Installing Python 3.12 with Homebrew"
    brew install python@3.12
    PY="$(brew --prefix python@3.12)/bin/python3.12"
  fi
  ok "python ($("$PY" --version))"

  if [ -d "$DIR/.git" ]; then
    say "Updating $DIR"
    git -C "$DIR" pull --ff-only
  else
    say "Cloning into $DIR"
    git clone "$REPO_URL" "$DIR"
  fi

  say "Setting up the Python environment (bridge + PlatformIO)"
  [ -x "$DIR/host/.venv/bin/python" ] || "$PY" -m venv "$DIR/host/.venv"
  VPY="$DIR/host/.venv/bin/python"
  "$VPY" -m pip install -q --upgrade pip
  "$VPY" -m pip install -q -r "$DIR/host/requirements.txt" -r "$DIR/firmware/requirements.txt"
  "$VPY" "$DIR/host/bridge.py" --selftest

  PORT="$(ls /dev/cu.usbmodem* 2>/dev/null | head -1 || true)"
  if [ -n "$PORT" ] && ask "Flash the firmware to the ESP32 on $PORT now? (first build downloads ~500 MB of tools)"; then
    "$DIR/host/.venv/bin/pio" run -d "$DIR/firmware" -t upload --upload-port "$PORT"
    ok "firmware flashed"
  else
    [ -n "$PORT" ] || say "No ESP32-S3 found (plug it into the board's USB port)."
    say "Flash the firmware later with:"
    echo "    $DIR/host/.venv/bin/pio run -d $DIR/firmware -t upload"
  fi

  say "Permissions"
  echo "    In System Settings > Privacy & Security, turn on your terminal app under"
  echo "    BOTH 'Input Monitoring' and 'Accessibility', then quit and reopen it."
  if ask "Open those settings pages now?"; then
    open "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"
    open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
  fi

  cat <<EOF

$(ok "Installed in $DIR")

Next:
  1. iPhone: Settings > Bluetooth > tap "Xbox Wireless Controller" (first time only)
  2. Run:     $DIR/start.sh
  3. Toggle:  Ctrl+Opt+Cmd+K sends keyboard + mouse to the iPhone and back
EOF
}

main "$@"
