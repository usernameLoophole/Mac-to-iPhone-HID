"""macOS capture: Quartz event tap. Needs Input Monitoring + Accessibility."""
import sys

KEYCODES = {  # shared key name -> macOS ANSI virtual keycode
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9, "b": 11,
    "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17, "1": 18, "2": 19, "3": 20, "4": 21,
    "6": 22, "5": 23, "=": 24, "9": 25, "7": 26, "-": 27, "8": 28, "0": 29, "]": 30, "o": 31,
    "u": 32, "[": 33, "i": 34, "p": 35, "return": 36, "l": 37, "j": 38, "'": 39, "k": 40,
    ";": 41, "\\": 42, ",": 43, "/": 44, "n": 45, "m": 46, ".": 47, "tab": 48, "space": 49,
    "`": 50, "delete": 51, "esc": 53, "rmeta": 54, "meta": 55, "shift": 56, "caps": 57,
    "alt": 58, "ctrl": 59, "rshift": 60, "ralt": 61, "rctrl": 62,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97, "f7": 98, "f8": 100,
    "f9": 101, "f10": 109, "f11": 103, "f12": 111,
    "left": 123, "right": 124, "down": 125, "up": 126,
}
NAMES = {code: name for name, code in KEYCODES.items()}


def grab(on):
    import Quartz as Q
    Q.CGAssociateMouseAndMouseCursorPosition(not on)


def run(on_event):
    import Quartz as Q

    # flagsChanged carries no up/down: read it from the modifier's flag bit
    MODS = {56: Q.kCGEventFlagMaskShift, 60: Q.kCGEventFlagMaskShift,
            59: Q.kCGEventFlagMaskControl, 62: Q.kCGEventFlagMaskControl,
            58: Q.kCGEventFlagMaskAlternate, 61: Q.kCGEventFlagMaskAlternate,
            55: Q.kCGEventFlagMaskCommand, 54: Q.kCGEventFlagMaskCommand,
            57: Q.kCGEventFlagMaskAlphaShift}
    BUTTONS = {Q.kCGEventLeftMouseDown: ("left", True), Q.kCGEventLeftMouseUp: ("left", False),
               Q.kCGEventRightMouseDown: ("right", True), Q.kCGEventRightMouseUp: ("right", False)}
    OTHER = (Q.kCGEventOtherMouseDown, Q.kCGEventOtherMouseUp)
    MOVES = {Q.kCGEventMouseMoved, Q.kCGEventLeftMouseDragged,
             Q.kCGEventRightMouseDragged, Q.kCGEventOtherMouseDragged}
    field = Q.CGEventGetIntegerValueField

    def callback(proxy, etype, ev, refcon):
        if etype in (Q.kCGEventTapDisabledByTimeout, Q.kCGEventTapDisabledByUserInput):
            Q.CGEventTapEnable(tap, True)
            return ev
        if etype in (Q.kCGEventKeyDown, Q.kCGEventKeyUp, Q.kCGEventFlagsChanged):
            code = field(ev, Q.kCGKeyboardEventKeycode)
            if etype == Q.kCGEventFlagsChanged:
                down = bool(Q.CGEventGetFlags(ev) & MODS.get(code, 0))
            else:
                down = etype == Q.kCGEventKeyDown
            swallow = on_event("key", NAMES.get(code), down)
        elif etype in BUTTONS:
            swallow = on_event("button", *BUTTONS[etype])
        elif etype in OTHER:
            n = field(ev, Q.kCGMouseEventButtonNumber)
            swallow = on_event("button", "middle" if n == 2 else f"button{n + 1}",
                               etype == Q.kCGEventOtherMouseDown)
        elif etype in MOVES:
            swallow = on_event("move", field(ev, Q.kCGMouseEventDeltaX),
                               field(ev, Q.kCGMouseEventDeltaY))
        elif etype == Q.kCGEventScrollWheel:
            d = field(ev, Q.kCGScrollWheelEventDeltaAxis1)
            swallow = on_event("wheel", (d > 0) - (d < 0))
        else:
            swallow = False
        return None if swallow else ev

    mask = 0
    for e in (Q.kCGEventKeyDown, Q.kCGEventKeyUp, Q.kCGEventFlagsChanged,
              Q.kCGEventLeftMouseDown, Q.kCGEventLeftMouseUp, Q.kCGEventRightMouseDown,
              Q.kCGEventRightMouseUp, *OTHER, *MOVES, Q.kCGEventScrollWheel):
        mask |= Q.CGEventMaskBit(e)
    tap = Q.CGEventTapCreate(Q.kCGSessionEventTap, Q.kCGHeadInsertEventTap,
                             Q.kCGEventTapOptionDefault, mask, callback, None)
    if not tap:
        sys.exit("Event tap failed: grant Input Monitoring + Accessibility to your terminal "
                 "(System Settings > Privacy & Security), then restart it.")
    src = Q.CFMachPortCreateRunLoopSource(None, tap, 0)
    Q.CFRunLoopAddSource(Q.CFRunLoopGetCurrent(), src, Q.kCFRunLoopCommonModes)
    Q.CGEventTapEnable(tap, True)
    Q.CFRunLoopRun()
