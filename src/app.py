"""Stick Shift: keyboard + mouse -> virtual Xbox 360 / DS4 controller.

    python -m src.app               run (toggle with F8 by default)
    python -m src.app --calibrate   measure the game's stick turn speed + curve
    python -m src.app --mode ds4    override output type

Frozen (StickShift.exe): same flags; config.json lives next to the exe.
"""

import argparse
import ctypes
import json
import math
import os
import sys
import threading
import time

from .hooks import InputHooks
from .keymap import VK, is_valid, vk
from .mapper import apply_keys, bound_names, display_name, normalize
from .state import GamepadState
from .stick import MouseStick, StickConfig, game_turn_rate

FROZEN = getattr(sys, "frozen", False)
if FROZEN:   # PyInstaller: bundled files unpack to _MEIPASS, user files sit by the exe
    BUNDLE, HOME = sys._MEIPASS, os.path.dirname(sys.executable)
else:
    BUNDLE = HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PATH = os.path.join(BUNDLE, "config.default.json")
USER_PATH = os.path.join(HOME, "config.json")
DRIVER_MSI = "ViGEmBusSetup_x64.msi"


# ---------------------------------------------------------------- config
def load_config():
    with open(DEFAULT_PATH) as f:
        cfg = normalize(json.load(f))
    if os.path.exists(USER_PATH):
        with open(USER_PATH) as f:
            user = json.load(f)
        if "buttons" in user or "triggers" in user:
            normalize(user)
        for k, v in user.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    bad = sorted(n for n in bound_names(cfg) if not is_valid(n))
    if bad or not is_valid(cfg["toggle_key"]):
        raise SystemExit(f"[config] unknown key name(s): {bad or [cfg['toggle_key']]}")
    return cfg


def save_right_stick(updates):
    user = {}
    if os.path.exists(USER_PATH):
        with open(USER_PATH) as f:
            user = json.load(f)
    user.setdefault("right_stick", {}).update(updates)
    with open(USER_PATH, "w") as f:
        json.dump(user, f, indent=2)


# ---------------------------------------------------------------- windows bits
def check_pointer_settings():
    """Warn about settings that make cursor deltas != sensor counts."""
    user32 = ctypes.windll.user32
    mouse = (ctypes.c_int * 3)()
    user32.SystemParametersInfoW(0x0003, 0, mouse, 0)          # SPI_GETMOUSE
    speed = ctypes.c_int()
    user32.SystemParametersInfoW(0x0070, 0, ctypes.byref(speed), 0)  # SPI_GETMOUSESPEED
    if mouse[2]:
        print("[warn] 'Enhance pointer precision' is ON - Windows accelerates the\n"
              "       deltas we read, so aim won't be consistent. Turn it off in\n"
              "       Settings > Bluetooth & devices > Mouse > Additional mouse settings.")
    if speed.value != 10:
        print(f"[warn] Windows pointer speed is {speed.value}/20 (10 is 1:1 with the sensor).\n"
              "       Fine, but then mouse_dpi in config.json is effectively scaled.")


class _CURSORINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint32), ("flags", ctypes.c_uint32),
                ("hCursor", ctypes.c_void_p), ("pt", ctypes.c_long * 2)]


def cursor_visible():
    """True when Windows is drawing a cursor (menus, desktop). FPS gameplay
    hides it, which is what tells us the mouse should be the right stick."""
    ci = _CURSORINFO(cbSize=ctypes.sizeof(_CURSORINFO))
    if not ctypes.windll.user32.GetCursorInfo(ctypes.byref(ci)):
        return False
    return bool(ci.flags & 1)  # CURSOR_SHOWING


def beep(on):
    import winsound
    threading.Thread(target=winsound.Beep, args=(1200 if on else 500, 70), daemon=True).start()


def vigembus_installed():
    import winreg
    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                       r"SYSTEM\CurrentControlSet\Services\ViGEmBus"))
        return True
    except OSError:
        return False


def ensure_driver():
    """Test PCs won't have ViGEmBus. Offer the bundled installer (one UAC prompt)."""
    if vigembus_installed():
        return
    msi = next((p for p in (os.path.join(HOME, DRIVER_MSI), os.path.join(BUNDLE, DRIVER_MSI))
                if os.path.exists(p)), None)
    print("The ViGEmBus driver (creates the virtual controller) isn't installed on this PC.")
    if not msi:
        raise SystemExit("Install it from https://github.com/nefarius/ViGEmBus/releases and rerun.")
    if input("Install it now? Windows will ask for admin. [Y/n] ").strip().lower() not in ("", "y", "yes"):
        raise SystemExit("Can't run without it.")
    import subprocess
    subprocess.run(["msiexec", "/i", msi, "/passive", "/norestart"])
    if not vigembus_installed():
        raise SystemExit("Driver install didn't complete. Run the .msi by hand, then rerun.")
    print("Driver installed.\n")


