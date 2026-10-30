"""Normalized, output-agnostic gamepad state.

The whole bridge speaks this one intermediate representation:

    keyboard + mouse  ->  GamepadState  ->  virtual Xbox / DS4

Input backends fill a GamepadState in. Output backends read it out. Neither
side needs to know about the other, so adding a controller or an output target
only touches one file.
"""

from dataclasses import dataclass, field

# Logical button names. These are abstract (not Xbox- or PlayStation-specific):
# A/B/X/Y are the four face buttons in Xbox layout positions. Each output
# backend maps these to its own native button.
BUTTONS = (
    "A", "B", "X", "Y",
    "LB", "RB",            # shoulder bumpers
    "BACK", "START", "GUIDE",
    "LS", "RS",            # stick clicks
    "DUP", "DDOWN", "DLEFT", "DRIGHT",
)


@dataclass
class GamepadState:
    # Sticks: floats in [-1.0, 1.0]. +x = right, +y = up.
    lx: float = 0.0
    ly: float = 0.0
    rx: float = 0.0
    ry: float = 0.0
    # Triggers: floats in [0.0, 1.0].
    lt: float = 0.0
    rt: float = 0.0
    # Buttons: name -> pressed?
    buttons: dict = field(default_factory=lambda: {b: False for b in BUTTONS})

    # Mouse intent for this frame: relative cursor motion (pixels, may be
    # fractional) plus optional click state. Populated by trackpad/gyro
    # processors when their destination is "mouse"; otherwise zero/None.
    mdx: float = 0.0
    mdy: float = 0.0
    mouse_left: bool = False
    mouse_right: bool = False

    def reset(self):
        self.lx = self.ly = self.rx = self.ry = 0.0
        self.lt = self.rt = 0.0
        for b in self.buttons:
            self.buttons[b] = False
        self.mdx = self.mdy = 0.0
        self.mouse_left = self.mouse_right = False
