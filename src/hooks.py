"""Low-level keyboard/mouse hooks (WH_KEYBOARD_LL / WH_MOUSE_LL) via ctypes.

While ACTIVE the hooks swallow input so the game never sees keyboard/mouse
(many games drop aim assist and switch prompts the instant they see KBM).
The toggle key is always swallowed and flips ACTIVE on/off.

Mouse deltas: a blocked WM_MOUSEMOVE never moves the cursor, but its pt is
where the cursor WOULD have gone, so pt - GetCursorPos() is that event's
motion in counts. With "Enhance pointer precision" off and the Windows
pointer speed at the default 10/20, that is 1:1 with the sensor. Blocking in
an LL hook also suppresses Raw Input, so games reading raw mouse see nothing.

Injected events (SendInput from other software) are passed through untouched
unless allow_injected is set (used only for self-tests).
"""

import ctypes
import ctypes.wintypes as w
import threading

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WH_KEYBOARD_LL, WH_MOUSE_LL = 13, 14
WM_QUIT = 0x0012
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x100, 0x101, 0x104, 0x105
WM_MOUSEMOVE = 0x200
WM_MOUSEWHEEL = 0x20A
LLKHF_INJECTED = 0x10
LLMHF_INJECTED = 0x01

# The hook's pt is in physical pixels; without DPI awareness GetCursorPos
# returns *scaled* coordinates on a 125/150% display and every delta is wrong.
user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2

LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, w.WPARAM, w.LPARAM)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", w.DWORD), ("scanCode", w.DWORD), ("flags", w.DWORD),
                ("time", w.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", w.POINT), ("mouseData", w.DWORD), ("flags", w.DWORD),
                ("time", w.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, w.HINSTANCE, w.DWORD]
user32.SetWindowsHookExW.restype = w.HHOOK
user32.CallNextHookEx.argtypes = [w.HHOOK, ctypes.c_int, w.WPARAM, w.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [w.HHOOK]
user32.GetMessageW.argtypes = [ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT]
user32.PostThreadMessageW.argtypes = [w.DWORD, w.UINT, w.WPARAM, w.LPARAM]
user32.GetCursorPos.argtypes = [ctypes.POINTER(w.POINT)]
kernel32.GetModuleHandleW.restype = w.HMODULE

# Mouse button messages -> (button name, is_down)
_MOUSE_MSGS = {
    0x201: ("MOUSE1", True), 0x202: ("MOUSE1", False),
    0x204: ("MOUSE2", True), 0x205: ("MOUSE2", False),
    0x207: ("MOUSE3", True), 0x208: ("MOUSE3", False),
}
_XBUTTON_DOWN, _XBUTTON_UP = 0x20B, 0x20C


class InputHooks:
    def __init__(self, vk_to_name, toggle_vk, on_toggle=None,
                 capture_mouse=True, block_all=True, allow_injected=False):
        self.vk_to_name = vk_to_name        # vk -> key name, for keys we track
        self.toggle_vk = toggle_vk
        self.on_toggle = on_toggle
        self.capture_mouse = capture_mouse
        self.block_all = block_all
        self.allow_injected = allow_injected

        self.active = False
        # Menu mode: mouse behaves as a normal mouse while the pad stays live.
        self.mouse_passthrough = False
        self.hold_name = None         # mouse/key name that forces menu mode
        self.hotkeys = {}             # vk -> callback, always swallowed
        self._passed = set()          # mouse buttons whose DOWN reached the game
        self._lock = threading.Lock()
        self._down = {}           # name -> press sequence number (for last-wins)
        self._seq = 0
        self._dx = self._dy = 0
        self._wheel = {"WHEELUP": 0, "WHEELDOWN": 0}
        self._toggle_held = False
        self._down_hotkeys = set()
        self._thread = None
        self._tid = None
        # Keep references so the callbacks are never garbage-collected.
        self._kproc = HOOKPROC(self._kbd)
        self._mproc = HOOKPROC(self._mouse)

    # --- called from the main loop -------------------------------------
    def take_mouse(self):
        with self._lock:
            dx, dy = self._dx, self._dy
            self._dx = self._dy = 0
        return dx, dy

    def take_wheel(self):
        with self._lock:
            out = dict(self._wheel)
            for k in self._wheel:
                self._wheel[k] = 0
        return out

    def keys(self):
        """name -> press sequence (higher = pressed more recently)."""
        with self._lock:
            return dict(self._down)

    def set_active(self, on):
        with self._lock:
            self.active = on
            self._down.clear()
            self._dx = self._dy = 0
        if on and self.capture_mouse:
            # Park the cursor mid-screen so edge clamping never eats motion.
            user32.SetCursorPos(user32.GetSystemMetrics(0) // 2,
                                user32.GetSystemMetrics(1) // 2)

    # --- hook thread ------------------------------------------------------
    def start(self):
        ready = threading.Event()
        err = []

        def run():
            self._tid = kernel32.GetCurrentThreadId()
            hmod = kernel32.GetModuleHandleW(None)
            hk = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._kproc, hmod, 0)
            hm = user32.SetWindowsHookExW(WH_MOUSE_LL, self._mproc, hmod, 0) if self.capture_mouse else None
            if not hk or (self.capture_mouse and not hm):
                err.append(ctypes.get_last_error())
                ready.set()
                return
            ready.set()
            msg = w.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                pass
            user32.UnhookWindowsHookEx(hk)
            if hm:
                user32.UnhookWindowsHookEx(hm)

        self._thread = threading.Thread(target=run, name="stickshift-hooks", daemon=True)
        self._thread.start()
        ready.wait(5)
        if err:
            raise OSError(f"SetWindowsHookEx failed (winerror {err[0]})")

    def stop(self):
        if self._tid:
            user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
        if self._thread:
            self._thread.join(2)

    def _press(self, name, down):
        if down:
            if name not in self._down:
                self._seq += 1
                self._down[name] = self._seq
        else:
            self._down.pop(name, None)

    # Callbacks must stay tiny: Windows silently unhooks slow LL hooks.
    def _kbd(self, code, wparam, lparam):
        if code == 0:
            kb = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            if self.allow_injected or not (kb.flags & LLKHF_INJECTED):
                down = wparam in (WM_KEYDOWN, WM_SYSKEYDOWN)
                cb = self.hotkeys.get(kb.vkCode)
                if cb:
                    if down and kb.vkCode not in self._down_hotkeys:
                        self._down_hotkeys.add(kb.vkCode)
                        cb()
                    elif not down:
                        self._down_hotkeys.discard(kb.vkCode)
                    return 1
                if kb.vkCode == self.toggle_vk:
                    if down and not self._toggle_held:
                        self._toggle_held = True
                        self.set_active(not self.active)
                        if self.on_toggle:
                            self.on_toggle(self.active)
                    elif not down:
                        self._toggle_held = False
                    return 1
                if self.active:
                    name = self.vk_to_name.get(kb.vkCode)
                    if name:
                        with self._lock:
                            self._press(name, down)
                    if name or self.block_all:
                        return 1
        return user32.CallNextHookEx(None, code, wparam, lparam)

    def _mouse(self, code, wparam, lparam):
        if code == 0 and self.active:
            ms = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            if self.allow_injected or not (ms.flags & LLMHF_INJECTED):
                if wparam == WM_MOUSEMOVE and not self.mouse_passthrough:
                    cur = w.POINT()
                    user32.GetCursorPos(ctypes.byref(cur))
                    with self._lock:
                        self._dx += ms.pt.x - cur.x
                        self._dy += ms.pt.y - cur.y
                    return 1
                if wparam == WM_MOUSEWHEEL and not self.mouse_passthrough:
                    delta = ctypes.c_short(ms.mouseData >> 16).value
                    with self._lock:
                        self._wheel["WHEELUP" if delta > 0 else "WHEELDOWN"] += 1
                    return 1
                btn = _MOUSE_MSGS.get(wparam)
                if btn is None and wparam in (_XBUTTON_DOWN, _XBUTTON_UP):
                    which = (ms.mouseData >> 16) & 0xFFFF
                    btn = ("MOUSE4" if which == 1 else "MOUSE5", wparam == _XBUTTON_DOWN)
                if btn and btn[0] == self.hold_name:
                    with self._lock:
                        self._press(*btn)
                    return 1
                # In menu mode clicks go to the game as real clicks. A button
                # pressed in menu mode also gets its release, so leaving menu
                # mode mid-click can't leave the game with a stuck button.
                if btn and (self.mouse_passthrough or (not btn[1] and btn[0] in self._passed)):
                    if btn[1]:
                        self._passed.add(btn[0])
                    else:
                        self._passed.discard(btn[0])
                        with self._lock:      # also release it on the pad
                            self._press(btn[0], False)
                    return user32.CallNextHookEx(None, code, wparam, lparam)
                if self.mouse_passthrough:
                    return user32.CallNextHookEx(None, code, wparam, lparam)
                if btn:
                    with self._lock:
                        self._press(*btn)
                    return 1
                if self.block_all:
                    return 1
        return user32.CallNextHookEx(None, code, wparam, lparam)

