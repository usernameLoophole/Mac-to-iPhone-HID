#!/usr/bin/env bash
# One-line installer for Mac-to-iPhone-HID (macOS and Linux; Windows: install.ps1):
#   curl -fsSL https://raw.githubusercontent.com/usernameLoophole/Mac-to-iPhone-HID/main/install.sh | bash
# Re-running it is safe: it updates the clone and skips what's already done.
# Env overrides: INSTALL_DIR (default ~/Mac-to-iPhone-HID), REPO_URL, BRANCH, NONINTERACTIVE=1.
set -euo pipefail

main() {  # everything in a function: a half-downloaded script runs nothing
  REPO_URL="${REPO_URL:-https://github.com/usernameLoophole/Mac-to-iPhone-HID.git}"
  DIR="${INSTALL_DIR:-$HOME/Mac-to-iPhone-HID}"
  OS="$(uname)"
  RELOGIN=""

  say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
  ok()   { printf '\033[1;32m ok\033[0m %s\n' "$*"; }
  die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }
  ask()  {  # ask "question" -> 0 for yes (default yes); reads the terminal even when piped
    [ "${NONINTERACTIVE:-}" = 1 ] && return 1
    { exec 3</dev/tty; } 2>/dev/null || return 1
    printf '%s [Y/n] ' "$1"; read -r a <&3 || a=n; exec 3<&-
    case "$a" in [nN]*) return 1 ;; *) return 0 ;; esac
  }
  find_python() {  # first Python >= 3.11 with venv support
    for c in python3.13 python3.12 python3.11 python3; do
      if command -v "$c" >/dev/null &&
         "$c" -c 'import sys, venv, ensurepip; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
        command -v "$c"; return
      fi
    done
  }
  pkg_install() {  # Linux: install packages with whatever package manager is there
    if command -v apt-get >/dev/null; then sudo apt-get update -qq && sudo apt-get install -y -qq "$@"
    elif command -v dnf >/dev/null; then sudo dnf install -y -q "$@"
    elif command -v pacman >/dev/null; then sudo pacman -S --needed --noconfirm "$@"
    elif command -v zypper >/dev/null; then sudo zypper -q install -y "$@"
    else die "unknown package manager: install $* yourself, then run this again."
    fi
  }

  say "Checking dependencies"
  case "$OS" in
    Darwin)
      export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"  # Homebrew, often missing from PATH
      xcode-select -p >/dev/null 2>&1 || {
        xcode-select --install 2>/dev/null || true
        die "Apple's Command Line Tools (git) are missing. Finish the install window that just opened, then run this again."
      } ;;
    Linux)
      command -v git >/dev/null || pkg_install git ;;
    *) die "unsupported system: $OS (use install.ps1 on Windows)." ;;
  esac
  ok "git"

  PY="$(find_python)"
  if [ -z "$PY" ]; then
    say "Installing Python 3.11+"
    if [ "$OS" = Darwin ]; then
      command -v brew >/dev/null || die "Python 3.11+ is needed. Install it from https://www.python.org/downloads/ (or Homebrew), then run this again."
      brew install python@3.12
    elif command -v apt-get >/dev/null; then
      pkg_install python3 python3-venv
      [ -n "$(find_python)" ] || pkg_install python3.11 python3.11-venv  # older Ubuntu/Debian
    elif command -v pacman >/dev/null; then pkg_install python
    elif command -v zypper >/dev/null; then pkg_install python311
    else pkg_install python3
    fi
    PY="$(find_python)"
    [ -n "$PY" ] || die "could not install Python 3.11+. Install it yourself, then run this again."
  fi
  ok "python ($("$PY" --version))"

  if [ -d "$DIR/.git" ]; then
    say "Updating $DIR"
    git -C "$DIR" pull --ff-only
  else
    say "Cloning into $DIR"
    git clone ${BRANCH:+-b "$BRANCH"} "$REPO_URL" "$DIR"
  fi

  say "Setting up the Python environment (bridge + PlatformIO)"
  [ -x "$DIR/host/.venv/bin/python" ] || "$PY" -m venv "$DIR/host/.venv"
  VPY="$DIR/host/.venv/bin/python"
  "$VPY" -m pip install -q --upgrade pip
  "$VPY" -m pip install -q -r "$DIR/host/requirements.txt" -r "$DIR/firmware/requirements.txt"
  "$VPY" "$DIR/host/bridge.py" --selftest

  if [ "$OS" = Linux ]; then
    say "Permissions (read keyboard/mouse, use the serial port)"
    SERIAL_GROUP="$(getent group dialout >/dev/null && echo dialout || echo uucp)"
    for g in input "$SERIAL_GROUP"; do
      if id -nG | tr ' ' '\n' | grep -qx "$g"; then
        ok "in group $g"
      else
        sudo usermod -aG "$g" "$USER" && RELOGIN=1 && ok "added to group $g"
      fi
    done
  fi

  PORT="$("$VPY" -c 'from serial.tools import list_ports as l; print(next((p.device for p in l.comports() if p.vid == 0x303A), ""))')"
  if [ -n "$PORT" ] && [ -z "$RELOGIN" ] &&
     ask "Flash the firmware to the ESP32 on $PORT now? (first build downloads ~500 MB of tools)"; then
    "$DIR/host/.venv/bin/pio" run -d "$DIR/firmware" -t upload --upload-port "$PORT"
    ok "firmware flashed"
  else
    [ -n "$PORT" ] || say "No ESP32-S3 found (plug it into the board's USB port)."
    say "Flash the firmware later with:"
    echo "    $DIR/host/.venv/bin/pio run -d $DIR/firmware -t upload"
  fi

  if [ "$OS" = Darwin ]; then
    say "Permissions"
    echo "    In System Settings > Privacy & Security, turn on your terminal app under"
    echo "    BOTH 'Input Monitoring' and 'Accessibility', then quit and reopen it."
    if ask "Open those settings pages now?"; then
      open "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"
      open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
    fi
    HOTKEY="Ctrl+Opt+Cmd+K"
  else
    HOTKEY="Ctrl+Alt+Super+K"
  fi

  echo
  ok "Installed in $DIR"
  [ -z "$RELOGIN" ] || say "Log out and back in first (new group membership), then flash and run."
  cat <<EOF

Next:
  1. iPhone: Settings > Bluetooth > tap "Xbox Wireless Controller" (first time only)
  2. Run:     $DIR/start.sh
  3. Toggle:  $HOTKEY sends keyboard + mouse to the iPhone and back
EOF
}

main "$@"
