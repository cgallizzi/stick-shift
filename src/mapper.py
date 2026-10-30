"""Held keys -> GamepadState (sticks from WASD, d-pad, buttons, triggers).

Pure function of (held keys, config), so it is unit-tested without hooks.
"""

import math

from .state import GamepadState, BUTTONS


# PlayStation names -> the Xbox-position names used internally. Either set
# works in config.json; the DS4 output maps them back (LT -> L2, A -> Cross).
PS_ALIASES = {
    "CROSS": "A", "CIRCLE": "B", "SQUARE": "X", "TRIANGLE": "Y",
    "L1": "LB", "R1": "RB", "L2": "LT", "R2": "RT", "L3": "LS", "R3": "RS",
    "SHARE": "BACK", "CREATE": "BACK", "OPTIONS": "START", "PS": "GUIDE",
}
PS_NAMES = {v: k for k, v in PS_ALIASES.items() if k not in ("CREATE",)}


def normalize(cfg):
    """Fold PlayStation-named bindings into buttons/triggers (in place).
    Run on each config file before merging, so a user's "R2" replaces the
    default "RT" instead of adding to it."""
    for section in ("buttons", "triggers"):
        cfg.setdefault(section, {})
    for section in ("buttons", "triggers"):
        for name in list(cfg[section]):
            canon = PS_ALIASES.get(name.upper(), name.upper())
            keys = cfg[section].pop(name)
            target = "triggers" if canon in ("LT", "RT") else "buttons"
            merged = cfg[target].setdefault(canon, [])
            merged.extend(k for k in keys if k not in merged)
    return cfg


def display_name(btn, output):
    return PS_NAMES.get(btn, btn) if output == "ds4" else btn


def _axis(keys, neg, pos):
    """Digital axis with last-input-wins SOCD: holding A then D goes right."""
    a, b = keys.get(neg), keys.get(pos)
    if a and b:
        return 1.0 if b > a else -1.0
    if b:
        return 1.0
    if a:
        return -1.0
    return 0.0


def _any(keys, names):
    return any(n in keys for n in names)


def apply_keys(state: GamepadState, keys, cfg):
    """keys: name -> press sequence. Mutates and returns state (sticks only
    for the LEFT side; the right stick is set by MouseStick)."""
    ls = cfg["left_stick"]
    x = _axis(keys, ls["left"], ls["right"])
    y = _axis(keys, ls["down"], ls["up"])
    mag = math.hypot(x, y)
    if mag > 1.0:   # diagonals sit on the unit circle, like a real stick
        x, y = x / mag, y / mag
    if ls.get("walk_key") and ls["walk_key"] in keys:
        x *= ls.get("walk_scale", 0.5)
        y *= ls.get("walk_scale", 0.5)
    state.lx, state.ly = x, y

    for btn in BUTTONS:
        state.buttons[btn] = _any(keys, cfg["buttons"].get(btn, []))
    dp = cfg["dpad"]
    for btn, key in (("DUP", dp["up"]), ("DDOWN", dp["down"]),
                     ("DLEFT", dp["left"]), ("DRIGHT", dp["right"])):
        state.buttons[btn] = state.buttons[btn] or key in keys

    tr = cfg["triggers"]
    state.lt = 1.0 if _any(keys, tr.get("LT", [])) else 0.0
    state.rt = 1.0 if _any(keys, tr.get("RT", [])) else 0.0
    return state


def bound_names(cfg):
    """Every key/mouse name the config uses (these get tracked + blocked)."""
    names = set()
    ls = cfg["left_stick"]
    names.update(ls[k] for k in ("up", "down", "left", "right"))
    if ls.get("walk_key"):
        names.add(ls["walk_key"])
    names.update(cfg["dpad"].values())
    for v in cfg["buttons"].values():
        names.update(v)
    for v in cfg["triggers"].values():
        names.update(v)
    return names
