"""Tests for the CLI functionality."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from rich.console import Console

from test_a_ble import cli
from test_a_ble.test_context import TestStatus


def test_get_console():
    """Test that get_console returns a Console instance."""
    console = cli.get_console()
    assert isinstance(console, Console)


@pytest.mark.asyncio
@patch("test_a_ble.cli.console")
async def test_print_test_results(mock_console):
    """Test printing test results."""
    # Create mock test results with the correct format
    results = {
        "results": {
            "test_1": {
                "status": TestStatus.PASS.value,
                "message": "Test passed",
                "duration": 0.1,
            },
            "test_2": {
                "status": TestStatus.PASS.value,
                "message": "Test passed",
                "duration": 0.2,
            },
            "test_3": {
                "status": TestStatus.FAIL.value,
                "message": "Test failed",
                "duration": 0.3,
                "exception": Exception("Test exception"),
            },
        },
        "passed_tests": 2,
        "failed_tests": 1,
        "total_tests": 3,
    }

    # Call the function
    cli.print_test_results(results)

    # Assert that console.print was called with the expected arguments
    assert mock_console.print.called

    # Verify that the table was created with the correct columns
    table_calls = [
        call for call in mock_console.print.call_args_list if str(call[0][0]).startswith("<rich.table.Table")
    ]
    assert len(table_calls) > 0, "No table was printed"

    # Verify that the summary information was printed
    mock_console.print.assert_any_call("\n[bold]Test Results:[/bold]")
    mock_console.print.assert_any_call("\n[bold]Total tests:[/bold] 3")
    mock_console.print.assert_any_call("[bold green]Passed:[/bold green] 2")
    mock_console.print.assert_any_call("[bold red]Failed:[/bold red] 1")


@pytest.mark.asyncio
@patch("test_a_ble.cli.TestRunner")
@patch("test_a_ble.cli.BLEManager")
@patch("test_a_ble.cli.print_test_results")
@patch("test_a_ble.cli.console")
async def test_run_ble_tests_with_address(
    mock_console, mock_print_results, mock_ble_manager_class, mock_test_runner_class
):
    """Test running BLE tests with a specific device address."""
    # Setup mocks
    mock_ble_manager = MagicMock()
    mock_ble_manager.connect_to_device = AsyncMock(return_value=True)
    mock_ble_manager.disconnect = AsyncMock()
    mock_ble_manager_class.return_value = mock_ble_manager

    # Mock test context
    mock_test_context = MagicMock()
    mock_test_context.cleanup_tasks = AsyncMock()

    mock_test_runner = MagicMock()
    mock_test_runner.test_context = mock_test_context
    mock_test_runner.discover_tests = MagicMock(return_value=[("test_module", ["test_1"])])
    mock_test_runner.run_tests = AsyncMock()
    mock_test_runner.run_tests.return_value = {
        "test_suite": "Test Suite",
        "total_tests": 1,
        "passed": 1,
        "failed": 0,
        "skipped": 0,
        "test_results": [
            {
                "name": "test_1",
                "status": TestStatus.PASS,
                "message": "Test passed",
                "duration": 0.1,
            }
        ],
    }
    mock_test_runner_class.return_value = mock_test_runner

    # Create args
    args = MagicMock()
    args.address = "00:11:22:33:44:55"
    args.name = None
    args.interactive = False
    args.test_module = "test_module"
    args.verbose = False
    args.scan_timeout = 5.0
    args.test_specifiers = ["test_module"]

    # Call the function
    await cli.run_ble_tests(args)

    # Assert
    mock_ble_manager.connect_to_device.assert_called_once_with("00:11:22:33:44:55")
    mock_test_runner_class.assert_called_once()
    mock_test_runner.discover_tests.assert_called_once_with(["test_module"])
    mock_test_runner.run_tests.assert_called_once_with(["test_1"])
    mock_test_context.cleanup_tasks.assert_called_once()
    mock_ble_manager.disconnect.assert_called_once()


@pytest.mark.asyncio
@patch("test_a_ble.cli.TestRunner")
@patch("test_a_ble.cli.BLEManager")
@patch("test_a_ble.cli.print_test_results")
@patch("test_a_ble.cli.console")
async def test_run_ble_tests_with_name(
    mock_console, mock_print_results, mock_ble_manager_class, mock_test_runner_class
):
    """Test running BLE tests with a device name filter."""
    # Setup mocks
    mock_ble_manager = MagicMock()
    mock_ble_manager.discover_devices = AsyncMock()
    mock_ble_manager.connect_to_device = AsyncMock(return_value=True)
    mock_ble_manager.disconnect = AsyncMock()

    # Create a mock device
    mock_device = MagicMock()
    mock_device.name = "Test Device"
    mock_device.address = "00:11:22:33:44:55"
    mock_ble_manager.discover_devices.return_value = [mock_device]

    mock_ble_manager_class.return_value = mock_ble_manager

    # Mock test context
    mock_test_context = MagicMock()
    mock_test_context.cleanup_tasks = AsyncMock()

    mock_test_runner = MagicMock()
    mock_test_runner.test_context = mock_test_context
    mock_test_runner.discover_tests = MagicMock(return_value=[("test_module", ["test_1"])])
    mock_test_runner.run_tests = AsyncMock()
    mock_test_runner.run_tests.return_value = {
        "test_suite": "Test Suite",
        "total_tests": 1,
        "passed": 1,
        "failed": 0,
        "skipped": 0,
        "test_results": [
            {
                "name": "test_1",
                "status": TestStatus.PASS,
                "message": "Test passed",
                "duration": 0.1,
            }
        ],
    }
    mock_test_runner_class.return_value = mock_test_runner

    # Create args
    args = MagicMock()
    args.address = None
    args.name = "Test Device"
    args.interactive = False
    args.test_module = "test_module"
    args.verbose = False
    args.scan_timeout = 5.0
    args.test_specifiers = ["test_module"]

    # Call the function
    await cli.run_ble_tests(args)

    # Assert
    mock_ble_manager.discover_devices.assert_called_once_with(timeout=5.0)
    mock_ble_manager.connect_to_device.assert_called_once_with(mock_device)
    mock_test_runner_class.assert_called_once()
    mock_test_runner.discover_tests.assert_called_once_with(["test_module"])
    mock_test_runner.run_tests.assert_called_once_with(["test_1"])
    mock_test_context.cleanup_tasks.assert_called_once()
    mock_ble_manager.disconnect.assert_called_once()


@pytest.mark.asyncio
@patch("test_a_ble.cli.connect_to_device")
@patch("test_a_ble.cli.TestRunner")
@patch("test_a_ble.cli.BLEManager")
@patch("test_a_ble.cli.print_test_results")
@patch("test_a_ble.cli.console")
async def test_run_ble_tests_interactive(
    mock_console,
    mock_print_results,
    mock_ble_manager_class,
    mock_test_runner_class,
    mock_connect_to_device,
):
    """Test running BLE tests in interactive mode."""
    # Setup mocks
    mock_ble_manager = MagicMock()
    mock_ble_manager.disconnect = AsyncMock()
    mock_ble_manager_class.return_value = mock_ble_manager

    # Mock the connect_to_device function to return success
    mock_connect_to_device.return_value = (True, False)  # (connected, user_quit)

    # Mock test context
    mock_test_context = MagicMock()
    mock_test_context.cleanup_tasks = AsyncMock()

    mock_test_runner = MagicMock()
    mock_test_runner.test_context = mock_test_context
    mock_test_runner.discover_tests = MagicMock(return_value=[("test_module", ["test_1"])])
    mock_test_runner.run_tests = AsyncMock()
    mock_test_runner.run_tests.return_value = {
        "test_suite": "Test Suite",
        "total_tests": 1,
        "passed": 1,
        "failed": 0,
        "skipped": 0,
        "test_results": [
            {
                "name": "test_1",
                "status": TestStatus.PASS,
                "message": "Test passed",
                "duration": 0.1,
            }
        ],
    }
    mock_test_runner_class.return_value = mock_test_runner

    # Create args
    args = MagicMock()
    args.address = None
    args.name = None
    args.interactive = True
    args.test_module = "test_module"
    args.verbose = False
    args.scan_timeout = 5.0
    args.test_specifiers = ["test_module"]

    # Call the function
    await cli.run_ble_tests(args)

    # Assert
    mock_connect_to_device.assert_called_once_with(mock_ble_manager, interactive=True, scan_timeout=5.0)
    mock_test_runner_class.assert_called_once()
    mock_test_runner.discover_tests.assert_called_once_with(["test_module"])
    mock_test_runner.run_tests.assert_called_once_with(["test_1"])
    mock_test_context.cleanup_tasks.assert_called_once()
    mock_ble_manager.disconnect.assert_called_once()
    mock_print_results.assert_called_once()


@pytest.mark.asyncio
@patch("test_a_ble.cli.connect_to_device")
@patch("test_a_ble.cli.TestRunner")
@patch("test_a_ble.cli.BLEManager")
@patch("test_a_ble.cli.print_test_results")
@patch("test_a_ble.cli.console")
async def test_run_ble_tests_user_quit(
    mock_console,
    mock_print_results,
    mock_ble_manager_class,
    mock_test_runner_class,
    mock_connect_to_device,
):
    """Test running BLE tests when user quits during device selection."""
    # Setup mocks
    mock_ble_manager = MagicMock()
    mock_ble_manager.disconnect = AsyncMock()
    mock_ble_manager_class.return_value = mock_ble_manager

    # Mock the connect_to_device function to return user quit
    mock_connect_to_device.return_value = (False, True)  # (connected, user_quit)

    # Mock test context
    mock_test_context = MagicMock()
    mock_test_context.cleanup_tasks = AsyncMock()

    mock_test_runner = MagicMock()
    mock_test_runner.test_context = mock_test_context
    mock_test_runner.discover_tests = MagicMock(return_value=[("test_module", ["test_1"])])
    mock_test_runner_class.return_value = mock_test_runner

    # Create args
    args = MagicMock()
    args.address = None
    args.name = None
    args.interactive = True
    args.test_module = "test_module"
    args.verbose = False
    args.scan_timeout = 5.0
    args.test_specifiers = ["test_module"]

    # Call the function
    await cli.run_ble_tests(args)

    # Assert
    mock_connect_to_device.assert_called_once_with(mock_ble_manager, interactive=True, scan_timeout=5.0)
    # Test runner should not be called if user quits
    mock_test_runner.run_tests.assert_not_called()
    mock_print_results.assert_not_called()
    # Discover tests should still be called before connection attempt
    mock_test_runner.discover_tests.assert_called_once_with(["test_module"])


@patch("test_a_ble.cli.run_ble_tests")
@patch("test_a_ble.cli.asyncio.new_event_loop")
@patch("argparse.ArgumentParser.parse_args")
def test_main(mock_parse_args, mock_asyncio_new_event_loop, mock_run_ble_tests):
    """Test the main function."""
    # Setup mocks
    mock_args = MagicMock()
    mock_args.verbose = False
    mock_args.log_file = None  # No log file
    mock_args.test_specifiers = ["test_function"]
    mock_args.address = "1234567890"
    mock_parse_args.return_value = mock_args

    # Call the function
    cli.main()

    # Assert
    mock_parse_args.assert_called_once()
    mock_asyncio_new_event_loop.assert_called_once()


@patch("test_a_ble.cli.setup_logging")
@patch("test_a_ble.cli.run_ble_tests")
@patch("test_a_ble.cli.asyncio.new_event_loop")
@patch("argparse.ArgumentParser.parse_args")
def test_main_verbose(mock_parse_args, mock_asyncio_new_event_loop, mock_run_ble_tests, mock_setup_logging):
    """Test the main function with verbose flag."""
    # Setup mocks
    mock_args = MagicMock()
    mock_args.verbose = True
    mock_args.log_file = None  # No log file
    mock_parse_args.return_value = mock_args

    # Call the function
    cli.main()

    # Assert
    mock_parse_args.assert_called_once()
    mock_setup_logging.assert_called_once_with(verbose=True, log_file=None)
    mock_asyncio_new_event_loop.assert_called_once()


@pytest.mark.asyncio
@patch("test_a_ble.cli.dynamic_device_selection")
async def test_connect_to_device_interactive(mock_dynamic_device_selection):
    """Test connecting to a device in interactive mode."""
    # Setup mocks
    mock_ble_manager = MagicMock()
    mock_dynamic_device_selection.return_value = (True, False)  # (connected, user_quit)

    # Call the function
    connected, user_quit = await cli.connect_to_device(mock_ble_manager, interactive=True, scan_timeout=5.0)

    # Assert
    assert connected is True
    assert user_quit is False
    mock_dynamic_device_selection.assert_called_once_with(mock_ble_manager, 5.0)


@pytest.mark.asyncio
async def test_connect_to_device_with_address():
    """Test connecting to a device with a specific address."""
    # Setup mocks
    mock_ble_manager = MagicMock()
    mock_ble_manager.connect_to_device = AsyncMock(return_value=True)

    # Call the function
    connected, user_quit = await cli.connect_to_device(mock_ble_manager, address="00:11:22:33:44:55")

    # Assert
    assert connected is True
    assert user_quit is False
    mock_ble_manager.connect_to_device.assert_called_once_with("00:11:22:33:44:55")


@pytest.mark.asyncio
async def test_connect_to_device_with_name():
    """Test connecting to a device with a name filter."""
    # Setup mocks
    mock_ble_manager = MagicMock()

    # Create a mock device
    mock_device = MagicMock()
    mock_device.name = "Test Device"
    mock_device.address = "00:11:22:33:44:55"

    # Setup discover_devices to return our mock device
    mock_ble_manager.discover_devices = AsyncMock(return_value=[mock_device])
    mock_ble_manager.connect_to_device = AsyncMock(return_value=True)

    # Call the function
    connected, user_quit = await cli.connect_to_device(mock_ble_manager, name="Test Device", scan_timeout=5.0)

    # Assert
    assert connected is True
    assert user_quit is False
    mock_ble_manager.discover_devices.assert_called_once_with(timeout=5.0, name_filter="Test Device")
    mock_ble_manager.connect_to_device.assert_called_once_with(mock_device)


@pytest.mark.asyncio
async def test_connect_to_device_with_name_no_devices():
    """Test connecting to a device with a name filter when no devices are found."""
    # Setup mocks
    mock_ble_manager = MagicMock()

    # Setup discover_devices to return no devices
    mock_ble_manager.discover_devices = AsyncMock(return_value=[])

    # Call the function
    connected, user_quit = await cli.connect_to_device(mock_ble_manager, name="Test Device", scan_timeout=5.0)

    # Assert
    assert connected is False
    assert user_quit is False
    mock_ble_manager.discover_devices.assert_called_once_with(timeout=5.0, name_filter="Test Device")
    mock_ble_manager.connect_to_device.assert_not_called()


@pytest.mark.asyncio
async def test_print_test_results_actual_output():
    """Test the actual output of print_test_results."""
    from io import StringIO

    from rich.console import Console

    # Create a StringIO object to capture the output
    string_io = StringIO()

    # Create a Console that writes to our StringIO
    test_console = Console(file=string_io, highlight=False)

    # Patch the console in cli module
    with patch("test_a_ble.cli.console", test_console):
        # Create test results with the correct format
        results = {
            "results": {
                "test_1": {
                    "status": TestStatus.PASS.value,
                    "message": "Test passed",
                    "duration": 0.1,
                },
                "test_2": {
                    "status": TestStatus.PASS.value,
                    "message": "Test passed",
                    "duration": 0.2,
                },
                "test_3": {
                    "status": TestStatus.FAIL.value,
                    "message": "Test failed",
                    "duration": 0.3,
                    "exception": "Test exception",
                },
            },
            "passed_tests": 2,
            "failed_tests": 1,
            "total_tests": 3,
        }

        # Call the function
        cli.print_test_results(results)

        # Get the output
        output = string_io.getvalue()

        # Print the output for debugging
        print("\nActual output of print_test_results:")
        print(output)

        # Check for key elements in the output
        assert "Test Results" in output
        assert "test_1" in output
        assert "test_2" in output
        assert "test_3" in output
        assert "PASS" in output
        assert "FAIL" in output
        assert "Test passed" in output
        assert "Test failed" in output
