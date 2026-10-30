"""Virtual gamepad output via vgamepad / ViGEmBus.

Two backends behind one tiny interface (apply(state) / close()):
  - XboxOutput : virtual Xbox 360 pad (XInput). Best compatibility, incl. Game Pass.
  - DS4Output  : virtual DualShock 4 pad. For games that want PlayStation prompts.

Both consume the same normalized GamepadState, so switching between them at
runtime is just swapping which object the main loop holds.
"""

import vgamepad as vg


class XboxOutput:
    mode = "xbox"

    def __init__(self):
        self.gp = vg.VX360Gamepad()
        B = vg.XUSB_BUTTON
        # logical name -> XInput button flag
        self._btn = {
            "A": B.XUSB_GAMEPAD_A,
            "B": B.XUSB_GAMEPAD_B,
            "X": B.XUSB_GAMEPAD_X,
            "Y": B.XUSB_GAMEPAD_Y,
            "LB": B.XUSB_GAMEPAD_LEFT_SHOULDER,
            "RB": B.XUSB_GAMEPAD_RIGHT_SHOULDER,
            "BACK": B.XUSB_GAMEPAD_BACK,
            "START": B.XUSB_GAMEPAD_START,
            "GUIDE": B.XUSB_GAMEPAD_GUIDE,
            "LS": B.XUSB_GAMEPAD_LEFT_THUMB,
            "RS": B.XUSB_GAMEPAD_RIGHT_THUMB,
            "DUP": B.XUSB_GAMEPAD_DPAD_UP,
            "DDOWN": B.XUSB_GAMEPAD_DPAD_DOWN,
            "DLEFT": B.XUSB_GAMEPAD_DPAD_LEFT,
            "DRIGHT": B.XUSB_GAMEPAD_DPAD_RIGHT,
        }

    def apply(self, s):
        gp = self.gp
        gp.left_joystick_float(x_value_float=s.lx, y_value_float=s.ly)
        gp.right_joystick_float(x_value_float=s.rx, y_value_float=s.ry)
        gp.left_trigger_float(value_float=s.lt)
        gp.right_trigger_float(value_float=s.rt)
        for name, flag in self._btn.items():
            if s.buttons.get(name):
                gp.press_button(button=flag)
            else:
                gp.release_button(button=flag)
        gp.update()

    def close(self):
        try:
            self.gp.reset()
            self.gp.update()
        except Exception:
            pass


class DS4Output:
    mode = "ds4"

    def __init__(self):
        self.gp = vg.VDS4Gamepad()
        B = vg.DS4_BUTTONS
        D = vg.DS4_DPAD_DIRECTIONS
        self._dpad_dirs = D
        # DS4 face buttons map to Xbox positions: A=Cross, B=Circle,
        # X=Square, Y=Triangle.
        self._btn = {
            "A": B.DS4_BUTTON_CROSS,
            "B": B.DS4_BUTTON_CIRCLE,
            "X": B.DS4_BUTTON_SQUARE,
            "Y": B.DS4_BUTTON_TRIANGLE,
            "LB": B.DS4_BUTTON_SHOULDER_LEFT,
            "RB": B.DS4_BUTTON_SHOULDER_RIGHT,
            "BACK": B.DS4_BUTTON_SHARE,
            "START": B.DS4_BUTTON_OPTIONS,
            "LS": B.DS4_BUTTON_THUMB_LEFT,
            "RS": B.DS4_BUTTON_THUMB_RIGHT,
        }
        # GUIDE -> PS button is a special call on vgamepad.

    def apply(self, s):
        gp = self.gp
        gp.left_joystick_float(x_value_float=s.lx, y_value_float=s.ly)
        gp.right_joystick_float(x_value_float=s.rx, y_value_float=s.ry)
        gp.left_trigger_float(value_float=s.lt)
        gp.right_trigger_float(value_float=s.rt)

        for name, flag in self._btn.items():
            if s.buttons.get(name):
                gp.press_button(button=flag)
            else:
                gp.release_button(button=flag)

        # DS4 d-pad is a direction enum, not 4 buttons.
        gp.directional_pad(direction=self._dpad_direction(s))

        # PS / GUIDE button.
        try:
            if s.buttons.get("GUIDE"):
                gp.press_special_button(special_button=vg.DS4_SPECIAL_BUTTONS.DS4_SPECIAL_BUTTON_PS)
            else:
                gp.release_special_button(special_button=vg.DS4_SPECIAL_BUTTONS.DS4_SPECIAL_BUTTON_PS)
        except Exception:
            pass

        gp.update()

    def _dpad_direction(self, s):
        D = self._dpad_dirs
        up, down = s.buttons.get("DUP"), s.buttons.get("DDOWN")
        left, right = s.buttons.get("DLEFT"), s.buttons.get("DRIGHT")
        if up and left:
            return D.DS4_BUTTON_DPAD_NORTHWEST
        if up and right:
            return D.DS4_BUTTON_DPAD_NORTHEAST
        if down and left:
            return D.DS4_BUTTON_DPAD_SOUTHWEST
        if down and right:
            return D.DS4_BUTTON_DPAD_SOUTHEAST
        if up:
            return D.DS4_BUTTON_DPAD_NORTH
        if down:
            return D.DS4_BUTTON_DPAD_SOUTH
        if left:
            return D.DS4_BUTTON_DPAD_WEST
        if right:
            return D.DS4_BUTTON_DPAD_EAST
        return D.DS4_BUTTON_DPAD_NONE

    def close(self):
        try:
            self.gp.reset()
            self.gp.update()
        except Exception:
            pass


def make_output(mode):
    """Factory: 'xbox' or 'ds4' -> an output backend instance."""
    if mode == "ds4":
        return DS4Output()
    return XboxOutput()
