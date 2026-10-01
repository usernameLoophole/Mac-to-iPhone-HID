"""Mac keyboard+mouse -> Xbox controller frames over USB serial (see README.md).

Run from Terminal.app (needs Input Monitoring + Accessibility):
    .venv/bin/python bridge.py [port]
Toggle forwarding: Ctrl+Opt+Cmd+K.   Self-test: bridge.py --selftest
"""
import glob, math, os, struct, sys, threading, time, tomllib
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "config.toml")
TICK = 0.008

BUTTONS = {n: 1 << i for i, n in enumerate(
    ["A", "B", "X", "Y", "LB", "RB", "LS", "RS", "View", "Menu", "Guide", "Share"])}
DPAD = {"DU": (0, -1), "DD": (0, 1), "DL": (-1, 0), "DR": (1, 0)}
LSTICK = {"LS_UP": (0, -1), "LS_DOWN": (0, 1), "LS_LEFT": (-1, 0), "LS_RIGHT": (1, 0)}
# (dx, dy) -> HID hat value, y down
HAT = {(0, -1): 1, (1, -1): 2, (1, 0): 3, (1, 1): 4, (0, 1): 5, (-1, 1): 6, (-1, 0): 7, (-1, -1): 8}

KEYCODES = {  # macOS ANSI virtual keycodes
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9, "b": 11,
    "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17, "1": 18, "2": 19, "3": 20, "4": 21,
    "6": 22, "5": 23, "=": 24, "9": 25, "7": 26, "-": 27, "8": 28, "0": 29, "]": 30, "o": 31,
    "u": 32, "[": 33, "i": 34, "p": 35, "return": 36, "l": 37, "j": 38, "'": 39, "k": 40,
    ";": 41, "\\": 42, ",": 43, "/": 44, "n": 45, "m": 46, ".": 47, "tab": 48, "space": 49,
    "`": 50, "delete": 51, "esc": 53, "rcmd": 54, "cmd": 55, "shift": 56, "caps": 57,
    "option": 58, "ctrl": 59, "rshift": 60, "roption": 61, "rctrl": 62,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97, "f7": 98, "f8": 100,
    "f9": 101, "f10": 109, "f11": 103, "f12": 111,
    "left": 123, "right": 124, "down": 125, "up": 126,
}
HOTKEY_CODE = 40  # K


def frame(buttons=0, hat=0, lx=0, ly=0, rx=0, ry=0, lt=0, rt=0):
    p = struct.pack("<HBhhhhBB", buttons, hat, lx, ly, rx, ry, lt, rt)
    x = 0
    for b in p:
        x ^= b
    return b"\xA5" + p + bytes([x])


def stick(vx, vy, mag=1.0):
    """Direction (vx, vy) scaled to magnitude mag (0..1), clipped to the unit circle."""
    n = math.hypot(vx, vy)
    if n == 0:
        return 0, 0
    m = min(1.0, mag) * 32767 / n
    return round(vx * m), round(vy * m)


def aim(dx, dy, window_s, cfg):
    """Mouse counts summed over window -> right stick (README.md, "Mouse → right stick")."""
    vx, vy = dx / window_s, dy / window_s * cfg["y_ratio"]
    m = math.hypot(vx, vy) / cfg["full_speed"]
    if m == 0:
        return 0, 0
    dz = cfg["deadzone"]
    return stick(vx, vy, dz + (1 - dz) * min(1.0, m) ** cfg["gamma"])


def dither(rx, ry, tick):
    """Move a non-centred stick 1 LSB toward centre on odd ticks: iOS/Fortnite
    ignore a right stick that holds perfectly still, so every frame must differ."""
    if not tick:
        return rx, ry
    if rx:
        return rx - (1 if rx > 0 else -1), ry
    if ry:
        return rx, ry - (1 if ry > 0 else -1)
    return rx, ry