def make_pad(mode):
    try:
        from .output_vgamepad import make_output
        return make_output(mode)
    except Exception as e:
        raise SystemExit(f"[error] couldn't create virtual {mode} pad: {e}\n"
                         "        Install ViGEmBus: https://github.com/nefarius/ViGEmBus/releases")


# ---------------------------------------------------------------- run
def run(cfg):
    sc = StickConfig.from_dict(cfg["right_stick"])
    stick = MouseStick(sc)
    pad = make_pad(cfg["output"])
    state = GamepadState()

    menu = cfg["menu_mode"]
    names = bound_names(cfg) | ({menu["hold_key"]} if menu.get("hold_key") else set())
    vk_to_name = {vk(n): n for n in names if n.upper() in VK}

    def on_toggle(active):
        beep(active)
        print("[ON ] controller mode - KBM hidden from games" if active
              else "[OFF] keyboard + mouse back to normal")

    hooks = InputHooks(vk_to_name, vk(cfg["toggle_key"]), on_toggle,
                       block_all=cfg["block_all_input_when_active"])
    hooks.hold_name = menu.get("hold_key") or None

    stats = {"hz": 0.0}
    ov_cfg = cfg["overlay"]
    if ov_cfg.get("enabled"):
        from .overlay import Overlay

        def telemetry():
            return {
                "mode": ("menu" if hooks.mouse_passthrough else "aim") if hooks.active else "native",
                "output": cfg["output"],
                "lx": state.lx, "ly": state.ly, "rx": state.rx, "ry": state.ry,
                "lt": state.lt, "rt": state.rt, "buttons": dict(state.buttons),
                "demand": stick.demand, "rate": stick.rate, "max_rate": sc.max_turn_deg_s,
                "pending": stick.pending_deg, "saturated": stick.saturated,
                "deadzone": sc.game_deadzone, "hz": stats["hz"] if hooks.active else 0.0,
            }

        overlay = Overlay(telemetry, ov_cfg.get("position", "top-left"),
                          ov_cfg.get("scale", 1.0), ov_cfg.get("alpha", 0.95))
        overlay.start()
        if ov_cfg.get("toggle_key"):
            hooks.hotkeys[vk(ov_cfg["toggle_key"])] = overlay.toggle
    hooks.start()

    print(f"Virtual {cfg['output'].upper()} pad connected.")
    print(f"Mouse: {sc.mouse_dpi:g} DPI @ {sc.cm_per_360:g} cm/360 = {sc.counts_per_360:.0f} counts/360")
    print(f"Game:  {sc.max_turn_deg_s:g} deg/s max, deadzone {sc.game_deadzone:g}, curve ^{sc.game_curve_exponent:g}")
    fastest = sc.max_turn_deg_s / 360 * sc.cm_per_360
    print(f"       mouse swipes faster than {fastest:.0f} cm/s hit the stick's max turn speed")
    binds = {**cfg["buttons"], **cfg["triggers"]}
    print("Bindings: " + "  ".join(f"{display_name(b, cfg['output'])}={'/'.join(k)}"
                                   for b, k in binds.items() if k))
    if menu.get("auto_when_cursor_visible"):
        print("Menu mode: mouse works as a normal mouse whenever the cursor is showing.")
    if hooks.hold_name:
        print(f"           hold {hooks.hold_name} to force normal mouse.")
    if ov_cfg.get("enabled"):
        print(f"Overlay: {ov_cfg.get('position', 'top-left')}, {ov_cfg.get('toggle_key')} shows/hides it.")
    print(f"Press {cfg['toggle_key']} to toggle controller mode.  Ctrl+C (while OFF) to quit.\n")

    if cfg.get("start_active"):
        hooks.set_active(True)
        on_toggle(True)

    winmm = ctypes.windll.winmm
    winmm.timeBeginPeriod(1)
    period = 1.0 / cfg["tick_hz"]
    pulse = cfg["wheel_pulse_ms"] / 1000.0
    wheel_until = {"WHEELUP": 0.0, "WHEELDOWN": 0.0}
    was_active = False
    last = time.perf_counter()
    hz_t0, hz_n = last, 0
    try:
        while True:
            now = time.perf_counter()
            dt, last = now - last, now

            if not hooks.active:
                if was_active:
                    stick.reset()
                    state.reset()
                    pad.apply(state)
                    was_active = False
                time.sleep(0.01)
                continue
            was_active = True

            keys = hooks.keys()
            in_menu = (hooks.hold_name in keys) or (
                menu.get("auto_when_cursor_visible") and cursor_visible())
            if in_menu != hooks.mouse_passthrough:
                hooks.mouse_passthrough = in_menu
                stick.reset()
                print("  [menu] normal mouse" if in_menu else "  [aim ] mouse = right stick")

            dx, dy = hooks.take_mouse()
            stick.add_counts(dx, dy)
            state.rx, state.ry = stick.tick(dt)

            for name, n in hooks.take_wheel().items():
                if n:
                    wheel_until[name] = now + pulse
            for name, until in wheel_until.items():
                if now < until:
                    keys[name] = 0
            apply_keys(state, keys, cfg)
            pad.apply(state)
            hz_n += 1
            if now - hz_t0 >= 1.0:
                stats["hz"], hz_t0, hz_n = hz_n / (now - hz_t0), now, 0

            spare = period - (time.perf_counter() - now)
            if spare > 0:
                time.sleep(spare)
    except KeyboardInterrupt:
        pass
    finally:
        winmm.timeEndPeriod(1)
        hooks.stop()
        pad.close()
        print("bye")


