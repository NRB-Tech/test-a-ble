"""Test function."""

import asyncio

from test_a_ble.ble_manager import BLEManager
from test_a_ble.test_context import TestContext, ble_test


@ble_test
async def test_function_1(ble_manager: BLEManager, test_context: TestContext):
    """Standalone test function."""
    print("Running test_function_1")
    await asyncio.sleep(0)  # Make sure it's a real coroutine
    pass


@ble_test
async def test_function_2(ble_manager: BLEManager, test_context: TestContext):
    """Standalone test function."""
    print("Running test_function_2")
    await asyncio.sleep(0)  # Make sure it's a real coroutine
    pass
