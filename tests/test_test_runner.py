"""Tests for the TestRunner class."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest  # type: ignore

from test_a_ble.ble_manager import BLEManager
from test_a_ble.test_context import TestContext, TestStatus
from test_a_ble.test_runner import TestRunner

TEST_PACKAGE_DIR = Path(__file__).parent / "test_discovery_test_package"


@pytest.fixture
def mock_ble_manager():
    """Create a mock BLEManager for testing."""
    mock_manager = MagicMock(spec=BLEManager)
    mock_manager.connect_to_device = AsyncMock(return_value=True)
    mock_manager.disconnect = AsyncMock()
    return mock_manager


@pytest.fixture
def test_runner(mock_ble_manager):
    """Create a TestRunner instance for testing."""
    return TestRunner(mock_ble_manager)


def test_init(test_runner, mock_ble_manager):
    """Test initialization of TestRunner."""
    assert test_runner.ble_manager == mock_ble_manager
    assert isinstance(test_runner.test_context, TestContext)


@pytest.mark.asyncio
@patch("inspect.getmembers")
async def test_run_test_function(mock_getmembers, test_runner):
    """Test running a test function."""
    # Setup
    test_name = "test_function"
    test_description = "Test description"

    # Create a mock test function
    mock_test_func = AsyncMock()
    mock_test_func._is_ble_test = True
    mock_test_func._test_description = test_description

    # Mock the test context
    test_runner.test_context.start_test = MagicMock()
    test_runner.test_context.end_test = MagicMock()
    test_runner.test_context.unsubscribe_all = AsyncMock()

    # Run the test
    await test_runner.run_test(test_name, mock_test_func)

    # Assert
    test_runner.test_context.start_test.assert_called_once_with(test_description)
    mock_test_func.assert_called_once_with(test_runner.ble_manager, test_runner.test_context)
    test_runner.test_context.end_test.assert_called_once_with(TestStatus.PASS)
    test_runner.test_context.unsubscribe_all.assert_called_once()


@pytest.mark.asyncio
@patch("inspect.getmembers")
async def test_run_test_class(mock_getmembers, test_runner):
    """Test running a test class."""
    # Setup
    test_name = "TestClass.test_method"
    test_description = "Test class description"

    # Create a mock test class and method
    mock_test_method = AsyncMock()
    mock_test_method._test_description = test_description

    # Create a mock class instance that will be returned by the class constructor
    mock_instance = MagicMock()
    mock_instance.setUp = AsyncMock()
    mock_instance.tearDown = AsyncMock()

    # Create a mock class that returns the mock instance when called
    mock_test_class = MagicMock()
    mock_test_class._is_test_class = True
    mock_test_class._test_description = test_description
    mock_test_class.return_value = mock_instance
    mock_test_class.test_method = mock_test_method

    # Setup the test item as a tuple (class_name, class_obj, method)
    test_item = ("TestClass", mock_test_class, mock_test_method)

    # Mock the test context
    test_runner.test_context.start_test = MagicMock()
    test_runner.test_context.end_test = MagicMock()
    test_runner.test_context.unsubscribe_all = AsyncMock()

    # Run the test
    await test_runner.run_test(test_name, test_item)

    # Assert
    test_runner.test_context.start_test.assert_called_once_with(test_description)
    mock_instance.setUp.assert_called_once_with(test_runner.ble_manager, test_runner.test_context)
    mock_test_method.assert_called_once_with(mock_instance, test_runner.ble_manager, test_runner.test_context)
    mock_instance.tearDown.assert_called_once_with(test_runner.ble_manager, test_runner.test_context)
    test_runner.test_context.end_test.assert_called_once_with(TestStatus.PASS)
    test_runner.test_context.unsubscribe_all.assert_called_once()


@pytest.mark.asyncio
async def test_run_tests(test_runner):
    """Test running multiple tests."""
    # Setup
    mock_func1 = AsyncMock()
    mock_func1._is_ble_test = True
    mock_func2 = AsyncMock()
    mock_func2._is_ble_test = True

    tests = [("test_1", mock_func1), ("test_2", mock_func2)]

    # Mock the run_test method
    test_runner.run_test = AsyncMock()

    # Mock the test context
    test_runner.test_context.get_test_summary = MagicMock(return_value={"results": {}})
    test_runner.test_context.cleanup_tasks = AsyncMock()

    # Run the tests
    result = await test_runner.run_tests(tests)

    # Assert
    assert test_runner.run_test.call_count == 2
    test_runner.run_test.assert_any_call("test_1", mock_func1)
    test_runner.run_test.assert_any_call("test_2", mock_func2)
    test_runner.test_context.get_test_summary.assert_called_once()
    test_runner.test_context.cleanup_tasks.assert_called_once()
    assert result == {"results": {}}
