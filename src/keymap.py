"""Key names used in config.json -> Windows virtual-key codes."""

MOUSE_BUTTONS = ("MOUSE1", "MOUSE2", "MOUSE3", "MOUSE4", "MOUSE5")
WHEEL = ("WHEELUP", "WHEELDOWN")

VK = {
    "BACKSPACE": 0x08, "TAB": 0x09, "ENTER": 0x0D, "PAUSE": 0x13,
    "CAPSLOCK": 0x14, "ESC": 0x1B, "SPACE": 0x20,
    "PAGEUP": 0x21, "PAGEDOWN": 0x22, "END": 0x23, "HOME": 0x24,
    "LEFT": 0x25, "UP": 0x26, "RIGHT": 0x27, "DOWN": 0x28,
    "INSERT": 0x2D, "DELETE": 0x2E,
    "LSHIFT": 0xA0, "RSHIFT": 0xA1, "LCTRL": 0xA2, "RCTRL": 0xA3,
    "LALT": 0xA4, "RALT": 0xA5,
    "SEMICOLON": 0xBA, "EQUALS": 0xBB, "COMMA": 0xBC, "MINUS": 0xBD,
    "PERIOD": 0xBE, "SLASH": 0xBF, "GRAVE": 0xC0,
    "LBRACKET": 0xDB, "BACKSLASH": 0xDC, "RBRACKET": 0xDD, "QUOTE": 0xDE,
}
VK.update({chr(c): c for c in range(ord("A"), ord("Z") + 1)})
VK.update({str(d): 0x30 + d for d in range(10)})
VK.update({f"NUM{d}": 0x60 + d for d in range(10)})
VK.update({f"F{n}": 0x6F + n for n in range(1, 25)})


def is_valid(name):
    return name in VK or name in MOUSE_BUTTONS or name in WHEEL


def vk(name):
    return VK[name.upper()]