def build(targets, mouse_sum, window_s, cfg):
    """Set of held targets + mouse movement -> frame args."""
    btn = 0
    for t in targets:
        btn |= BUTTONS.get(t, 0)
    lx = sum(LSTICK[t][0] for t in targets if t in LSTICK)
    ly = sum(LSTICK[t][1] for t in targets if t in LSTICK)
    hx = max(-1, min(1, sum(DPAD[t][0] for t in targets if t in DPAD)))
    hy = max(-1, min(1, sum(DPAD[t][1] for t in targets if t in DPAD)))
    rx, ry = aim(*mouse_sum, window_s, cfg["aim"])
    return dict(buttons=btn, hat=HAT.get((hx, hy), 0), lx=stick(lx, ly)[0], ly=stick(lx, ly)[1],
                rx=rx, ry=ry, lt=255 if "LT" in targets else 0, rt=255 if "RT" in targets else 0)


TARGETS = set(BUTTONS) | set(DPAD) | set(LSTICK) | {"LT", "RT"}
MOUSE_NAMES = {"left", "right", "middle", "button4", "button5", "wheel_up", "wheel_down"}


def read_config():
    """Load and validate config.toml -> (cfg, {keycode: target}). Raises ValueError on mistakes."""
    with open(CONFIG, "rb") as f:
        cfg = tomllib.load(f)
    for name, t in cfg["keys"].items():
        if name not in KEYCODES:
            raise ValueError(f"[keys] unknown key '{name}'")
        if t not in TARGETS:
            raise ValueError(f"[keys] {name}: unknown target '{t}'")
    for name, t in cfg["mouse"].items():
        if name == "wheel_pulse_ms":
            continue
        if name not in MOUSE_NAMES or t not in TARGETS:
            raise ValueError(f"[mouse] bad entry {name} = '{t}'")
    for k in ("full_speed", "gamma", "deadzone", "window_ms", "y_ratio"):
        if not isinstance(cfg["aim"].get(k), (int, float)) or cfg["aim"][k] <= 0:
            raise ValueError(f"[aim] {k} must be a positive number")
    cfg["mouse"].setdefault("wheel_pulse_ms", 60)
    return cfg, {KEYCODES[k]: v for k, v in cfg["keys"].items()}


def selftest():
    f = frame()
    assert len(f) == 15 and f[0] == 0xA5 and f[-1] == 0
    f = frame(buttons=0x801, lx=-1)
    x = 0
    for b in f[1:-1]:
        x ^= b
    assert x == f[-1]
    cfg = read_config()[0]
    a = build({"LS_UP", "LS_RIGHT"}, (0, 0), 0.02, cfg)  # W+D: diagonal inside the circle
    assert a["lx"] > 0 and a["ly"] < 0 and abs(math.hypot(a["lx"], a["ly"]) - 32767) < 2
    assert build({"LS_UP", "LS_DOWN"}, (0, 0), 0.02, cfg)["ly"] == 0
    assert build({"DU", "DR"}, (0, 0), 0.02, cfg)["hat"] == 2
    assert build({"LT", "A", "Share"}, (0, 0), 0.02, cfg)["buttons"] == 0x801
    ac = cfg["aim"]
    prev = 0
    for c in range(1, 400):  # aim: monotonic, starts at deadzone, caps at full
        r = aim(c, 0, 0.02, ac)[0]
        assert r >= prev and r >= int(ac["deadzone"] * 32767) - 1
        prev = r
    assert prev == 32767 and aim(0, 0, 0.02, ac) == (0, 0) and aim(0, 10, 0.02, ac)[1] > 0
    assert dither(0, 0, 1) == (0, 0) and dither(32767, 5, 1) == (32766, 5)
    assert dither(0, -9, 1) == (0, -8) and dither(100, 0, 0) == (100, 0)
    print("selftest ok")


