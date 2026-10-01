"""Windows capture: low-level keyboard/mouse hooks (read + block) and Raw Input (mouse deltas).
Stdlib only (ctypes). Can't see input while an app running as administrator is focused."""
import sys, time

# shared key name -> set-1 scan code (+0x100 for extended keys). Positional like macOS/Linux,
# so WASD stays WASD on any keyboard layout. Base codes equal the Linux input codes.
KEYCODES = {
    "esc": 1, "1": 2, "2": 3, "3": 4, "4": 5, "5": 6, "6": 7, "7": 8, "8": 9, "9": 10, "0": 11,
    "-": 12, "=": 13, "delete": 14, "tab": 15, "q": 16, "w": 17, "e": 18, "r": 19, "t": 20,
    "y": 21, "u": 22, "i": 23, "o": 24, "p": 25, "[": 26, "]": 27, "return": 28, "ctrl": 29,
    "a": 30, "s": 31, "d": 32, "f": 33, "g": 34, "h": 35, "j": 36, "k": 37, "l": 38, ";": 39,
    "'": 40, "`": 41, "shift": 42, "\\": 43, "z": 44, "x": 45, "c": 46, "v": 47, "b": 48,
    "n": 49, "m": 50, ",": 51, ".": 52, "/": 53, "rshift": 54, "alt": 56, "space": 57,
    "caps": 58, "f1": 59, "f2": 60, "f3": 61, "f4": 62, "f5": 63, "f6": 64, "f7": 65, "f8": 66,
    "f9": 67, "f10": 68, "f11": 87, "f12": 88,
    "rctrl": 0x11D, "ralt": 0x138, "up": 0x148, "left": 0x14B, "right": 0x14D, "down": 0x150,
    "meta": 0x15B, "rmeta": 0x15C,
}
NAMES = {code: name for name, code in KEYCODES.items()}

_state = {"grabbed": False, "raw_seen": 0.0, "hook_moves": 0, "anchor": None}


def grab(on):
    """Input is blocked per event by the hooks; here we only remember where the cursor
    was, for the fallback that measures movement from it."""
    _state["grabbed"] = on
    _state["hook_moves"] = 0
    if on:
        import ctypes
        from ctypes import wintypes
        pt = wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        _state["anchor"] = (pt.x, pt.y)


