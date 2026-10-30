"""The real test of the mouse->stick model: drive it with mouse motion, feed
its output through a model of the GAME (deadzone, curve, max rate) and check
the camera turns as far as the mouse would have turned it."""

import math
import unittest

from src.stick import MouseStick, StickConfig, game_turn_rate
from src.mapper import apply_keys, normalize, display_name
from src.state import GamepadState


def simulate(cfg, motion, secs, tick_hz=500, sensor_hz=1000):
    """motion(t) -> mouse speed in counts/s (x, y). Returns (yaw, pitch)
    degrees the game actually turned, and the last stick output."""
    stick = MouseStick(cfg)
    dt = 1.0 / tick_hz
    per_tick = sensor_hz // tick_hz
    yaw = pitch = 0.0
    carry_x = carry_y = 0.0
    out = (0.0, 0.0)
    t = 0.0
    for _ in range(int(secs * tick_hz)):
        for i in range(per_tick):
            vx, vy = motion(t + i / sensor_hz)
            carry_x += vx / sensor_hz
            carry_y += vy / sensor_hz
            ix, iy = int(carry_x), int(carry_y)   # sensors report whole counts
            carry_x -= ix
            carry_y -= iy
            stick.add_counts(ix, iy)
        out = stick.tick(dt)
        ry, rp = game_turn_rate(out[0], out[1], cfg)
        yaw += ry * dt
        pitch += rp * dt
        t += dt
    return yaw, pitch, out


class TestDistance(unittest.TestCase):
    def setUp(self):
        self.cfg = StickConfig(mouse_dpi=800, cm_per_360=35, max_turn_deg_s=400,
                               game_deadzone=0.12, game_curve_exponent=1.0)

    def swipe(self, cm, over_s, cfg=None):
        cfg = cfg or self.cfg
        counts = cm / 2.54 * cfg.mouse_dpi
        motion = lambda t: (counts / over_s if t < over_s else 0.0, 0.0)
        return simulate(cfg, motion, over_s + 0.5, )

    def test_slow_swipe_turns_exact_angle(self):
        # 5 cm over 1 s = ~51 deg at 35 cm/360; well under max turn speed.
        yaw, _, out = self.swipe(5, 1.0)
        self.assertAlmostEqual(yaw, 5 / 35 * 360, delta=0.5)
        self.assertEqual(out, (0.0, 0.0))  # stick re-centred, no drift

    def test_micro_adjust_survives_deadzone(self):
        # 1 mm nudge = ~1 deg. Without deadzone lift this would turn 0.
        yaw, _, _ = self.swipe(0.1, 0.2)
        self.assertAlmostEqual(yaw, 0.1 / 35 * 360, delta=0.1)

    def test_quadratic_curve_is_inverted(self):
        cfg = StickConfig(**{**self.cfg.__dict__, "game_curve_exponent": 2.0})
        yaw, _, _ = self.swipe(5, 1.0, cfg)
        self.assertAlmostEqual(yaw, 5 / 35 * 360, delta=0.5)

    def test_fast_flick_lands_with_carryover(self):
        # 3 cm in 50 ms = 617 deg/s requested vs 400 max -> saturates.
        yaw, _, _ = self.swipe(3, 0.05)
        self.assertAlmostEqual(yaw, 3 / 35 * 360, delta=0.5)

    def test_carryover_cap_limits_overspin(self):
        cfg = StickConfig(**{**self.cfg.__dict__, "carryover_max_deg": 0})
        yaw, _, _ = self.swipe(3, 0.05, cfg)
        self.assertLess(yaw, 3 / 35 * 360 - 5)   # overflow dropped, by design

    def test_diagonal_keeps_direction_and_pitch_ratio(self):
        cfg = StickConfig(**{**self.cfg.__dict__, "pitch_ratio": 0.6})
        c = 4 / 2.54 * 800
        yaw, pitch, _ = simulate(cfg, lambda t: (c, -c) if t < 1 else (0, 0), 1.5)
        want = 4 / 35 * 360
        self.assertAlmostEqual(yaw, want, delta=0.5)
        self.assertAlmostEqual(pitch, want, delta=0.5)   # -dy = mouse up = look up

    def test_output_inside_unit_circle(self):
        stick = MouseStick(self.cfg)
        stick.add_counts(50000, 50000)
        x, y = stick.tick(0.002)
        self.assertLessEqual(math.hypot(x, y), 1.0 + 1e-9)


class TestMapper(unittest.TestCase):
    def cfg(self):
        return normalize({
            "left_stick": {"up": "W", "down": "S", "left": "A", "right": "D",
                           "walk_key": "LALT", "walk_scale": 0.5},
            "dpad": {"up": "UP", "down": "DOWN", "left": "LEFT", "right": "RIGHT"},
            "buttons": {"CROSS": ["SPACE"], "R1": ["E"]},
            "triggers": {"L2": ["MOUSE2"], "RT": ["MOUSE1"]},
        })

    def test_playstation_names_fold_in(self):
        c = self.cfg()
        self.assertEqual(c["buttons"], {"A": ["SPACE"], "RB": ["E"]})
        self.assertEqual(c["triggers"], {"LT": ["MOUSE2"], "RT": ["MOUSE1"]})
        self.assertEqual(display_name("RT", "ds4"), "R2")
        self.assertEqual(display_name("RT", "xbox"), "RT")

    def test_wasd_diagonal_and_socd(self):
        s = apply_keys(GamepadState(), {"W": 1, "D": 2}, self.cfg())
        self.assertAlmostEqual(math.hypot(s.lx, s.ly), 1.0)
        s = apply_keys(GamepadState(), {"A": 1, "D": 2}, self.cfg())
        self.assertEqual(s.lx, 1.0)   # last pressed wins
        s = apply_keys(GamepadState(), {"W": 1, "LALT": 2}, self.cfg())
        self.assertEqual(s.ly, 0.5)

    def test_buttons_triggers_dpad(self):
        s = apply_keys(GamepadState(), {"SPACE": 1, "MOUSE1": 2, "UP": 3}, self.cfg())
        self.assertTrue(s.buttons["A"] and s.buttons["DUP"])
        self.assertEqual((s.lt, s.rt), (0.0, 1.0))


if __name__ == "__main__":
    unittest.main()
