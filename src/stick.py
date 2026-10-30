"""Mouse -> right-stick translation. Pure math, no Windows APIs (unit-tested).

Why this is not just "scale dx into the stick":

  A mouse is a POSITION device: N counts of motion = N counts of camera turn,
  no matter how fast you moved. A stick is a RATE device: deflection sets a
  turn SPEED, and the camera keeps turning for as long as you hold it. The
  game then bends that speed through a deadzone, a response curve and a hard
  cap (the "max turn rate" at full deflection).

So for a mouse movement to feel like the mouse, we must:

  1. Convert counts to the angle you WANTED to turn (your normal cm/360).
  2. Bank that angle in a "pending" buffer and pay it out over a few ms as a
     turn RATE. Paying out pending/tau per second is a first-order low-pass on
     rotation: total angle out == total angle in (distance is preserved), and
     the stick snaps back to center ~tau after the mouse stops (no drift).
  3. Turn that rate into the deflection the GAME needs to produce it: divide
     by the game's max turn rate, undo its response curve, and lift the result
     past its inner deadzone (otherwise slow micro-adjustments vanish).
  4. Cap at full deflection. A fast flick wants more than max_turn_deg_s;
     the overflow stays in "pending" (carryover) so the flick still lands on
     the right angle, just slightly later. carryover_max_deg bounds that so a
     huge swipe doesn't keep spinning you for a second after you stop.

X and Y are handled as one vector so diagonals keep their direction and never
exceed the stick's unit circle.
"""

import math
from dataclasses import dataclass


@dataclass
class StickConfig:
    # What the mouse should feel like (your usual PC sensitivity).
    mouse_dpi: float = 800.0
    cm_per_360: float = 35.0
    # What the game does with the stick (measure with --calibrate).
    max_turn_deg_s: float = 360.0   # yaw speed at full deflection
    pitch_ratio: float = 1.0        # game's vertical speed / horizontal speed
    game_deadzone: float = 0.10     # game's inner deadzone (0..1)
    game_curve_exponent: float = 1.0  # 1 = linear, 2 = "exponential"/quadratic
    # How the angle is paid out.
    smoothing_ms: float = 15.0      # tau: ~1 game frame. lower = snappier
    carryover_max_deg: float = 45.0  # 0 = drop anything beyond max turn rate
    invert_y: bool = False

    @property
    def counts_per_360(self):
        return self.cm_per_360 / 2.54 * self.mouse_dpi

    @property
    def deg_per_count(self):
        return 360.0 / self.counts_per_360

    @classmethod
    def from_dict(cls, d):
        fields = cls.__dataclass_fields__
        return cls(**{k: v for k, v in d.items() if k in fields})


class MouseStick:
    # Pending angles below this are considered "arrived" (prevents a deadzone-
    # floored tail from creeping the camera after the mouse stops).
    EPSILON_DEG = 0.01

    def __init__(self, cfg: StickConfig):
        self.cfg = cfg
        self.pending_x = 0.0  # degrees still owed, yaw (+ = right)
        self.pending_y = 0.0  # degrees still owed, pitch (+ = up)
        # Telemetry for the overlay (read-only from outside).
        self.demand = 0.0     # turn rate the mouse asked for, deg/s
        self.rate = 0.0       # turn rate actually sent (capped), deg/s
        self.saturated = False

    def reset(self):
        self.pending_x = self.pending_y = 0.0
        self.demand = self.rate = 0.0
        self.saturated = False

    @property
    def pending_deg(self):
        return math.hypot(self.pending_x, self.pending_y)

    def add_counts(self, dx, dy):
        """Raw mouse counts (Windows convention: +dy = down)."""
        k = self.cfg.deg_per_count
        self.pending_x += dx * k
        sign = 1.0 if self.cfg.invert_y else -1.0
        self.pending_y += sign * dy * k

    def tick(self, dt):
        """Advance dt seconds. Returns (x, y) stick deflection in [-1, 1]."""
        c = self.cfg
        if dt <= 0:
            return 0.0, 0.0

        # Pitch is turned by the game at max*pitch_ratio, so express pitch
        # in "yaw-equivalent" degrees; then one max rate applies to the vector.
        py_eq = self.pending_y / c.pitch_ratio if c.pitch_ratio > 0 else 0.0
        mag_pending = math.hypot(self.pending_x, py_eq)
        if mag_pending < self.EPSILON_DEG:
            self.pending_x = self.pending_y = 0.0
            self.demand = self.rate = 0.0
            self.saturated = False
            return 0.0, 0.0

        # Direction of the owed turn (the drain below is proportional, so it
        # doesn't change direction).
        ux, uy = self.pending_x / mag_pending, py_eq / mag_pending

        tau = max(c.smoothing_ms, 0.1) / 1000.0
        # Exact exponential drain over dt (stable for any dt vs tau).
        rate = mag_pending * (1.0 - math.exp(-dt / tau)) / dt
        saturated = rate >= c.max_turn_deg_s
        self.demand = rate
        rate = min(rate, c.max_turn_deg_s)
        self.rate, self.saturated = rate, saturated

        out_deg = rate * dt
        frac = out_deg / mag_pending
        self.pending_x -= self.pending_x * frac
        self.pending_y -= self.pending_y * frac

        # Bound the overflow a saturated flick leaves behind.
        cap = max(c.carryover_max_deg, 0.0)
        rem = mag_pending - out_deg
        if saturated and rem > cap:
            s = cap / rem
            self.pending_x *= s
            self.pending_y *= s

        # rate -> deflection the game needs (undo curve, then deadzone).
        r = rate / c.max_turn_deg_s
        m = r ** (1.0 / c.game_curve_exponent)
        dz = c.game_deadzone
        mag_out = min(1.0, dz + (1.0 - dz) * m)
        return ux * mag_out, uy * mag_out


def game_turn_rate(x, y, cfg: StickConfig):
    """Model of what the GAME does with a deflection: returns (yaw, pitch)
    deg/s. Used by tests and by the calibration report to check the inverse."""
    mag = math.hypot(x, y)
    dz = cfg.game_deadzone
    if mag <= dz:
        return 0.0, 0.0
    m = min(1.0, (mag - dz) / (1.0 - dz))
    rate = cfg.max_turn_deg_s * m ** cfg.game_curve_exponent
    return rate * x / mag, rate * y / mag * cfg.pitch_ratio
