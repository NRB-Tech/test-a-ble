"""Nordic Blinky Tests.

Tests for the Nordic Semiconductor BLE Blinky sample application.
These tests demonstrate controlling the LED and receiving button state notifications.
"""

import asyncio

from nordic_blinky.config import (
    BUTTON_PRESSED,
    BUTTON_RELEASED,
    CHAR_BUTTON,
    CHAR_LED,
    LED_OFF,
    LED_ON,
)

from test_a_ble.ble_manager import BLEManager
from test_a_ble.test_context import TestContext, TestFailure, ble_test, ble_test_class


@ble_test_class("Blinky Tests")
class BlinkyTests:
    """Tests for the Nordic Semiconductor BLE Blinky sample application.

    These tests demonstrate controlling the LED and receiving button state notifications.
    """

    async def setUp(self, _ble_manager: BLEManager, test_context: TestContext):
        """Set up the test environment."""
        test_context.debug("Setting up the test environment")

    async def tearDown(self, _ble_manager: BLEManager, test_context: TestContext):
        """Tear down the test environment."""
        test_context.debug("Tearing down the test environment")

    @ble_test("Toggle LED On and Off")
    async def test_led_toggle(self, ble_manager: BLEManager, test_context: TestContext):
        """Test toggling the LED on and off."""
        test_context.debug("Starting LED toggle test")

        # Turn LED on
        test_context.print("Starting LED toggle test - we'll turn the LED ON and OFF")
        test_context.debug(f"Writing value {LED_ON.hex()} to characteristic {CHAR_LED}")
        await ble_manager.write_characteristic(CHAR_LED, LED_ON)
        await asyncio.sleep(0.5)  # Add a small delay to ensure LED state has time to change
        test_context.debug("Waiting for LED state to stabilize")

        # Ask user to verify with ability to indicate failure
        test_context.debug("Requesting user verification of LED ON state")
        response = test_context.prompt_user("Is the LED ON? (y/n)")
        test_context.debug(f"User response for LED ON: {response}")

        if response.lower() not in ["y", "yes"]:
            test_context.error("LED ON test failed - user reported LED not turning on")
            test_context.warning("Check device power and LED connections")
            raise TestFailure("User reported LED did not turn on")

        test_context.debug("LED ON verified by user")
        test_context.print("LED ON state verified!")

        # Turn LED off
        test_context.debug(f"Writing value {LED_OFF.hex()} to characteristic {CHAR_LED}")
        await ble_manager.write_characteristic(CHAR_LED, LED_OFF)
        await asyncio.sleep(0.5)  # Add a small delay to ensure LED state has time to change
        test_context.debug("Waiting for LED state to stabilize")

        # Ask user to verify with ability to indicate failure
        test_context.debug("Requesting user verification of LED OFF state")
        response = test_context.prompt_user("Is the LED OFF? (y/n)")
        test_context.debug(f"User response for LED OFF: {response}")

        if response.lower() not in ["y", "yes"]:
            test_context.error("LED OFF test failed - user reported LED not turning off")
            test_context.warning("Check device power and LED circuit")
            raise TestFailure("User reported LED did not turn off")

        test_context.debug("LED OFF verified by user")
        test_context.print("LED OFF state verified!")
        test_context.print("LED toggle test completed successfully")

    @ble_test("Button Press and Release Notification")
    async def test_button_press(self, ble_manager: BLEManager, test_context: TestContext):
        """Test receiving button press notifications."""
        test_context.debug("Starting button press test")

        # First check the current button state
        test_context.debug("Reading current button state")
        current_button_state = await ble_manager.read_characteristic(CHAR_BUTTON)
        test_context.debug(f"Current button state: {current_button_state.hex()}")

        # If the button is already pressed, ask the user to release it first
        if current_button_state == BUTTON_PRESSED:
            test_context.warning("Button is already pressed, must be released to start test")

            # Wait for button release
            test_context.debug("Waiting for initial button release")
            test_context.print_formatted_box(
                "WAITING FOR NOTIFICATION",
                ["Button is currently pressed. Please RELEASE the button before starting the test."],
            )
            await test_context.wait_for_notification_interactive(
                characteristic_uuid=CHAR_BUTTON,
                expected_value=BUTTON_RELEASED,
                timeout=15.0,
            )
            test_context.debug("Button released successfully, continuing with test")
            await asyncio.sleep(0.5)  # Brief pause

        # Now wait for button press
        test_context.debug("Waiting for button press")
        test_context.debug(f"Watching characteristic {CHAR_BUTTON} for value {BUTTON_PRESSED.hex()}")
        test_context.print_formatted_box(
            "WAITING FOR NOTIFICATION",
            ["Please PRESS the button on the device to demonstrate BLE notifications."],
        )
        press_result = await test_context.wait_for_notification_interactive(
            characteristic_uuid=CHAR_BUTTON,
            expected_value=BUTTON_PRESSED,
            timeout=15.0,
        )

        # Button press detected
        test_context.debug(f"Received button press notification: {press_result['value'].hex()}")
        test_context.print("Detected BUTTON PRESS event")

        # Brief pause to let user see the feedback
        await asyncio.sleep(0.5)

        # Now wait for button release
        test_context.debug("Waiting for button release")
        test_context.debug(f"Watching characteristic {CHAR_BUTTON} for value {BUTTON_RELEASED.hex()}")
        test_context.print_formatted_box(
            "WAITING FOR NOTIFICATION",
            ["Now please RELEASE the button to complete the test."],
        )
        await test_context.wait_for_notification_interactive(
            characteristic_uuid=CHAR_BUTTON,
            expected_value=BUTTON_RELEASED,
            timeout=15.0,
        )

        # Button release detected
        test_context.print("Detected BUTTON RELEASE event")

        # Successfully detected both events
        test_context.debug("Successfully detected both button press and release")
        test_context.print("Button press/release test completed successfully")

    @ble_test("LED and Button Interaction")
    async def test_led_button_interaction(self, ble_manager: BLEManager, test_context: TestContext):
        """Test LED control based on button press."""
        test_context.debug("Starting LED and button interaction test")

        # Turn LED off initially
        test_context.debug("Setting LED to OFF state initially")
        test_context.debug(f"Writing value {LED_OFF.hex()} to characteristic {CHAR_LED}")
        await ble_manager.write_characteristic(CHAR_LED, LED_OFF)
        await asyncio.sleep(0.5)
        test_context.debug("Waiting for LED state to stabilize")

        # Use the updated helper method to wait for button press
        test_context.debug("Waiting for button press to turn on LED")
        test_context.print_formatted_box(
            "WAITING FOR NOTIFICATION",
            ["Press and HOLD the button on the device.\nThe LED should remain OFF until you press the button."],
        )
        press_result = await test_context.wait_for_notification_interactive(
            characteristic_uuid=CHAR_BUTTON,
            expected_value=BUTTON_PRESSED,
            timeout=15.0,
        )

        # If we get here, button press was successful
        test_context.print("Detected BUTTON PRESS event")
        test_context.debug(f"Button press notification value: {press_result['value'].hex()}")

        # Turn on LED when button is pressed
        test_context.debug("Setting LED to ON state")
        test_context.debug(f"Writing value {LED_ON.hex()} to characteristic {CHAR_LED}")
        await ble_manager.write_characteristic(CHAR_LED, LED_ON)
        await asyncio.sleep(0.5)  # Give the LED time to change

        # Ask user to verify LED state with feedback
        test_context.debug("Requesting user verification of LED ON state")
        response = test_context.prompt_user("Is the LED ON? (y/n)")
        test_context.debug(f"User response for LED ON: {response}")

        if response.lower() not in ["y", "yes"]:
            test_context.debug("User reported LED did not turn on")
            test_context.error("LED ON verification failed during button press")
            test_context.warning("Check if button press was registered correctly")
            # Turn off LED before ending test
            await ble_manager.write_characteristic(CHAR_LED, LED_OFF)
            raise TestFailure("User reported LED did not turn on")

        # Now prompt user to release button and wait for release notification
        test_context.debug("Waiting for button release to turn off LED")
        test_context.print_formatted_box(
            "WAITING FOR NOTIFICATION",
            ["RELEASE the button now.\nWhen you release the button, the LED should turn OFF."],
        )
        await test_context.wait_for_notification_interactive(
            characteristic_uuid=CHAR_BUTTON,
            expected_value=BUTTON_RELEASED,
            timeout=15.0,
        )

        # If we get here, button release was successful
        test_context.print("Detected BUTTON RELEASE event")

        # Turn off LED when button is released
        test_context.debug("Setting LED to OFF state")
        test_context.debug(f"Writing value {LED_OFF.hex()} to characteristic {CHAR_LED}")
        await ble_manager.write_characteristic(CHAR_LED, LED_OFF)
        await asyncio.sleep(0.5)  # Give the LED time to change

        # Ask user to verify LED state with feedback
        test_context.debug("Requesting user verification of LED OFF state")
        led_off_response = test_context.prompt_user("Is the LED OFF? (y/n)")
        test_context.debug(f"User response for LED OFF: {led_off_response}")

        if led_off_response.lower() not in ["y", "yes"]:
            test_context.debug("User reported LED did not turn off")
            test_context.error("LED OFF verification failed after button release")
            raise TestFailure("User reported LED did not turn off")

        # Test passed - success is implicit
        test_context.debug("LED successfully controlled by button state")
        test_context.print("LED and button interaction test completed successfully")
