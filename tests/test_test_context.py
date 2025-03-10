"""Tests for the TestContext class."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Note: We import classes with names starting with "Test" (like TestContext, TestStatus, etc.)
# which pytest would normally try to collect as test classes. To prevent this, we've configured
# pytest in pyproject.toml with a python_classes pattern that excludes these specific classes.
from test_a_ble.ble_manager import BLEManager
from test_a_ble.test_context import (
    NotificationResult,
    NotificationSubscription,
    NotificationWaiter,
    TestContext,
    TestException,
    TestFailure,
    TestSkip,
    TestStatus,
    ble_test,
    ble_test_class,
)


def test_ble_test_decorator():
    """Test the ble_test decorator."""

    @ble_test("Test description")
    def test_function():
        pass

    assert hasattr(test_function, "_is_ble_test")
    assert test_function._is_ble_test is True
    assert hasattr(test_function, "_test_description")
    assert test_function._test_description == "Test description"

    # Test without description
    @ble_test
    def test_function2():
        pass

    assert hasattr(test_function2, "_is_ble_test")
    assert test_function2._is_ble_test is True
    assert hasattr(test_function2, "_test_description")
    assert test_function2._test_description is None


def test_ble_test_class_decorator():
    """Test the ble_test_class decorator."""

    @ble_test_class("Test class description")
    class TestClass:
        pass

    assert hasattr(TestClass, "_is_test_class")
    assert TestClass._is_test_class is True
    assert hasattr(TestClass, "_test_description")
    assert TestClass._test_description == "Test class description"

    # Test without description
    @ble_test_class
    class TestClass2:
        pass

    assert hasattr(TestClass2, "_is_test_class")
    assert TestClass2._is_test_class is True
    assert hasattr(TestClass2, "_test_description")
    assert TestClass2._test_description is None


@pytest.fixture
def mock_ble_manager():
    """Create a mock BLEManager for testing."""
    mock_manager = MagicMock(spec=BLEManager)
    mock_manager.connect_to_device = AsyncMock(return_value=True)
    mock_manager.disconnect = AsyncMock()
    mock_manager.read_characteristic = AsyncMock(return_value=bytearray([0x01, 0x02, 0x03]))
    mock_manager.write_characteristic = AsyncMock()
    mock_manager.subscribe_to_characteristic = AsyncMock()
    mock_manager.unsubscribe_from_characteristic = AsyncMock()
    return mock_manager


@pytest.fixture
def test_context(mock_ble_manager):
    """Create a TestContext instance for testing."""
    return TestContext(mock_ble_manager)


def test_init(test_context, mock_ble_manager):
    """Test initialization of TestContext."""
    assert test_context.ble_manager == mock_ble_manager
    assert test_context.current_test is None
    assert isinstance(test_context.test_results, dict)
    assert isinstance(test_context.notification_subscriptions, dict)


@pytest.mark.asyncio
async def test_start_end_test(test_context):
    """Test starting and ending a test."""
    # Start a test
    test_context.start_test("test_example")
    assert test_context.current_test == "test_example"
    assert "test_example" in test_context.test_results
    assert test_context.test_results["test_example"]["status"] == TestStatus.RUNNING.value

    # End the test
    result = test_context.end_test(TestStatus.PASS, "Test passed")
    assert test_context.current_test is None
    assert test_context.test_results["test_example"]["status"] == TestStatus.PASS.value
    assert test_context.test_results["test_example"]["message"] == "Test passed"
    assert "duration" in test_context.test_results["test_example"]
    assert result == test_context.test_results["test_example"]


@pytest.mark.asyncio
async def test_logging(test_context):
    """Test logging methods."""
    # Start a test to capture logs
    test_context.start_test("test_logging")

    # Test different log levels
    test_context.debug("Debug message")
    test_context.info("Info message")
    test_context.warning("Warning message")
    test_context.error("Error message")
    test_context.critical("Critical message")

    # Check that logs were captured
    logs = test_context.test_results["test_logging"]["logs"]
    assert len(logs) == 5
    assert logs[0]["level"] == "DEBUG"
    assert logs[0]["message"] == "Debug message"
    assert logs[1]["level"] == "INFO"
    assert logs[1]["message"] == "Info message"
    assert logs[2]["level"] == "WARNING"
    assert logs[2]["message"] == "Warning message"
    assert logs[3]["level"] == "ERROR"
    assert logs[3]["message"] == "Error message"
    assert logs[4]["level"] == "CRITICAL"
    assert logs[4]["message"] == "Critical message"


@pytest.mark.asyncio
async def test_subscribe_to_characteristic(test_context, mock_ble_manager):
    """Test subscribing to a characteristic."""
    char_uuid = "00002a37-0000-1000-8000-00805f9b34fb"  # Heart Rate Measurement

    # Subscribe to a characteristic
    await test_context.subscribe_to_characteristic(char_uuid)

    # Check that the subscription was created
    assert char_uuid in test_context.notification_subscriptions
    assert isinstance(test_context.notification_subscriptions[char_uuid], NotificationSubscription)

    # Check that the BLE manager was called
    mock_ble_manager.subscribe_to_characteristic.assert_called_once_with(
        char_uuid, test_context.notification_subscriptions[char_uuid].on_notification
    )


@pytest.mark.asyncio
async def test_create_notification_waiter(test_context):
    """Test creating a notification waiter."""
    char_uuid = "00002a37-0000-1000-8000-00805f9b34fb"  # Heart Rate Measurement
    expected_value = bytearray([0x01, 0x02, 0x03])

    # First subscribe to the characteristic
    await test_context.subscribe_to_characteristic(char_uuid)

    # Create a notification waiter
    waiter = await test_context.create_notification_waiter(char_uuid, expected_value)

    # Check that the waiter was created correctly
    assert isinstance(waiter, NotificationWaiter)
    assert waiter.characteristic_uuid == char_uuid
    assert waiter.expected_value == expected_value


@pytest.mark.asyncio
async def test_wait_for_notification(test_context):
    """Test waiting for a notification."""
    char_uuid = "00002a37-0000-1000-8000-00805f9b34fb"  # Heart Rate Measurement
    expected_value = bytearray([0x01, 0x02, 0x03])

    # Mock the create_notification_waiter method
    with patch.object(test_context, "create_notification_waiter") as mock_create_waiter:
        # Create a mock waiter
        mock_waiter = MagicMock()
        mock_waiter.complete_event = asyncio.Event()
        mock_waiter.complete_event.set()  # Set the event to simulate notification received
        mock_waiter.matching_notification = expected_value
        mock_waiter.failure_reason = None
        mock_create_waiter.return_value = mock_waiter

        # Mock the handle_notification_waiter_result method
        with patch.object(test_context, "handle_notification_waiter_result") as mock_handle_result:
            mock_handle_result.return_value = {
                "success": True,
                "data": expected_value,
                "timeout": False,
            }

            # Wait for a notification
            result = await test_context.wait_for_notification(char_uuid, timeout=1.0, expected_value=expected_value)

            # Check that the methods were called correctly - using call() to match exactly how it was called
            from unittest.mock import call

            assert mock_create_waiter.call_args == call(char_uuid, expected_value, True)
            mock_handle_result.assert_called_once_with(mock_waiter, 1.0)

            # Check the result
            assert result["success"] is True
            assert result["data"] == expected_value
            assert result["timeout"] is False


@pytest.mark.asyncio
async def test_cleanup_tasks(test_context, mock_ble_manager):
    """Test cleaning up tasks."""
    # Add some notification subscriptions
    char_uuid1 = "00002a37-0000-1000-8000-00805f9b34fb"  # Heart Rate Measurement
    char_uuid2 = "00002a38-0000-1000-8000-00805f9b34fb"  # Another characteristic

    await test_context.subscribe_to_characteristic(char_uuid1)
    await test_context.subscribe_to_characteristic(char_uuid2)

    # Clean up tasks
    await test_context.cleanup_tasks()

    # Check that unsubscribe was called for each subscription
    assert mock_ble_manager.unsubscribe_from_characteristic.call_count == 2
    mock_ble_manager.unsubscribe_from_characteristic.assert_any_call(char_uuid1)
    mock_ble_manager.unsubscribe_from_characteristic.assert_any_call(char_uuid2)

    # Check that the subscriptions were cleared
    assert len(test_context.notification_subscriptions) == 0


@pytest.mark.asyncio
async def test_get_test_summary(test_context):
    """Test getting the test summary."""
    # Add some test results
    test_context.start_test("test_1")
    test_context.end_test(TestStatus.PASS, "Test 1 passed")

    test_context.start_test("test_2")
    test_context.end_test(TestStatus.FAIL, "Test 2 failed")

    test_context.start_test("test_3")
    test_context.end_test(TestStatus.SKIP, "Test 3 skipped")

    # Get the test summary
    summary = test_context.get_test_summary()

    # Check the summary
    assert summary["total_tests"] == 3
    assert summary["passed_tests"] == 1
    assert summary["failed_tests"] == 1
    # The get_test_summary method doesn't include a skipped_tests key
    # Count skipped tests manually
    skipped_tests = sum(1 for result in summary["results"].values() if result["status"] == TestStatus.SKIP.value)
    assert skipped_tests == 1
    assert "results" in summary
    assert len(summary["results"]) == 3
    assert "test_1" in summary["results"]
    assert "test_2" in summary["results"]
    assert "test_3" in summary["results"]
    assert summary["results"]["test_1"]["status"] == TestStatus.PASS.value
    assert summary["results"]["test_2"]["status"] == TestStatus.FAIL.value
    assert summary["results"]["test_3"]["status"] == TestStatus.SKIP.value


@pytest.mark.asyncio
async def test_notification_waiter():
    """Test the NotificationWaiter class."""
    char_uuid = "00002a37-0000-1000-8000-00805f9b34fb"  # Heart Rate Measurement
    expected_value = bytearray([0x01, 0x02, 0x03])

    # Create a waiter with an expected value
    waiter = NotificationWaiter(char_uuid, expected_value)

    # Test with matching notification
    assert waiter.on_notification(expected_value) is True
    assert waiter.matching_notification == expected_value
    assert waiter.complete_event.is_set() is True

    # Create a waiter with a callable
    def check_notification(data):
        return data[0] == 0x01

    waiter = NotificationWaiter(char_uuid, check_notification)

    # Test with matching notification
    assert waiter.on_notification(bytearray([0x01, 0x04, 0x05])) is True
    assert waiter.matching_notification == bytearray([0x01, 0x04, 0x05])
    assert waiter.complete_event.is_set() is True

    # Create a waiter with a callable that returns NotificationResult
    def check_notification_enum(data):
        if data[0] == 0x01:
            return NotificationResult.MATCH
        elif data[0] == 0x02:
            return NotificationResult.FAIL
        else:
            return NotificationResult.IGNORE

    waiter = NotificationWaiter(char_uuid, check_notification_enum)

    # Test with matching notification
    assert waiter.on_notification(bytearray([0x01, 0x04, 0x05])) is True
    assert waiter.matching_notification == bytearray([0x01, 0x04, 0x05])
    assert waiter.complete_event.is_set() is True

    # Reset the waiter
    waiter.complete_event.clear()
    waiter.matching_notification = None

    # Test with failing notification
    assert waiter.on_notification(bytearray([0x02, 0x04, 0x05])) is False
    assert waiter.matching_notification is None
    assert waiter.complete_event.is_set() is True
    assert waiter.failure_reason is not None

    # Reset the waiter
    waiter.complete_event.clear()
    waiter.matching_notification = None
    waiter.failure_reason = None

    # Test with ignored notification
    assert waiter.on_notification(bytearray([0x03, 0x04, 0x05])) is False
    assert waiter.matching_notification is None
    assert waiter.complete_event.is_set() is False
    assert waiter.failure_reason is None


@pytest.mark.asyncio
async def test_notification_subscription():
    """Test the NotificationSubscription class."""
    char_uuid = "00002a37-0000-1000-8000-00805f9b34fb"  # Heart Rate Measurement

    # Create a subscription
    subscription = NotificationSubscription(char_uuid)

    # Check initial state
    assert subscription.characteristic_uuid == char_uuid
    assert subscription.waiter is None
    assert subscription.collected_notifications == []

    # Create a waiter
    expected_value = bytearray([0x01, 0x02, 0x03])
    waiter = NotificationWaiter(char_uuid, expected_value)

    # Set the waiter
    subscription.set_waiter(waiter)
    assert subscription.waiter == waiter

    # Test notification handling with matching notification
    subscription.on_notification(expected_value)
    assert waiter.matching_notification == expected_value
    assert waiter.complete_event.is_set() is True
    # When a notification matches the waiter's criteria, collected_notifications is cleared
    assert len(subscription.collected_notifications) == 0

    # Clear the waiter
    subscription.clear_waiter()
    assert subscription.waiter is None

    # Test notification handling without a waiter
    subscription.on_notification(bytearray([0x04, 0x05, 0x06]))
    assert len(subscription.collected_notifications) == 1
    assert subscription.collected_notifications[0] == bytearray([0x04, 0x05, 0x06])

    # Set a new waiter and process collected notifications
    waiter = NotificationWaiter(char_uuid, lambda data: data[0] == 0x04)
    subscription.set_waiter(waiter, process_collected_notifications=True)
    assert waiter.matching_notification == bytearray([0x04, 0x05, 0x06])
    assert waiter.complete_event.is_set() is True
    # Again, collected_notifications is cleared when a match is found
    assert len(subscription.collected_notifications) == 0


def test_test_exceptions():
    """Test the test exception classes."""
    # Test TestException
    exception = TestException("Test exception message")
    assert exception.message == "Test exception message"
    assert str(exception) == "Test exception message"
    assert exception.status == TestStatus.ERROR

    # Test TestFailure
    failure = TestFailure("Test failure message")
    assert failure.message == "Test failure message"
    assert str(failure) == "Test failure message"
    assert failure.status == TestStatus.FAIL

    # Test TestSkip
    skip = TestSkip("Test skip message")
    assert skip.message == "Test skip message"
    assert str(skip) == "Test skip message"
    assert skip.status == TestStatus.SKIP
