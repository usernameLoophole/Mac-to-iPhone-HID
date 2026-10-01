"""Linux capture: reads /dev/input/event* directly (stdlib only, works on X11 and Wayland).
Needs read access to the input devices: user in the 'input' group."""
import re, select, struct, sys, time

KEYCODES = {  # shared key name -> Linux input event code (linux/input-event-codes.h)
    "esc": 1, "1": 2, "2": 3, "3": 4, "4": 5, "5": 6, "6": 7, "7": 8, "8": 9, "9": 10, "0": 11,
    "-": 12, "=": 13, "delete": 14, "tab": 15, "q": 16, "w": 17, "e": 18, "r": 19, "t": 20,
    "y": 21, "u": 22, "i": 23, "o": 24, "p": 25, "[": 26, "]": 27, "return": 28, "ctrl": 29,
    "a": 30, "s": 31, "d": 32, "f": 33, "g": 34, "h": 35, "j": 36, "k": 37, "l": 38, ";": 39,
    "'": 40, "`": 41, "shift": 42, "\\": 43, "z": 44, "x": 45, "c": 46, "v": 47, "b": 48,
    "n": 49, "m": 50, ",": 51, ".": 52, "/": 53, "rshift": 54, "alt": 56, "space": 57,
    "caps": 58, "f1": 59, "f2": 60, "f3": 61, "f4": 62, "f5": 63, "f6": 64, "f7": 65, "f8": 66,
    "f9": 67, "f10": 68, "f11": 87, "f12": 88, "rctrl": 97, "ralt": 100, "up": 103,
    "left": 105, "right": 106, "down": 108, "meta": 125, "rmeta": 126,
}
NAMES = {code: name for name, code in KEYCODES.items()}
BUTTONS = {272: "left", 273: "right", 274: "middle", 275: "button4", 276: "button5"}
EV_KEY, EV_REL = 1, 2
REL_X, REL_Y, REL_WHEEL = 0, 1, 8
EV_REP_BIT = 1 << 20          # devices with key repeat = real keyboards
EVIOCGRAB = 0x40044590        # _IOW('E', 0x90, int)
EVENT = struct.Struct("llHHi")  # struct input_event: timeval, type, code, value

_devs = {}                    # path -> open file
_want_grab = False
_grabbed = False
_down = set()                 # keys/buttons currently down (grab waits until empty)


def find_devices():
    """eventN paths of keyboards and mice, from /proc/bus/input/devices."""
    with open("/proc/bus/input/devices") as f:
        blocks = f.read().split("\n\n")
    out = []
    for b in blocks:
        h = re.search(r"^H: Handlers=(.*)$", b, re.M)
        ev = re.search(r"^B: EV=([0-9a-f]+)$", b, re.M)
        node = re.search(r"\b(event\d+)\b", h.group(1)) if h else None
        if not (node and ev):
            continue
        handlers = h.group(1).split()
        if "mouse" in [x.rstrip("0123456789") for x in handlers] or (
                "kbd" in handlers and int(ev.group(1), 16) & EV_REP_BIT):
            out.append("/dev/input/" + node.group(1))
    return out


def _set_grab(on):
    import fcntl  # Unix-only: imported here so the tables load on Windows (selftest)
    global _grabbed
    for f in list(_devs.values()):
        try:
            fcntl.ioctl(f, EVIOCGRAB, 1 if on else 0)
        except OSError:
            pass
    _grabbed = on


def grab(on):
    """Grabbing is deferred until no key is held: otherwise the desktop never sees the
    release of the hotkey's keys and treats them as stuck."""
    global _want_grab
    _want_grab = on
    if not on and _grabbed:
        _set_grab(False)


def _rescan():
    import fcntl
    for path in find_devices():
        if path in _devs:
            continue
        try:
            _devs[path] = open(path, "rb", buffering=0)
            if _grabbed:
                fcntl.ioctl(_devs[path], EVIOCGRAB, 1)
        except PermissionError:
            sys.exit(f"No access to {path}: run  sudo usermod -aG input $USER  then log out and back in.")
        except OSError:
            pass


def run(on_event):
    _rescan()
    if not _devs:
        sys.exit("No keyboard or mouse found in /dev/input.")
    last_scan = time.monotonic()
    try:
        while True:
            ready, _, _ = select.select(list(_devs.values()), [], [], 1.0)
            for f in ready:
                try:
                    data = f.read(EVENT.size * 64)
                except OSError:  # device unplugged
                    path = next(p for p, d in _devs.items() if d is f)
                    del _devs[path]
                    f.close()
                    continue
                for i in range(0, len(data) - EVENT.size + 1, EVENT.size):
                    _, _, etype, code, value = EVENT.unpack_from(data, i)
                    if etype == EV_KEY and value in (0, 1):  # 2 = autorepeat
                        (_down.add if value else _down.discard)(code)
                        if code in BUTTONS:
                            on_event("button", BUTTONS[code], bool(value))
                        else:
                            on_event("key", NAMES.get(code), bool(value))
                    elif etype == EV_REL:
                        if code == REL_X:
                            on_event("move", value, 0)
                        elif code == REL_Y:
                            on_event("move", 0, value)
                        elif code == REL_WHEEL:
                            on_event("wheel", (value > 0) - (value < 0))
            if _want_grab and not _grabbed and not _down:
                _set_grab(True)
            if time.monotonic() - last_scan > 2:  # pick up devices plugged in later
                _rescan()
                last_scan = time.monotonic()
    finally:
        _set_grab(False)