def main():
    import serial
    import Quartz as Q

    ports = [a for a in sys.argv[1:] if not a.startswith("-")][:1] or glob.glob("/dev/cu.usbmodem*")
    if not ports:
        sys.exit("ESP32 not found: plug it into the board's USB port (or pass the port as an argument).")
    port = ports[0]
    ser = serial.Serial(port)
    lock = threading.Lock()
    # wheel: queued wheel notches, each becomes its own press + release
    st = dict(active=False, keys=set(), mouse=deque(), wheel=deque(maxlen=4), cfg=None, mtime=0)

    def load_cfg():
        m = os.path.getmtime(CONFIG)
        if m == st["mtime"]:
            return
        st["mtime"] = m
        try:
            cfg, keymap = read_config()
        except Exception as e:  # keep the previous config on a typo
            print("config error:", e)
            if st["cfg"] is None:
                sys.exit(1)
            return
        st["cfg"], st["keymap"] = cfg, keymap
        print("config loaded")

    load_cfg()

    def set_active(on):
        st["active"] = on
        st["keys"].clear(); st["mouse"].clear(); st["wheel"].clear()
        Q.CGAssociateMouseAndMouseCursorPosition(not on)
        print("FORWARDING ON" if on else "forwarding off")

    MODS = {56: Q.kCGEventFlagMaskShift, 60: Q.kCGEventFlagMaskShift,
            59: Q.kCGEventFlagMaskControl, 62: Q.kCGEventFlagMaskControl,
            58: Q.kCGEventFlagMaskAlternate, 61: Q.kCGEventFlagMaskAlternate,
            55: Q.kCGEventFlagMaskCommand, 54: Q.kCGEventFlagMaskCommand,
            57: Q.kCGEventFlagMaskAlphaShift}
    HOTKEY = Q.kCGEventFlagMaskControl | Q.kCGEventFlagMaskAlternate | Q.kCGEventFlagMaskCommand
    MOUSE_BTN = {Q.kCGEventLeftMouseDown: ("left", True), Q.kCGEventLeftMouseUp: ("left", False),
                 Q.kCGEventRightMouseDown: ("right", True), Q.kCGEventRightMouseUp: ("right", False)}
    MOVES = {Q.kCGEventMouseMoved, Q.kCGEventLeftMouseDragged,
             Q.kCGEventRightMouseDragged, Q.kCGEventOtherMouseDragged}

    def callback(proxy, etype, ev, refcon):
        if etype in (Q.kCGEventTapDisabledByTimeout, Q.kCGEventTapDisabledByUserInput):
            Q.CGEventTapEnable(tap, True)
            return ev
        with lock:
            if etype == Q.kCGEventKeyDown:
                code = Q.CGEventGetIntegerValueField(ev, Q.kCGKeyboardEventKeycode)
                if code == HOTKEY_CODE and (Q.CGEventGetFlags(ev) & HOTKEY) == HOTKEY:
                    set_active(not st["active"])
                    return None
            if not st["active"]:
                return ev
            cfg = st["cfg"]
            if etype in (Q.kCGEventKeyDown, Q.kCGEventKeyUp, Q.kCGEventFlagsChanged):
                code = Q.CGEventGetIntegerValueField(ev, Q.kCGKeyboardEventKeycode)
                if etype == Q.kCGEventFlagsChanged:
                    down = bool(Q.CGEventGetFlags(ev) & MODS.get(code, 0))
                else:
                    down = etype == Q.kCGEventKeyDown
                t = st["keymap"].get(code)
                if t:
                    (st["keys"].add if down else st["keys"].discard)(("k", code, t))
            elif etype in MOUSE_BTN or etype in (Q.kCGEventOtherMouseDown, Q.kCGEventOtherMouseUp):
                if etype in MOUSE_BTN:
                    name, down = MOUSE_BTN[etype]
                else:
                    n = Q.CGEventGetIntegerValueField(ev, Q.kCGMouseEventButtonNumber)
                    name = "middle" if n == 2 else f"button{n + 1}"
                    down = etype == Q.kCGEventOtherMouseDown
                t = cfg["mouse"].get(name)
                if t:
                    (st["keys"].add if down else st["keys"].discard)(("m", name, t))
            elif etype in MOVES:
                st["mouse"].append((time.monotonic(),
                                    Q.CGEventGetIntegerValueField(ev, Q.kCGMouseEventDeltaX),
                                    Q.CGEventGetIntegerValueField(ev, Q.kCGMouseEventDeltaY)))
            elif etype == Q.kCGEventScrollWheel:
                d = Q.CGEventGetIntegerValueField(ev, Q.kCGScrollWheelEventDeltaAxis1)
                t = cfg["mouse"].get("wheel_up" if d > 0 else "wheel_down") if d else None
                if t:
                    st["wheel"].append(t)
            return None  # swallow everything while forwarding

    mask = 0
    for e in (Q.kCGEventKeyDown, Q.kCGEventKeyUp, Q.kCGEventFlagsChanged, Q.kCGEventMouseMoved,
              Q.kCGEventLeftMouseDown, Q.kCGEventLeftMouseUp, Q.kCGEventRightMouseDown,
              Q.kCGEventRightMouseUp, Q.kCGEventOtherMouseDown, Q.kCGEventOtherMouseUp,
              Q.kCGEventLeftMouseDragged, Q.kCGEventRightMouseDragged,
              Q.kCGEventOtherMouseDragged, Q.kCGEventScrollWheel):
        mask |= Q.CGEventMaskBit(e)
    tap = Q.CGEventTapCreate(Q.kCGSessionEventTap, Q.kCGHeadInsertEventTap,
                             Q.kCGEventTapOptionDefault, mask, callback, None)
    if not tap:
        sys.exit("Event tap failed: grant Input Monitoring + Accessibility to Terminal "
                 "(System Settings > Privacy & Security), then restart Terminal.")

    def sender():
        last_cfg_check = 0
        tick = 0
        pulse = None  # (target, press_until, release_until) of the wheel notch in progress
        while True:
            now = time.monotonic()
            with lock:
                if now - last_cfg_check > 1:
                    load_cfg(); last_cfg_check = now
                if st["active"]:
                    cfg = st["cfg"]
                    w = cfg["aim"]["window_ms"] / 1000
                    m = st["mouse"]
                    while m and m[0][0] < now - w:
                        m.popleft()
                    targets = {k[2] for k in st["keys"]}
                    if pulse and now >= pulse[2]:
                        pulse = None
                    if not pulse and st["wheel"]:
                        d = cfg["mouse"]["wheel_pulse_ms"] / 1000
                        pulse = (st["wheel"].popleft(), now + d, now + 2 * d)
                    if pulse and now < pulse[1]:
                        targets.add(pulse[0])
                    a = build(targets, (sum(e[1] for e in m), sum(e[2] for e in m)), w, cfg)
                    tick ^= 1
                    a["rx"], a["ry"] = dither(a["rx"], a["ry"], tick)
                    f = frame(**a)
                else:
                    pulse = None
                    f = frame()
            try:
                ser.write(f)
            except Exception as e:
                print("serial error:", e)
                Q.CGAssociateMouseAndMouseCursorPosition(True)
                os._exit(1)
            time.sleep(max(0, TICK - (time.monotonic() - now)))

    threading.Thread(target=sender, daemon=True).start()
    src = Q.CFMachPortCreateRunLoopSource(None, tap, 0)
    Q.CFRunLoopAddSource(Q.CFRunLoopGetCurrent(), src, Q.kCFRunLoopCommonModes)
    Q.CGEventTapEnable(tap, True)
    print(f"Ready on {port}. Ctrl+Opt+Cmd+K toggles forwarding. Ctrl+C here to quit.")
    try:
        Q.CFRunLoopRun()
    except KeyboardInterrupt:
        pass
    finally:
        Q.CGAssociateMouseAndMouseCursorPosition(True)
        ser.write(frame())


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main()
