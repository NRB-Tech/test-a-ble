"""
Nordic Blinky Example Configuration.

Configuration for the Nordic Semiconductor BLE Blinky sample application.
"""

# Device identification
DEVICE_NAME_PREFIX = "Nordic_Blinky"  # Default name, may vary

# The Nordic LED Button Service (LBS)
SERVICE_LBS = "00001523-1212-efde-1523-785feabcd123"

# Characteristics
CHAR_BUTTON = "00001524-1212-efde-1523-785feabcd123"  # Button state characteristic
CHAR_LED = "00001525-1212-efde-1523-785feabcd123"  # LED state characteristic

# Button state values
BUTTON_PRESSED = bytes([0x01])
BUTTON_RELEASED = bytes([0x00])

# LED state values
LED_ON = bytes([0x01])
LED_OFF = bytes([0x00])

# Friendly names for characteristics
CHARACTERISTIC_NAMES = {CHAR_BUTTON: "Button State", CHAR_LED: "LED State"}

# Friendly names for services
SERVICE_NAMES = {SERVICE_LBS: "LED Button Service"}

# Map human-readable names to UUIDs
SERVICES_BY_NAME = {v: k for k, v in SERVICE_NAMES.items()}
CHARACTERISTICS_BY_NAME = {v: k for k, v in CHARACTERISTIC_NAMES.items()}
