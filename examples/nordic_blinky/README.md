# Nordic Blinky Example

This example demonstrates how to use the BLE IoT Device Testing Framework to test the Nordic Semiconductor BLE Blinky sample application.

## About the Nordic Blinky

The Nordic Blinky is a simple BLE application that provides:
- An LED that can be controlled remotely
- A button whose state can be read or monitored via notifications

This is a common example for Nordic Semiconductor's nRF5x series of BLE SoCs. See the [official documentation](https://developer.nordicsemi.com/nRF_Connect_SDK/doc/latest/nrf/samples/bluetooth/peripheral_lbs/README.html) for more details.

## Running the Example Tests

Once you have the Nordic Blinky sample running on your device, you can run the tests as follows:

```bash
# Run with interactive device selection
test-a-ble -i --test-dir test_a_ble/examples/nordic_blinky/tests

# Run specific tests
test-a-ble --name "Nordic_Blinky" --test-dir test_a_ble/examples/nordic_blinky/tests --test test_led_toggle

# Run all tests
test-a-ble --address XX:XX:XX:XX:XX:XX --test-dir test_a_ble/examples/nordic_blinky/tests --test all
```

## Test Descriptions

- **LED Toggle Test**: Tests the ability to turn the LED on and off remotely
- **Button Press Test**: Tests receiving notifications when the button is pressed and released
- **LED-Button Interaction Test**: Demonstrates a more complex interaction, controlling the LED based on button presses

## Customizing for Your Device

If your Nordic device has a different name or uses different UUIDs for the LED Button Service, you may need to modify the configuration in `config.py`.
