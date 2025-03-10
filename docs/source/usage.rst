Usage
=====

Command Line Interface
----------------------

Test-a-BLE provides a command-line interface for running tests:

.. code-block:: bash

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

Writing Tests
-------------

Test-a-BLE supports both function-based and class-based tests.

Function-based Tests
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    from test-a-ble import test

    @test
    def test_device_connection(ctx):
        """Test that we can connect to the device."""
        # ctx is a TestContext object that provides access to the device
        ctx.log.info("Connected to device")
        assert ctx.device is not None

Class-based Tests
~~~~~~~~~~~~~~~~~

.. code-block:: python

    from test-a-ble import TestCase

    class MyDeviceTests(TestCase):
        def test_read_characteristic(self):
            """Test that we can read a characteristic."""
            value = self.read_characteristic("00002a00-0000-1000-8000-00805f9b34fb")
            self.log.info(f"Read value: {value}")
            assert value is not None

        def test_write_characteristic(self):
            """Test that we can write to a characteristic."""
            self.write_characteristic("00002a00-0000-1000-8000-00805f9b34fb", b"test")
            self.log.info("Wrote to characteristic")

Common Testing Patterns
-----------------------

Write to device and expect a response:

.. code-block:: python

    @test
    def test_write_and_response(ctx):
        ctx.write_characteristic("00002a00-0000-1000-8000-00805f9b34fb", b"test")
        response = ctx.read_characteristic("00002a00-0000-1000-8000-00805f9b34fb")
        assert response == b"expected_response"

Write to device, prompt user for interaction, then expect a response:

.. code-block:: python

    @test
    def test_user_interaction(ctx):
        ctx.write_characteristic("00002a00-0000-1000-8000-00805f9b34fb", b"test")
        ctx.prompt_user("Please press the button on the device")
        response = ctx.read_characteristic("00002a00-0000-1000-8000-00805f9b34fb")
        assert response == b"button_pressed"

Prompt user for interaction and expect a notification:

.. code-block:: python

    @test
    def test_notification(ctx):
        ctx.subscribe_to_characteristic("00002a00-0000-1000-8000-00805f9b34fb")
        ctx.prompt_user("Please press the button on the device")
        notification = ctx.wait_for_notification("00002a00-0000-1000-8000-00805f9b34fb", timeout=5)
        assert notification == b"button_pressed"
