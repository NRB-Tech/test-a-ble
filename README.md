# Test-a-BLE: A BLE testing framework

[![PyPI version](https://img.shields.io/pypi/v/test-a-ble.svg)](https://pypi.org/project/test-a-ble/)
[![Python Versions](https://img.shields.io/pypi/pyversions/test-a-ble.svg)](https://pypi.org/project/test-a-ble/)
[![Build Status](https://github.com/nrb-tech/test-a-ble/actions/workflows/python-package.yml/badge.svg)](https://github.com/nrb-tech/test-a-ble/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Documentation Status](https://readthedocs.org/projects/test-a-ble/badge/?version=latest)](https://test-a-ble.readthedocs.io/en/latest/?badge=latest)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A flexible cross platform python framework for testing Bluetooth Low Energy (BLE) IoT devices, supporting both interactive and automated testing.

## Features

- Discover and connect to BLE devices
- Interactive device selection, or specify name or address
- Write tests in Python
- Support for common testing patterns:
  - Write to device and expect a response
  - Write to device, prompt user for interaction, then expect a response
  - Prompt user for interaction and expect a notification
- Automated test discovery and execution
- Record test duration
- Detailed logging of test operations
- Read and write to characteristics
- Subscribe to notifications
- Advanced notification validation with custom lambda functions
- Support for function-based and class-based tests
- Interactive test mode with user prompts

## Installation

```bash
pip install test-a-ble
```

## Usage

### Basic Usage

```bash
# Run all tests in the current directory with interactive device discovery (default)
test-a-ble

# Connect to a device by address and run all tests in the current directory
test-a-ble --address 00:11:22:33:44:55

# Connect to a device by name and run a specific test module or function
test-a-ble --name "My Device" test_module.test_function

# Run tests from a specific file path
test-a-ble path/to/test_file.py

# Run all tests in a specific directory
test-a-ble path/to/test_directory

# Run tests in a directory specified with dot notation (converts to path)
test-a-ble package.module.submodule

# Run a specific test file using dot notation
test-a-ble package.module.test_file

# Run a specific test class or function using dot notation
test-a-ble package.module.test_file.TestClass
test-a-ble package.module.test_file.test_function

# Run tests with wildcard patterns using dot notation
test-a-ble package.module.submodule.*
test-a-ble package.module.*_file
test-a-ble package.module.test_file.*

# Run all tests in a specific module using wildcard
test-a-ble test_module.*

# Run all tests in a nested module using wildcard
test-a-ble package.module.*

# Run with verbose logging
test-a-ble --address 00:11:22:33:44:55 --verbose test_module
```

### Command Line Options

```
usage: test-a-ble [-h] [--address ADDRESS] [--name NAME] [--scan-timeout SCAN_TIMEOUT]
                  [--verbose] [--log-file LOG_FILE]
                  [test_specifiers ...]

BLE IoT Device Testing Tool - Discovers and runs tests for BLE devices. If no device
address or name is provided, interactive device discovery will be used.

positional arguments:
  test_specifiers       Test specifiers in unittest-style format. Examples:
                        test_module # Run all tests in a module
                        test_module.test_function # Run a specific test function
                        path/to/test_file.py # Run all tests in a file
                        path/to/directory # Run all tests in a directory all # Run all
                        tests in current directory (default)

options:
  -h, --help            show this help message and exit

Device Selection:
  --address ADDRESS, -a ADDRESS
                        MAC address of the BLE device
  --name NAME           Name of the BLE device
  --scan-timeout SCAN_TIMEOUT
                        Timeout for device scanning in seconds (default: 10.0)

Logging Options:
  --verbose, -v         Enable verbose logging (includes logs for all tests)
  --log-file LOG_FILE   Log file path (default: no file logging)
```

## Complete Test Example

Here's a simple but complete test example showing common BLE operations:

```python
from test_a_ble.test_context import ble_test, TestFailure, NotificationResult

@ble_test("Complete BLE Test Example")
async def test_complete_example(ble_manager, test_context):
    """
    A complete test example demonstrating:
    1. Subscribe to notifications
    2. Write to a characteristic
    3. Wait for/process notifications
    4. Read from a characteristic
    5. Wait for notification with user interaction
    """
    # Define your characteristic UUIDs
    led_char_uuid = "00001523-1212-efde-1523-785feabcd123"
    button_char_uuid = "00001524-1212-efde-1523-785feabcd123"

    # Step 1: Subscribe to button notifications first
    # (Ensures we receive notifications after writing to the LED)
    test_context.info("Subscribing to button characteristic for notifications")
    await test_context.subscribe_to_characteristic(button_char_uuid)

    # Step 2: Write to the LED characteristic (turn LED on)
    test_context.info("Writing to LED characteristic to turn it ON")
    led_on_value = bytes([0x01])
    await ble_manager.write_characteristic(led_char_uuid, led_on_value)

    # Step 3: Wait for any notification that might be triggered by the write operation
    # Allow exceptions to propagate to the test runner
    test_context.info("Waiting for any notifications triggered by the write operation")

    # Use process_collected_notifications=True to process any notifications
    # that might have been received during the write operation
    try:
        notification_result = await test_context.wait_for_notification(
            characteristic_uuid=button_char_uuid,
            timeout=2.0,  # Short timeout since we're just checking for immediate response
            expected_value=None,  # Accept any notification
            process_collected_notifications=True
        )
        test_context.info(f"Received notification after write: {notification_result['value'].hex()}")
    except TimeoutError:
        # In this specific case, we're OK with a timeout since notifications are optional
        test_context.info("No notification received after write operation - continuing")

    # Step 4: Read from the LED characteristic to confirm state
    led_state = await ble_manager.read_characteristic(led_char_uuid)
    test_context.info(f"Current LED state: {led_state.hex()}")

    if led_state != led_on_value:
        raise TestFailure(f"LED state {led_state.hex()} doesn't match expected {led_on_value.hex()}")

    # Step 5: Wait for notification with user interaction
    test_context.print_formatted_box(
        "USER ACTION REQUIRED",
        ["Please press the button on the device",
            "The test will continue when the button is pressed",
            "Type 's' to skip or 'f' to fail if the button doesn't work"]
    )

    # Define a validation function for the notification
    def validate_button_press(data: bytes):
        """Check if button was pressed (assumes 0x01 means 'pressed')"""
        if len(data) < 1:
            return NotificationResult.FAIL, "Invalid button notification format"

        button_state = data[0]
        if button_state == 0x01:
            return NotificationResult.MATCH, "Button was pressed"
        else:
            return NotificationResult.IGNORE, "Button not pressed yet"

    # Wait for a button press notification
    # Let exceptions like TestSkip, TestFailure propagate to the test runner
    result = await test_context.wait_for_notification_interactive(
        characteristic_uuid=button_char_uuid,
        timeout=30.0,
        expected_value=validate_button_press
    )

    # Successfully received button press notification
    test_context.print(f"Button press detected! Notification data: {result['value'].hex()}")

    # Step 6: Write to the LED characteristic again (turn LED off)
    test_context.info("Writing to LED characteristic to turn it OFF")
    led_off_value = bytes([0x00])
    await ble_manager.write_characteristic(led_char_uuid, led_off_value)

    # Wait for any notification that might be triggered by this write operation too
    # Allow the TimeoutError to propagate if appropriate for your test
    try:
        notification_result = await test_context.wait_for_notification(
            characteristic_uuid=button_char_uuid,
            timeout=2.0,
            expected_value=None,
            process_collected_notifications=True
        )
        test_context.info(f"Received notification after second write: {notification_result['value'].hex()}")
    except TimeoutError:
        # In this specific case, we're OK with a timeout since notifications are optional
        test_context.info("No notification received after second write operation")

    # Read the LED state again to confirm
    led_state = await ble_manager.read_characteristic(led_char_uuid)
    test_context.info(f"Final LED state: {led_state.hex()}")
```

## Writing Tests

Tests are written as Python functions decorated with `@ble_test` in modules starting with `test_`. Optionally, tests can be methods on a class, decorated with `@ble_test_class`.

### Test Decorator

The framework provides a decorator to mark test functions:

```python
from test_a_ble.test_context import ble_test

# Optionally, tests can be part of a class
@ble_test_class("Button class name")
class ButtonTests:

    async def setUp(self, ble_manager: BLEManager, test_context: TestContext):
        # Optionally, you can specify setUp, to run code before every test in the class starts
        pass

    async def tearDown(self, ble_manager: BLEManager, test_context: TestContext):
        # or tear down, to run code after every test in the class finishes
        pass

    @ble_test("Button Press Test")  # Optional description
    async def test_button_press(self, ble_manager, test_context):
        # Test implementation here
        pass

    # If no description is provided, the function name is used
    @ble_test
    async def test_led_toggle(self, ble_manager, test_context):
        # Test implementation here
        pass
```

### Logging in Tests

The framework provides structured logging with different levels to help with debugging and observability. All logs are associated with the test that created them.

```python
# Different log levels - use these for diagnostic information
test_context.debug("Detailed debug information")
test_context.info("Normal informational message")
test_context.warning("Warning message")
test_context.error("Error message")
test_context.critical("Critical error message")

# General log method with custom level
test_context.log("Custom message", level="info")  # Default is "info"

# For user-facing output that should always be visible
test_context.print("This message will always display to the user")

# For formatted user interaction
test_context.print_formatted_box("TITLE", ["Line 1 of the message", "Line 2 of the message"])

# To prompt the user for input
user_response = test_context.prompt_user("Please do something and enter your observation")
```

When tests run:
1. Logs (debug, info, warning, etc.) are for diagnostic purposes
   - By default, only shown for failing tests
   - Shown for all tests with `--verbose`
2. Output from `test_context.print()` is always displayed to users
   - Clearly labeled as user output in the results
   - Always visible regardless of test outcome
3. Formatted boxes (`print_formatted_box`) provide clear user interaction points
   - Good for instructions, prompts, and test status

### Notification Handling and Subscription Management

Many BLE devices use the notification mechanism to send data to the client. The framework provides comprehensive tools for working with BLE notifications.

#### Subscribing to Notifications

Before receiving notifications, you need to subscribe to the relevant characteristic:

```python
# Subscribe to a characteristic for notifications
await test_context.subscribe_to_characteristic(
    characteristic_uuid="00002a37-0000-1000-8000-00805f9b34fb"  # Heart Rate Measurement
)
```

#### Basic Notification Waiting

The `wait_for_notification` method allows you to wait for a notification without user interaction:

```python
# Wait for any notification on a characteristic
result = await test_context.wait_for_notification(
    characteristic_uuid="00002a37-0000-1000-8000-00805f9b34fb",  # Heart Rate Measurement
    timeout=5.0,  # Timeout in seconds
    expected_value=None,  # Optional: expected value to match
    process_collected_notifications=True  # Process notifications collected during other operations
)

# Access the notification data
notification_value = result['value']
print(f"Received notification: {notification_value.hex()}")
```

This is useful for automated tests where you send a command to the device and expect a notification in response.

#### Interactive Notification Waiting

For tests requiring user interaction with the device, use `wait_for_notification_interactive`:

```python
# Wait for notification with user interaction
test_context.print("Please press the button on the device.")
result = await test_context.wait_for_notification_interactive(
    characteristic_uuid="00002a37-0000-1000-8000-00805f9b34fb",
    timeout=30.0,  # Longer timeout for user interaction
    expected_value=None  # Optional: expected value to match
)

# Access the notification data if successful
notification_value = result['value']
print(f"Received notification: {notification_value.hex()}")
```

This will display a prompt to the user allowing them to:
- Wait for the notification to arrive automatically
- Type 's' or 'skip' to skip the test
- Type 'f' or 'fail' to fail the test, in the event the device interaction did not produce the expected result
- Type 'd' to see debug information about received notifications

#### Validating Notification Values

Both notification waiting methods accept an optional `expected_value` parameter that can validate the received notification. If not provided, or `None` passed, it will return the first notification received. Alternatively you can provide a value or function in the parameter to validate received notifications:

```python
# Using an exact byte match
expected_value = bytes([0x06, 0x4B])  # Example expected format
result = await test_context.wait_for_notification(
    characteristic_uuid="00002a37-0000-1000-8000-00805f9b34fb",
    timeout=5.0,
    expected_value=expected_value  # Must match exactly
)
```

For more complex validation, you can use a custom function:

```python
from test_a_ble.test_context import NotificationResult

# Define a custom validation function
def validate_heart_rate(data: bytes) -> Union[bool, NotificationResult, Tuple[NotificationResult, str]]:
    """Check if heart rate notification is valid"""
    if len(data) < 2:
        return NotificationResult.FAIL, "Invalid data format"

    heart_rate = data[1]  # Extract heart rate (simplified)

    if heart_rate > 70:
        return NotificationResult.MATCH  # This is what we're looking for
    elif heart_rate < 30:
        return NotificationResult.FAIL, f"Heart rate too low: {heart_rate} BPM"
    else:
        return NotificationResult.IGNORE  # Continue waiting, this isn't what we want

# Alternative simpler return format (True = match, False = ignore)
def simple_validate(data: bytes) -> bool:
    return data[0] == 0x01  # Return True if first byte is 0x01

# Wait for a notification that passes the validation
result = await test_context.wait_for_notification(
    characteristic_uuid="00002a37-0000-1000-8000-00805f9b34fb",
    timeout=10.0,
    expected_value=validate_heart_rate
)
```

The `NotificationResult` enum provides three possible return values for validation functions:

- `MATCH`: The notification matches criteria, consider the test passed
- `IGNORE`: The notification doesn't match criteria, continue waiting
- `FAIL`: The notification indicates a failure condition, fail the test

Your validation function can return:
- A boolean: `True` for match, `False` for ignore
- A `NotificationResult` enum value
- A tuple of `(NotificationResult, str)` where the string provides additional context or error messages

#### Error Handling

The notification waiting methods can raise several exceptions:

- `TimeoutError`: If no notification is received within the timeout period
- `TestFailure`: If a notification is received but doesn't match the expected value or indicates a failure condition
- `TestSkip`: If the user chooses to skip the test (only for interactive mode)
- `RuntimeError`: If there's an error subscribing to the characteristic

You can allow these exceptions to propagate to the test runner, which will handle them appropriately, but if needed these can be caught and handled:

```python
try:
    result = await test_context.wait_for_notification(
        characteristic_uuid="00002a37-0000-1000-8000-00805f9b34fb",
        timeout=5.0
    )
    test_context.info(f"Received notification: {result['value'].hex()}")
except TimeoutError:
    test_context.warning("No notification received within timeout")
    raise
except TestFailure as e:
    test_context.error(f"Notification validation failed: {str(e)}")
    raise
```

#### Advanced Notification Handling

For more complex scenarios, you can use the low-level notification API:

```python
# Subscribe to notifications and create a waiter
waiter = await test_context.create_notification_waiter(
    characteristic_uuid="00002a37-0000-1000-8000-00805f9b34fb",
    expected_value=lambda data: data[0] == 0x01
)

# Wait for the notification with a custom timeout
try:
    await asyncio.wait_for(waiter.complete_event.wait(), timeout=5.0)

    # Process results
    if waiter.matching_notification:
        print(f"Success! Received: {waiter.matching_notification.hex()}")
    elif waiter.failure_reason:
        print(f"Failed: {waiter.failure_reason}")
    else:
        print("No matching notification received")

except asyncio.TimeoutError:
    print("Timed out waiting for notification")
```

For even more control, you can work with the NotificationWaiter directly:

```python
# Subscribe to a characteristic and process notifications manually
await test_context.subscribe_to_characteristic(
    characteristic_uuid="00002a37-0000-1000-8000-00805f9b34fb"
)

# Create a custom notification waiter with validation logic
waiter = NotificationWaiter(
    characteristic_uuid="00002a37-0000-1000-8000-00805f9b34fb",
    expected_value=lambda data: (NotificationResult.MATCH
                                if data[0] == 0x01
                                else NotificationResult.IGNORE)
)

# Set the waiter for the existing subscription
subscription = test_context.notification_subscriptions["00002a37-0000-1000-8000-00805f9b34fb"]
subscription.set_waiter(waiter)

# Wait for the notification using the waiter's event
await waiter.complete_event.wait()
```

#### Ensuring all notifications are caught

When a device responds to a write with a notification, it might be possible for a race condition to occur, where the notification is received before your test has started listening to it after the write. Alternatively, you may need to subscribe to the notification before the write is performed, otherwise the response may not be sent as notifications are not yet enabled. To avoid the possibility of these scenarios occuring, you can subscribe to notifications before the write is performed:

```python
# Subscribe to notifications before writing to the characteristic
await test_context.subscribe_to_characteristic(
    characteristic_uuid="00002a37-0000-1000-8000-00805f9b34fb"
)

# Write to a characteristic that triggers a notification response
await ble_manager.write_characteristic(
    characteristic_uuid="00002a38-0000-1000-8000-00805f9b34fb",
    value=bytes([0x01])
)

# Wait for notification with process_collected_notifications=True to catch any
# notifications that arrived between subscribing and setting up the wait
try:
    notification_result = await test_context.wait_for_notification(
        characteristic_uuid="00002a37-0000-1000-8000-00805f9b34fb",
        timeout=2.0,
        expected_value=lambda data: data[0] == 0x01,
        process_collected_notifications=True
    )

    print(f"Received notification: {notification_result['value'].hex()}")
except TimeoutError:
    print("No notification received within timeout period")

```

#### Automatic Cleanup

Notification subscriptions are automatically handled when calling the high-level notification waiting methods. The `unsubscribe_all()` method can be used to explicitly clean up subscriptions when needed:

```python
# Clean up notifications at the end of your test
await test_context.unsubscribe_all()
```

## Python Version Compatibility

The framework is compatible with Python 3.12+.

## Project-Specific structure

It is recommended that tests are implemented in a package, with global setup in `__init__.py`, characteristics defined in `config.py`, and tests in a `tests` subpackage. While this structure is not required, the framework's test discovery accomodates that structure, importing the main test package and scanning for tests in the `tests` subdirectory.

## Included Examples

### Nordic Blinky Example

The framework includes an example for testing the Nordic Semiconductor BLE Blinky sample application. This serves as a reference implementation and demonstrates how to structure your own tests.

The Nordic Blinky is a simple BLE application that provides:
- An LED that can be controlled remotely
- A button whose state can be read or monitored via notifications

#### Running the Nordic Blinky Example

Using the CLI:
```bash
# Run with automatic device discovery
test-a-ble test-a-ble/examples/nordic_blinky/tests

# Run with a specific device name
test-a-ble --name "Nordic_Blinky" test-a-ble/examples/nordic_blinky/tests

# Run specific test in the example directory
test-a-ble --address 12:34:56:78:90:AB test-a-ble/examples/nordic_blinky/tests/test_led.py

# Run all LED tests using wildcard pattern matching
test-a-ble test_led.*

# Run all tests in a specific test class
test-a-ble test_blinky.TestBlinkyCommunication.*
```

Or using the provided example script:
```bash
# Run with auto-discovery
python -m test_a_ble.examples.run_nordic_example

# Run with device name
python -m test_a_ble.examples.run_nordic_example Nordic_Blinky

# Run with device address
python -m test_a_ble.examples.run_nordic_example 12:34:56:78:90:AB
```

See the [example README](examples/nordic_blinky/README.md) for more details.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on our code of conduct and the process for submitting pull requests.