def run(on_event):
    import ctypes, signal
    from ctypes import wintypes

    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    sys.setswitchinterval(0.001)  # hooks must answer fast or Windows silently removes them

    LRESULT = ctypes.c_ssize_t
    HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    user32.CallNextHookEx.argtypes = (wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
    user32.CallNextHookEx.restype = LRESULT
    user32.DefWindowProcW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    user32.DefWindowProcW.restype = LRESULT
    user32.SetWindowsHookExW.argtypes = (ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD)
    user32.SetWindowsHookExW.restype = wintypes.HHOOK
    user32.CreateWindowExW.argtypes = (wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                       ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                       wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID)
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.GetRawInputData.argtypes = (wintypes.HANDLE, wintypes.UINT, ctypes.c_void_p,
                                       ctypes.POINTER(wintypes.UINT), wintypes.UINT)
    user32.GetRawInputData.restype = wintypes.UINT
    user32.UnhookWindowsHookEx.argtypes = (wintypes.HHOOK,)
    user32.SetTimer.argtypes = (wintypes.HWND, ctypes.c_size_t, wintypes.UINT, ctypes.c_void_p)
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE

    class KBDLL(ctypes.Structure):
        _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]

    class MSLL(ctypes.Structure):
        _fields_ = [("pt", wintypes.POINT), ("mouseData", wintypes.DWORD), ("flags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]

    class RAWINPUTHEADER(ctypes.Structure):
        _fields_ = [("dwType", wintypes.DWORD), ("dwSize", wintypes.DWORD),
                    ("hDevice", wintypes.HANDLE), ("wParam", wintypes.WPARAM)]

    class RAWMOUSE(ctypes.Structure):
        _fields_ = [("usFlags", wintypes.USHORT), ("ulButtons", wintypes.ULONG),
                    ("ulRawButtons", wintypes.ULONG), ("lLastX", wintypes.LONG),
                    ("lLastY", wintypes.LONG), ("ulExtraInformation", wintypes.ULONG)]

    class RAWINPUT(ctypes.Structure):
        _fields_ = [("header", RAWINPUTHEADER), ("mouse", RAWMOUSE)]

    class RAWINPUTDEVICE(ctypes.Structure):
        _fields_ = [("usUsagePage", wintypes.USHORT), ("usUsage", wintypes.USHORT),
                    ("dwFlags", wintypes.DWORD), ("hwndTarget", wintypes.HWND)]

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                    ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
                    ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE),
                    ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR),
                    ("lpszClassName", wintypes.LPCWSTR)]

    WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x100, 0x101, 0x104, 0x105
    WM_INPUT, WM_MOUSEMOVE, WM_MOUSEWHEEL, WM_XBUTTONDOWN, WM_XBUTTONUP = 0xFF, 0x200, 0x20A, 0x20B, 0x20C
    MOUSE_BTN = {0x201: ("left", True), 0x202: ("left", False), 0x204: ("right", True),
                 0x205: ("right", False), 0x207: ("middle", True), 0x208: ("middle", False)}
    LLKHF_EXTENDED, LLKHF_UP, LLKHF_INJECTED = 0x01, 0x80, 0x10

    keys_down = set()     # for telling a fresh press from autorepeat
    os_down = set()       # key presses Windows saw: let their release through even while
                          # forwarding, or Windows would think e.g. Ctrl is stuck afterwards

    def kb_proc(n, wparam, lparam):
        if n == 0:
            k = ctypes.cast(lparam, ctypes.POINTER(KBDLL)).contents
            if not k.flags & LLKHF_INJECTED:
                code = k.scanCode | (0x100 if k.flags & LLKHF_EXTENDED else 0)
                down = wparam in (WM_KEYDOWN, WM_SYSKEYDOWN)
                repeat = down and code in keys_down
                (keys_down.add if down else keys_down.discard)(code)
                swallow = on_event("key", None if repeat else NAMES.get(code), down)
                if down and not swallow:
                    os_down.add(code)
                elif not down and code in os_down:
                    os_down.discard(code)
                    swallow = False
                if swallow:
                    return 1
        return user32.CallNextHookEx(None, n, wparam, lparam)

    def mouse_proc(n, wparam, lparam):
        if n == 0:
            m = ctypes.cast(lparam, ctypes.POINTER(MSLL)).contents
            if wparam == WM_MOUSEMOVE:
                if _state["grabbed"]:
                    # Fallback if Raw Input never reports: measure from the frozen cursor.
                    _state["hook_moves"] += 1
                    if _state["hook_moves"] > 20 and time.monotonic() - _state["raw_seen"] > 0.5:
                        ax, ay = _state["anchor"]
                        on_event("move", m.pt.x - ax, m.pt.y - ay)
                    return 1  # block: the cursor stays where it was
            elif wparam in MOUSE_BTN:
                if on_event("button", *MOUSE_BTN[wparam]):
                    return 1
            elif wparam in (WM_XBUTTONDOWN, WM_XBUTTONUP):
                name = "button4" if (m.mouseData >> 16) == 1 else "button5"
                if on_event("button", name, wparam == WM_XBUTTONDOWN):
                    return 1
            elif wparam == WM_MOUSEWHEEL:
                d = ctypes.c_short(m.mouseData >> 16).value
                if on_event("wheel", (d > 0) - (d < 0)):
                    return 1
        return user32.CallNextHookEx(None, n, wparam, lparam)

    def wnd_proc(hwnd, msg, wparam, lparam):
        if msg == WM_INPUT:
            ri, size = RAWINPUT(), wintypes.UINT(ctypes.sizeof(RAWINPUT))
            if user32.GetRawInputData(lparam, 0x10000003, ctypes.byref(ri), ctypes.byref(size),
                                      ctypes.sizeof(RAWINPUTHEADER)) != 0xFFFFFFFF:
                mouse = ri.mouse
                if ri.header.dwType == 0 and not mouse.usFlags & 1 and (mouse.lLastX or mouse.lLastY):
                    _state["raw_seen"] = time.monotonic()
                    if _state["grabbed"]:
                        on_event("move", mouse.lLastX, mouse.lLastY)
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    # keep references: ctypes callbacks are freed if the Python objects die
    kb_cb, mouse_cb, wnd_cb = HOOKPROC(kb_proc), HOOKPROC(mouse_proc), WNDPROC(wnd_proc)
    hinst = kernel32.GetModuleHandleW(None)
    wc = WNDCLASSW(lpfnWndProc=wnd_cb, hInstance=hinst, lpszClassName="KbmBridgeRawInput")
    user32.RegisterClassW(ctypes.byref(wc))
    hwnd = user32.CreateWindowExW(0, wc.lpszClassName, None, 0, 0, 0, 0, 0, None, None, hinst, None)
    rid = RAWINPUTDEVICE(0x01, 0x02, 0x100, hwnd)  # generic desktop / mouse, RIDEV_INPUTSINK
    if not user32.RegisterRawInputDevices(ctypes.byref(rid), 1, ctypes.sizeof(rid)):
        print("Raw Input unavailable, measuring mouse movement from the cursor instead.")
    hooks = [user32.SetWindowsHookExW(13, kb_cb, hinst, 0), user32.SetWindowsHookExW(14, mouse_cb, hinst, 0)]
    if not all(hooks):
        sys.exit("Could not install the keyboard/mouse hooks.")

    # Ctrl+C: Python only runs its handler between callbacks, so a timer keeps the loop ticking
    signal.signal(signal.SIGINT, lambda *a: user32.PostQuitMessage(0))
    user32.SetTimer(None, 0, 200, None)
    msg = wintypes.MSG()
    try:
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
    finally:
        for h in hooks:
            user32.UnhookWindowsHookEx(h)
