# Stick Shift

*Your mouse, shifted into a thumbstick.*

Keyboard + mouse → a virtual Xbox 360 or DualShock 4 controller, toggled with **F8**.
WASD = left stick, mouse = right stick, arrows = d-pad. While it's on, games see
only the controller (KBM is blocked), so they stay in controller mode.

> **Read first:** some multiplayer games (Call of Duty, Fortnite, Apex, …)
> treat KBM pretending to be a controller like a XIM or Cronus device. That's
> against their rules and can get you banned. Check the game's policy before
> using this online.

## Portable build (for test PCs)
`build_exe.bat` produces `dist/StickShift-portable.zip`: `StickShift.exe` (no Python
needed), the ViGEmBus driver installer, `Calibrate.bat`, `Start DS4 mode.bat` and
`QUICKSTART.txt`. Unzip it anywhere. On first run the exe offers to install the driver
(one admin prompt). `config.json` is saved next to the exe.

## Setup (from source)
1. `install.bat` (Python 3.10+; ViGEmBus installs on first run)
2. Windows: turn off **Enhance pointer precision** and leave pointer speed at 10.
3. In game: set the response curve to linear, turn off look acceleration, set the
   right-stick deadzone low, and put that value in `config.json` → `game_deadzone`.
4. `run.bat --calibrate` (measures the game's max turn speed and curve, saves them)
5. Set `mouse_dpi` and `cm_per_360` to your usual PC sens. Then `run.bat`, and press F8 in game.

## How mouse becomes stick (the part that makes it feel right)
A mouse controls **position**: move 1 cm and you turn a fixed angle, however fast
you moved. A stick controls **speed**: deflection sets a turn rate, and the game bends
it through a deadzone, a response curve and a max speed. `src/stick.py` bridges the two:

1. **Counts → angle.** Mouse counts become the degrees you meant to turn, using your
   `mouse_dpi` and `cm_per_360`.
2. **Angle → rate.** That angle is banked and paid out over `smoothing_ms` (≈1 game
   frame). Total turn out equals total mouse turn in, so distance is preserved, and the
   stick re-centers as soon as the mouse stops.
3. **Rate → deflection.** The rate is divided by the game's `max_turn_deg_s`, the
   response curve is undone, and the result is lifted past the inner deadzone. Without
   that lift, small micro-adjustments disappear.
4. **Saturation.** No stick can turn faster than the game's max speed. If a flick asks
   for more, the extra is carried over (up to `carryover_max_deg`), so it still lands,
   just a few ms late. A huge swipe beyond that is capped, like on a real controller.
   The startup line shows the cm/s where this kicks in.

`tests/test_stick.py` checks this end to end against a model of the game. A 5 cm
swipe turns the 51.4° that 35 cm/360 calls for, and a 1 mm nudge still turns about 1°.

## Menu mode (clicking settings normally)
While the Windows cursor is **visible** (menus, settings, desktop), the mouse is a
normal mouse again, and its clicks don't become LT/RT. Once gameplay hides the cursor,
the mouse goes back to being the right stick. For games that draw their own cursor, hold
`menu_mode.hold_key` (mouse button 5 by default) to get the normal mouse.
Some games switch to KBM prompts while you use the real mouse. Touching any stick
switches them back.

## Demo overlay
An always-on-top, click-through panel (F7 shows/hides it). It shows the current mode
(controller aim, menu mouse, or native KBM), both sticks with the aim trail and the
game's deadzone ring, turn rate asked for vs. what the stick can deliver (red at max),
carryover, triggers and buttons, with PlayStation names in DS4 mode. It draws over
borderless and windowed games (the Game Pass default); OBS display capture records it.
Set the position, scale and opacity under `overlay` in config.json, or start with `--no-overlay`.

## Bindings
`config.json` overrides `config.default.json`. Use either button-name set:
`A B X Y LB RB LT RT LS RS START BACK GUIDE` or
`CROSS CIRCLE SQUARE TRIANGLE L1 R1 L2 R2 L3 R3 OPTIONS SHARE PS`.
Keys: letters, digits, `F1`–`F24`, `SPACE LSHIFT LCTRL LALT TAB ESC UP…`,
`MOUSE1`–`MOUSE5`, `WHEELUP`, `WHEELDOWN`. Use `"output": "ds4"` for a PlayStation pad.
