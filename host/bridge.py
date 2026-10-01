"""Keyboard+mouse -> Xbox controller frames over USB serial (see README.md).

    .venv/bin/python bridge.py [port]        start (toggle with the hotkey from config.toml)
    .venv/bin/python bridge.py --selftest    check the logic, no hardware needed
The OS-specific capture code lives in capture/.
"""
import math, os, struct, sys, threading, time, tomllib
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "config.toml")
TICK = 0.008
ESPRESSIF_VID = 0x303A  # ESP32-S3 native USB

BUTTONS = {n: 1 << i for i, n in enumerate(
    ["A", "B", "X", "Y", "LB", "RB", "LS", "RS", "View", "Menu", "Guide", "Share"])}
DPAD = {"DU": (0, -1), "DD": (0, 1), "DL": (-1, 0), "DR": (1, 0)}
LSTICK = {"LS_UP": (0, -1), "LS_DOWN": (0, 1), "LS_LEFT": (-1, 0), "LS_RIGHT": (1, 0)}
# (dx, dy) -> HID hat value, y down
HAT = {(0, -1): 1, (1, -1): 2, (1, 0): 3, (1, 1): 4, (0, 1): 5, (-1, 1): 6, (-1, 0): 7, (-1, -1): 8}
TARGETS = set(BUTTONS) | set(DPAD) | set(LSTICK) | {"LT", "RT"}
MOUSE_NAMES = {"left", "right", "middle", "button4", "button5", "wheel_up", "wheel_down"}

# Key names shared by config.toml and every capture backend (meta = Cmd / Win / Super)
KEY_NAMES = set("abcdefghijklmnopqrstuvwxyz0123456789") | set("`-=[]\\;',./") | {
    "return", "tab", "space", "delete", "esc", "caps", "left", "right", "up", "down",
    "shift", "rshift", "ctrl", "rctrl", "alt", "ralt", "meta", "rmeta",
    *(f"f{i}" for i in range(1, 13))}
MOD_GROUPS = {"ctrl": {"ctrl", "rctrl"}, "alt": {"alt", "ralt"},
              "meta": {"meta", "rmeta"}, "shift": {"shift", "rshift"}}
DEFAULT_HOTKEY = "ctrl+alt+shift+k" if sys.platform == "win32" else "ctrl+alt+meta+k"


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


def parse_hotkey(s):
    """"ctrl+alt+meta+k" -> ([modifier groups], "k"). Raises ValueError."""
    *mods, key = s.lower().split("+")
    if key not in KEY_NAMES or any(m not in MOD_GROUPS for m in mods):
        raise ValueError(f"hotkey '{s}': use modifiers {'/'.join(MOD_GROUPS)} + one key")
    return [MOD_GROUPS[m] for m in mods], key


def is_hotkey(name, held, hotkey):
    """Key `name` just went down while `held` keys are down: is it the hotkey?"""
    mods, key = hotkey
    return name == key and all(g & held for g in mods)


def read_config():
    """Load and validate config.toml. Raises ValueError on mistakes."""
    with open(CONFIG, "rb") as f:
        cfg = tomllib.load(f)
    for name, t in cfg["keys"].items():
        if name not in KEY_NAMES:
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
    cfg.setdefault("hotkey", DEFAULT_HOTKEY)
    cfg["_hotkey"] = parse_hotkey(cfg["hotkey"])
    return cfg


def find_port():
    """Serial port of the ESP32-S3 (by USB vendor ID), or the first non-option CLI argument."""
    from serial.tools import list_ports
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    ports = args[:1] or [p.device for p in list_ports.comports() if p.vid == ESPRESSIF_VID]
    if not ports:
        sys.exit("ESP32 not found: plug it into the board's USB port (or pass the port as an argument).")
    return ports[0]


def selftest():
    f = frame()
    assert len(f) == 15 and f[0] == 0xA5 and f[-1] == 0
    f = frame(buttons=0x801, lx=-1)
    x = 0
    for b in f[1:-1]:
        x ^= b
    assert x == f[-1]
    cfg = read_config()
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
    hk = parse_hotkey("ctrl+alt+meta+k")
    assert is_hotkey("k", {"rctrl", "alt", "meta"}, hk) and not is_hotkey("k", {"ctrl", "alt"}, hk)
    assert not is_hotkey("j", {"ctrl", "alt", "meta"}, hk)
    for bad in ("ctrl+hyper+k", "ctrl+alt+nope"):
        try:
            parse_hotkey(bad)
            raise AssertionError(bad)
        except ValueError:
            pass
    from capture import macos  # every backend must map onto the shared key names
    assert set(macos.KEYCODES) <= KEY_NAMES and len(set(macos.KEYCODES.values())) == len(macos.KEYCODES)
    print("selftest ok")


def main():
    import serial
    import capture
    cap = capture.load()

    port = find_port()
    ser = serial.Serial(port)
    lock = threading.Lock()
    # keys: held bindings as (kind, name, target); held: every key physically down (for the hotkey)
    # wheel: queued wheel notches, each becomes its own press + release
    st = dict(active=False, keys=set(), held=set(), mouse=deque(), wheel=deque(maxlen=4),
              cfg=None, mtime=0)

    def load_cfg():
        m = os.path.getmtime(CONFIG)
        if m == st["mtime"]:
            return
        st["mtime"] = m
        try:
            cfg = read_config()
        except Exception as e:  # keep the previous config on a typo
            print("config error:", e)
            if st["cfg"] is None:
                sys.exit(1)
            return
        st["cfg"] = cfg
        print("config loaded")

    load_cfg()

    def set_active(on):
        st["active"] = on
        st["keys"].clear(); st["mouse"].clear(); st["wheel"].clear()
        cap.grab(on)
        print("FORWARDING ON" if on else "forwarding off")

    def on_event(kind, *a):
        """Called by the capture backend for every input event. Returns True to swallow it."""
        with lock:
            cfg = st["cfg"]
            if kind == "key":
                name, down = a
                if name:
                    (st["held"].add if down else st["held"].discard)(name)
                if down and name and is_hotkey(name, st["held"], cfg["_hotkey"]):
                    set_active(not st["active"])
                    return True
                if not st["active"]:
                    return False
                t = cfg["keys"].get(name)
                if t:
                    (st["keys"].add if down else st["keys"].discard)(("k", name, t))
                return True
            if not st["active"]:
                return False
            if kind == "button":
                name, down = a
                t = cfg["mouse"].get(name)
                if t:
                    (st["keys"].add if down else st["keys"].discard)(("m", name, t))
            elif kind == "move":
                st["mouse"].append((time.monotonic(), *a))
            elif kind == "wheel" and a[0]:
                t = cfg["mouse"].get("wheel_up" if a[0] > 0 else "wheel_down")
                if t:
                    st["wheel"].append(t)
            return True  # swallow everything while forwarding

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
                cap.grab(False)
                os._exit(1)
            time.sleep(max(0, TICK - (time.monotonic() - now)))

    threading.Thread(target=sender, daemon=True).start()
    print(f"Ready on {port}. {st['cfg']['hotkey']} toggles forwarding. Ctrl+C here to quit.")
    try:
        cap.run(on_event)
    except KeyboardInterrupt:
        pass
    finally:
        cap.grab(False)
        ser.write(frame())


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main()