# ---------------------------------------------------------------- calibrate
def _timed_hold(hooks, pad, deflection, key="F9"):
    """Hold right stick at `deflection` while `key` is held; return seconds."""
    state = GamepadState()
    t0 = None
    while True:
        held = key in hooks.keys()
        if held and t0 is None:
            t0 = time.perf_counter()
            state.rx = deflection
            pad.apply(state)
        elif not held and t0 is not None:
            secs = time.perf_counter() - t0
            state.rx = 0.0
            pad.apply(state)
            return secs
        time.sleep(0.001)


def _ask_turns():
    raw = input("  How many full turns did you make? [3] ").strip()
    return float(raw) if raw else 3.0


def calibrate(cfg):
    sc = StickConfig.from_dict(cfg["right_stick"])
    pad = make_pad(cfg["output"])
    hooks = InputHooks({vk("F9"): "F9"}, toggle_vk=0, capture_mouse=False, block_all=False)
    hooks.start()
    hooks.set_active(True)
    ctypes.windll.winmm.timeBeginPeriod(1)

    print("Calibration. In the game first:")
    print("  * set stick response curve to LINEAR (or note what it is)")
    print("  * turn OFF look acceleration / turn ramp-up / 'extra yaw'")
    print("  * set the right-stick inner deadzone LOW, then put that value in")
    print(f"    config.json as game_deadzone (currently {sc.game_deadzone:g})")
    print("  * pick a landmark to line up with.\n")

    print("STEP 1 - full speed. Hold F9 in-game; release when you're back on the")
    print("         landmark after a whole number of turns (3+ is more accurate).")
    secs = _timed_hold(hooks, pad, 1.0)
    full = 360.0 * _ask_turns() / secs
    print(f"  -> max turn speed {full:.0f} deg/s ({secs:.2f}s held)\n")

    half_raw = 0.55
    m = (half_raw - sc.game_deadzone) / (1 - sc.game_deadzone)
    print("STEP 2 - partial deflection (finds the response curve). Same thing, F9.")
    secs = _timed_hold(hooks, pad, half_raw)
    part = 360.0 * _ask_turns() / secs
    exponent = math.log(part / full) / math.log(m) if 0 < part < full else 1.0
    exponent = round(min(max(exponent, 0.5), 4.0), 2)
    print(f"  -> {part:.0f} deg/s at {half_raw:.0%} stick => curve exponent {exponent}\n")

    hooks.stop()
    pad.close()
    save_right_stick({"max_turn_deg_s": round(full, 1), "game_curve_exponent": exponent})
    sc.max_turn_deg_s, sc.game_curve_exponent = full, exponent
    check, _ = game_turn_rate(half_raw, 0, sc)
    print(f"Saved to {USER_PATH}. (model check: {check:.0f} deg/s at {half_raw:.0%})")
    print("Now set mouse_dpi + cm_per_360 to your usual PC sens and play.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--mode", choices=["xbox", "ds4"])
    ap.add_argument("--no-overlay", action="store_true")
    args = ap.parse_args()
    sys.setswitchinterval(0.0005)   # hook callbacks need the GIL promptly
    cfg = load_config()
    if args.mode:
        cfg["output"] = args.mode
    if args.no_overlay:
        cfg["overlay"]["enabled"] = False
    check_pointer_settings()
    ensure_driver()
    if args.calibrate:
        calibrate(cfg)
    else:
        run(cfg)


def _pause():
    try:
        input("\nPress Enter to close.")
    except EOFError:   # no console attached (piped / scripted)
        pass


def entry():
    """Exe entry point: never let a double-clicked window vanish on an error."""
    sys.stdout.reconfigure(line_buffering=True)
    try:
        main()
    except SystemExit as e:
        if FROZEN and e.code not in (None, 0):
            print(e.code if isinstance(e.code, str) else "")
            _pause()
            sys.exit(1)   # message already shown; don't print it twice
        raise
    except Exception:
        if not FROZEN:
            raise
        import traceback
        traceback.print_exc()
        _pause()


if __name__ == "__main__":
    main()
