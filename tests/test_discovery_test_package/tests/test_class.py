"""Test class."""

import asyncio

from test_a_ble.ble_manager import BLEManager
from test_a_ble.test_context import TestContext, ble_test, ble_test_class


@ble_test_class
class TestClass:
    """Test class."""

    async def setUp(self, ble_manager: BLEManager, test_context: TestContext):
        """Set up the test."""
        print("Setting up the test")
        await asyncio.sleep(0)  # Make sure it's a real coroutine
        pass

    async def tearDown(self, ble_manager: BLEManager, test_context: TestContext):
        """Tear down the test."""
        print("Tearing down the test")
        await asyncio.sleep(0)  # Make sure it's a real coroutine
        pass

    # Define a proper async function that will be recognized as a coroutine function
    @ble_test
    async def test_method_1(self, ble_manager: BLEManager, test_context: TestContext):
        """Standalone test function."""
        print("Running test_method_1")
        await asyncio.sleep(0)  # Make sure it's a real coroutine
        pass

    @ble_test
    async def test_method_2(self, ble_manager: BLEManager, test_context: TestContext):
        """Standalone test function."""
        print("Running test_method_2")
        await asyncio.sleep(0)  # Make sure it's a real coroutine
