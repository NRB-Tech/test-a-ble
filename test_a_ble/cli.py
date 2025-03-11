"""Command Line Interface for BLE Testing Framework."""

import argparse
import asyncio
import concurrent.futures
import logging
import sys
import time
from typing import Any, Dict, Optional, Tuple

import bleak
from rich import box
from rich.console import Console
from rich.table import Table

from . import setup_logging
from .ble_manager import BLEManager
from .test_context import TestStatus
from .test_runner import TestRunner

# Set up console for rich output
console = Console()
logger = logging.getLogger("ble_tester")


def get_console() -> Console:
    """Return the global console object for rich output."""
    global console
    return console


async def dynamic_device_selection(ble_manager: BLEManager, timeout: float = 10.0) -> Tuple[bool, bool]:
    """
    Interactive device discovery with real-time updates and concurrent user input.

    Args:
        ble_manager: BLE Manager instance
        timeout: Maximum scan duration in seconds

    Returns:
        Tuple of (connected successfully, user quit)
    """
    console.print("[bold]Scanning for BLE devices...[/bold]")
    console.print(f"[dim]Scan will continue for up to {timeout} seconds[/dim]")
    console.print(
        "[bold yellow]Enter a device number to select it immediately, press Enter for options, or wait for scan to "
        "complete[/bold yellow]"
    )

    # Keep track of discovered devices in order of discovery
    discovered_devices = []

    # Event to signal when scanning should stop
    stop_event = asyncio.Event()

    # Flag to indicate UI needs updating
    ui_update_needed = asyncio.Event()

    # Function to be called when new devices are found (runs in BLE library thread)
    def device_found_callback(device, adv_data):
        # Skip devices we've already found
        if any(d.address == device.address for d in discovered_devices):
            return

        # Store the device and advertisement data (thread-safe operations)
        ble_manager.advertisement_data_map[device.address] = adv_data
        discovered_devices.append(device)

        # Signal that UI needs updating (thread-safe)
        ui_update_needed.set()

        # Log device discovery for debugging
        logger.debug(f"Device discovered: {device.name or 'Unknown'} ({device.address})")

    # Start scanning task
    async def scan_for_devices():
        # Create a new scanner each time
        scanner = bleak.BleakScanner(detection_callback=device_found_callback)

        try:
            # Start scanning
            await scanner.start()
            logger.debug("Scanner started")

            # Keep scanning until timeout or stop_event
            scan_end_time = time.time() + timeout
            while time.time() < scan_end_time and not stop_event.is_set():
                await asyncio.sleep(0.1)

            logger.debug(f"Scan finished: timeout={time.time() >= scan_end_time}, stopped={stop_event.is_set()}")

        finally:
            # Ensure scanner is stopped
            await scanner.stop()
            logger.debug("Scanner stopped")
            ble_manager.discovered_devices = discovered_devices.copy()

    # Task to update the UI when needed (runs in the main asyncio loop)
    async def update_ui():
        last_update_time = 0
        last_device_count = 0
        force_update = False

        while not stop_event.is_set():
            try:
                # Wait for signal with timeout
                try:
                    await asyncio.wait_for(ui_update_needed.wait(), timeout=0.5)
                    ui_update_needed.clear()
                    force_update = True  # Force update when signal is received
                except asyncio.TimeoutError:
                    # Force update every 3 seconds regardless of signal
                    if time.time() - last_update_time >= 3.0:
                        force_update = True
                    else:
                        continue  # No update needed

                # Check if we need to update the UI
                current_device_count = len(discovered_devices)

                # Skip update if no new devices and not forced
                if not force_update and current_device_count == last_device_count:
                    continue

                # Track last update time and device count
                last_update_time = time.time()
                last_device_count = current_device_count
                force_update = False  # Reset force flag

                # Create new table for each update
                table = Table(title="Discovered Devices")
                table.add_column("#", justify="right", style="cyan")
                table.add_column("Name", style="green")
                table.add_column("Address", style="blue")
                table.add_column("RSSI", justify="right")

                # Add devices to table
                for i, device in enumerate(discovered_devices):
                    adv_data = ble_manager.advertisement_data_map.get(device.address)
                    rssi = adv_data.rssi if adv_data else "N/A"

                    table.add_row(str(i + 1), device.name or "Unknown", device.address, str(rssi))

                # Clear console and redraw (in main thread)
                console.clear()
                console.print("[bold]Scanning for BLE devices...[/bold]")
                console.print(f"[dim]Scan will continue for up to {timeout} seconds[/dim]")
                if discovered_devices:
                    console.print(table)
                    console.print(
                        "[bold yellow]Enter a device number to select it immediately, press Enter for options, or wait "
                        "for scan to complete[/bold yellow]"
                    )
                else:
                    console.print("[dim]No devices found yet...[/dim]")
                    console.print(
                        "[bold yellow]Press Enter for options or wait for devices to be discovered[/bold yellow]"
                    )

            except Exception as e:
                logger.error(f"Error updating UI: {e}")
                await asyncio.sleep(0.5)  # Avoid tight loop on error

    # Create the tasks
    scan_task = asyncio.create_task(scan_for_devices())
    ui_task = asyncio.create_task(update_ui())

    # Set up input handling
    try:
        while not scan_task.done():
            # Get user input with timeout
            try:
                # Wait for user input
                user_input = await asyncio.to_thread(console.input, "")

                # Check if the input is a device number
                try:
                    # If input is a number and valid, connect to that device
                    if user_input.strip():
                        device_index = int(user_input.strip()) - 1

                        # Stop scanning first
                        stop_event.set()
                        await asyncio.wait_for(
                            asyncio.gather(scan_task, ui_task, return_exceptions=True),
                            timeout=2.0,
                        )

                        # Check if the device index is valid
                        if 0 <= device_index < len(discovered_devices):
                            device = discovered_devices[device_index]
                            console.print(
                                f"[bold]Connecting to {device.name or 'Unknown'} ({device.address})...[/bold]"
                            )
                            connected = await ble_manager.connect_to_device(device)

                            if connected:
                                console.print(f"[bold green]Successfully connected to {device.address}![/bold green]")
                                return True, False  # Connected, not user quit
                            else:
                                console.print(f"[bold red]Failed to connect to {device.address}![/bold red]")
                                # Return to selection menu rather than quitting
                                break
                        else:
                            console.print(f"[bold red]Invalid device number: {user_input}![/bold red]")
                            await asyncio.sleep(1)  # Brief pause so user can see the error
                            # Continue scanning
                            stop_event.clear()
                            scan_task = asyncio.create_task(scan_for_devices())
                            ui_task = asyncio.create_task(update_ui())
                            continue
                    else:
                        # Empty input (just Enter key) - stop scanning and show menu
                        stop_event.set()
                        await asyncio.wait_for(
                            asyncio.gather(scan_task, ui_task, return_exceptions=True),
                            timeout=2.0,
                        )
                        break
                except ValueError:
                    # Not a number, treat as Enter key
                    console.print(
                        f"[bold red]Invalid input: {user_input}. Press Enter or enter a device number.[/bold red]"
                    )
                    await asyncio.sleep(1)  # Brief pause so user can see the error
                    # Continue scanning
                    ui_update_needed.set()  # Force UI refresh
                    continue

            except asyncio.TimeoutError:
                # No input received, continue scanning
                continue

    except asyncio.CancelledError:
        # Task was cancelled, clean up
        stop_event.set()
        if not scan_task.done():
            scan_task.cancel()
        if not ui_task.done():
            ui_task.cancel()

    finally:
        # Make sure scanning is stopped and tasks are cleaned up
        stop_event.set()

        # Cancel any running tasks
        if not scan_task.done():
            scan_task.cancel()
            try:
                await asyncio.wait_for(scan_task, timeout=1.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass

        if not ui_task.done():
            ui_task.cancel()
            try:
                await asyncio.wait_for(ui_task, timeout=1.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass

    # Show selection menu after scan completes or user presses Enter
    if discovered_devices:
        # Build a final table for selection
        table = Table(title="Discovered Devices")
        table.add_column("#", justify="right", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Address", style="blue")
        table.add_column("RSSI", justify="right")

        for i, device in enumerate(discovered_devices):
            adv_data = ble_manager.advertisement_data_map.get(device.address)
            rssi = adv_data.rssi if adv_data else "N/A"

            table.add_row(str(i + 1), device.name or "Unknown", device.address, str(rssi))

        console.clear()
        console.print("[bold]Device Selection[/bold]")
        console.print(table)

        while True:
            selection = console.input(
                "\n[bold yellow]Enter device number to connect, 'r' to rescan, or 'q' to quit: [/bold yellow]"
            )

            if selection.lower() == "q":
                return False, True  # Not connected, user quit

            if selection.lower() == "r":
                # Reset and restart scanning
                discovered_devices.clear()
                ble_manager.advertisement_data_map.clear()
                ble_manager.discovered_devices.clear()
                return await dynamic_device_selection(ble_manager, timeout)

            try:
                index = int(selection) - 1
                if 0 <= index < len(discovered_devices):
                    device = discovered_devices[index]
                    # Connect to selected device
                    console.print(f"[bold]Connecting to {device.name or 'Unknown'} ({device.address})...[/bold]")
                    connected = await ble_manager.connect_to_device(device)

                    if connected:
                        console.print(f"[bold green]Successfully connected to {device.address}![/bold green]")
                        return True, False  # Connected, not user quit
                    else:
                        console.print(f"[bold red]Failed to connect to {device.address}![/bold red]")
                        # Ask if user wants to try again
                        retry = console.input("[bold yellow]Try again? (y/n): [/bold yellow]")
                        if retry.lower() == "y":
                            # Restart scanning
                            discovered_devices.clear()
                            ble_manager.advertisement_data_map.clear()
                            ble_manager.discovered_devices.clear()
                            return await dynamic_device_selection(ble_manager, timeout)
                        else:
                            return False, True  # User quit
                else:
                    console.print("[bold red]Invalid selection![/bold red]")
            except ValueError:
                console.print("[bold red]Please enter a number, 'r', or 'q'![/bold red]")
    else:
        console.print("[bold red]No devices found![/bold red]")
        rescan = console.input("[bold yellow]Press 'r' to rescan or any other key to quit: [/bold yellow]")
        if rescan.lower() == "r":
            # Clear previous state before rescanning
            discovered_devices.clear()
            ble_manager.advertisement_data_map.clear()
            ble_manager.discovered_devices.clear()
            return await dynamic_device_selection(ble_manager, timeout)
        return False, False  # Not connected, not user quit


async def connect_to_device(
    ble_manager: BLEManager,
    address: Optional[str] = None,
    name: Optional[str] = None,
    interactive: bool = False,
    scan_timeout: float = 10.0,
) -> Tuple[bool, bool]:
    """
    Connect to a BLE device by address, name, or interactively.

    Args:
        ble_manager: BLE Manager instance
        address: Optional device address to connect to
        name: Optional device name to connect to
        interactive: Whether to use interactive mode for device selection
        scan_timeout: Scan timeout in seconds

    Returns:
        Tuple of (connected successfully, user quit)
    """
    # Interactive mode
    if interactive and not address and not name:
        # Use dynamic device selection instead of the old interactive selection
        return await dynamic_device_selection(ble_manager, scan_timeout)

    # Connect by address
    if address:
        console.print(f"[bold]Connecting to device with address {address}...[/bold]")
        connected = await ble_manager.connect_to_device(address)

        if connected:
            console.print(f"[bold green]Successfully connected to {address}![/bold green]")
            return True, False  # Connected, not user quit
        else:
            console.print(f"[bold red]Failed to connect to {address}![/bold red]")
            return False, False  # Not connected, not user quit

    # Connect by name
    if name:
        console.print(f"[bold]Searching for device with name '{name}'...[/bold]")
        devices = await ble_manager.discover_devices(timeout=scan_timeout, name_filter=name)

        if not devices:
            console.print(f"[bold red]No devices found with name '{name}'![/bold red]")
            return False, False  # Not connected, not user quit

        # Connect to the first matching device
        device = devices[0]
        console.print(f"[bold]Connecting to {device.name} ({device.address})...[/bold]")
        connected = await ble_manager.connect_to_device(device)

        if connected:
            console.print(f"[bold green]Successfully connected to {device.address}![/bold green]")
            return True, False  # Connected, not user quit
        else:
            console.print(f"[bold red]Failed to connect to {device.address}![/bold red]")
            return False, False  # Not connected, not user quit

    # No connection method specified
    console.print("[bold red]No device specified for connection![/bold red]")
    return False, False  # Not connected, not user quit


def print_test_results(results: Dict[str, Any], verbose=False):
    """
    Print formatted test results.

    Args:
        results: Test results dictionary
        verbose: If True, show logs for all tests (not just failed ones)
    """
    console.print("\n[bold]Test Results:[/bold]")

    table = Table(title="Test Summary")
    table.add_column("Test", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Duration", justify="right")
    table.add_column("Message")

    total_duration = 0

    # Filter out any tests that are still marked as 'running' - these are duplicates
    # where a test function renamed itself
    filtered_results = {
        name: result
        for name, result in results.get("results", {}).items()
        if result.get("status", "unknown") != TestStatus.RUNNING.value
    }

    for test_name, result in filtered_results.items():
        status = result.get("status", "unknown")
        duration = result.get("duration", 0)
        total_duration += duration

        status_style = {
            TestStatus.PASS.value: "green",
            TestStatus.FAIL.value: "red",
            TestStatus.ERROR.value: "yellow",
            TestStatus.SKIP.value: "dim",
            TestStatus.RUNNING.value: "blue",
        }.get(status, "")

        table.add_row(
            test_name,
            f"[{status_style}]{status.upper()}[/{status_style}]",
            f"{duration:.2f}s",
            result.get("message", ""),
        )

    console.print(table)

    # Print detailed logs for tests based on criteria
    for test_name, result in filtered_results.items():
        status = result.get("status", "unknown")
        # Determine if we should show logs for this test
        # Show logs if verbose mode is enabled or if the test failed
        show_logs = verbose or status in [TestStatus.FAIL.value, TestStatus.ERROR.value]

        if show_logs:
            logs = result.get("logs", [])
            if logs:
                status_style = "red" if status in [TestStatus.FAIL.value, TestStatus.ERROR.value] else "cyan"
                console.print(f"\n[bold {status_style}]Logs for test: [cyan]{test_name}[/cyan][/bold {status_style}]")

                log_table = Table(show_header=True, box=box.SIMPLE)
                log_table.add_column("Level", style="bold")
                log_table.add_column("Message", style="white")

                for log in logs:
                    level = log.get("level", "INFO")
                    message = log.get("message", "")

                    # Style based on log level
                    level_style = {
                        "DEBUG": "dim blue",
                        "INFO": "white",
                        "WARNING": "yellow",
                        "ERROR": "red",
                        "CRITICAL": "bold red",
                        "USER": "green bold",
                    }.get(level, "white")

                    log_table.add_row(f"[{level_style}]{level}[/{level_style}]", message)

                console.print(log_table)

    # Print summary
    console.print(f"\n[bold]Total tests:[/bold] {len(filtered_results)}")
    console.print(f"[bold green]Passed:[/bold green] {results.get('passed_tests', 0)}")
    console.print(f"[bold red]Failed:[/bold red] {results.get('failed_tests', 0)}")
    console.print(f"[bold]Total duration:[/bold] {total_duration:.2f}s")

    # Overall status
    if results.get("failed_tests", 0) == 0:
        console.print("\n[bold green]All tests passed![/bold green]")
    else:
        console.print(f"\n[bold red]{results.get('failed_tests', 0)} tests failed![/bold red]")


async def run_ble_tests(args):
    """Run BLE tests based on command line arguments."""
    # Create BLE manager
    ble_manager = BLEManager()

    # Create console for rich output
    console = get_console()

    # Create a TestRunner instance
    test_runner = TestRunner(ble_manager)

    try:
        # IMPORTANT: First discover tests before attempting connection
        # This allows test packages to register their service UUIDs during initialization
        # Determine test directory and tests to run based on test specifiers
        all_tests = []
        logger.debug(f"args.test_specifiers: {args.test_specifiers}")
        # Process each test specifier to determine its test directory
        all_tests = test_runner.discover_tests(args.test_specifiers)
        if not all_tests:
            console.print("[bold red]No tests were discovered in any specified directories![/bold red]")
            console.print("[dim]Check that your test files begin with 'test_' and are in the correct location.[/dim]")
            return

        # sum number of tests in all modules:
        total_tests = sum(len(tests) for _, tests in all_tests)
        console.print(f"[bold]Found {total_tests} test(s) in {len(all_tests)} module(s)[/bold]")

        # Now that tests have been discovered and service UUIDs registered, connect to device
        # Connect to device
        if args.address:
            # Connect directly to the specified address
            console.print(f"[bold]Connecting to device with address {args.address}...[/bold]")
            connected = await ble_manager.connect_to_device(args.address)
            if not connected:
                console.print(f"[bold red]Failed to connect to {args.address}![/bold red]")
                return
        elif args.name:
            # Search for a device with the specified name
            console.print(f"[bold]Searching for device with name '{args.name}'...[/bold]")
            devices = await ble_manager.discover_devices(timeout=args.scan_timeout)
            matching_devices = [d for d in devices if args.name.lower() in (d.name or "").lower()]
            if not matching_devices:
                console.print(f"[bold red]No devices found with name containing '{args.name}'![/bold red]")
                return

            device = matching_devices[0]
            console.print(f"[bold]Connecting to {device.name} ({device.address})...[/bold]")
            connected = await ble_manager.connect_to_device(device)
            if not connected:
                console.print(f"[bold red]Failed to connect to {device.address}![/bold red]")
                return
        else:
            # No address or name specified, use interactive device discovery
            console.print("[bold]No device address or name specified, starting interactive device discovery...[/bold]")
            connected, user_quit = await connect_to_device(
                ble_manager, interactive=True, scan_timeout=args.scan_timeout
            )
            if not connected:
                if user_quit:
                    console.print("[bold yellow]User quit device selection![/bold yellow]")
                else:
                    console.print("[bold red]Failed to connect to device![/bold red]")
                return

        # Run tests from each discovered test directory
        all_results = {
            "results": {},
            "passed_tests": 0,
            "failed_tests": 0,
            "total_tests": 0,
        }

        # Run tests
        for module_name, tests in all_tests:
            console.print(f"[bold]Running {len(tests)} tests in {module_name}...[/bold]")
            results = await test_runner.run_tests(tests)

            # Merge results
            if "results" in results:
                all_results["results"].update(results["results"])
            all_results["passed_tests"] += results.get("passed_tests", 0)
            all_results["failed_tests"] += results.get("failed_tests", 0)
            all_results["total_tests"] += results.get("total_tests", 0)

        # Print consolidated results
        if all_results["total_tests"] > 0:
            print_test_results(all_results, args.verbose)
        else:
            console.print("[bold red]No tests were run![/bold red]")

    finally:
        # Clean up test context tasks
        if "test_runner" in locals():
            try:
                await test_runner.test_context.cleanup_tasks()
            except Exception as e:
                logger.error(f"Error cleaning up test context: {e}")

        # Disconnect from device
        console.print("[bold]Disconnecting from device...[/bold]")
        try:
            await ble_manager.disconnect()
        except Exception as e:
            logger.error(f"Error during disconnect: {e}")

        # More aggressive task cancellation to ensure clean exit
        # Get all tasks except the current one
        remaining_tasks = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]

        if remaining_tasks:
            logger.debug(f"Cancelling {len(remaining_tasks)} remaining tasks")

            # First attempt to cancel all tasks
            for task in remaining_tasks:
                task.cancel()

            # Wait for tasks to acknowledge cancellation
            try:
                # Set a short timeout to avoid blocking indefinitely
                await asyncio.wait(remaining_tasks, timeout=2.0)
                logger.debug("Tasks acknowledged cancellation")
            except Exception as e:
                logger.debug(f"Error waiting for task cancellation: {e}")

            # Check for any tasks that didn't cancel properly
            still_running = [t for t in remaining_tasks if not t.done()]
            if still_running:
                logger.debug(f"{len(still_running)} tasks still running after cancellation")

                # Try gathering with exceptions to force completion
                try:
                    await asyncio.gather(*still_running, return_exceptions=True)
                except Exception as e:
                    logger.debug(f"Error during forced task completion: {e}")

        # Force shutdown of all executor threads
        loop = asyncio.get_running_loop()

        # Force shutdown of any thread pools
        executor = concurrent.futures.ThreadPoolExecutor()
        executor._threads.clear()

        # Close all running transports - this helps with hanging socket connections
        for transport in getattr(loop, "_transports", set()):
            if hasattr(transport, "close"):
                logger.debug(f"Closing transport: {transport}")
                try:
                    transport.close()
                except Exception as e:
                    logger.debug(f"Error closing transport: {e}")

        # Force event loop to close by returning from this coroutine
        logger.debug("Cleanup complete, exiting run_ble_tests")


def main():
    """Execute the main function."""
    parser = argparse.ArgumentParser(
        description="BLE IoT Device Testing Tool - Discovers and runs tests for BLE devices. "
        "If no device address or name is provided, interactive device discovery will be used."
    )

    # Device selection options
    device_group = parser.add_argument_group("Device Selection")
    device_group.add_argument("--address", "-a", help="MAC address of the BLE device")
    device_group.add_argument("--name", help="Name of the BLE device")
    device_group.add_argument(
        "--scan-timeout",
        type=float,
        default=10.0,
        help="Timeout for device scanning in seconds (default: 10.0)",
    )

    # Test options
    test_group = parser.add_argument_group("Test Options")
    # Remove test-dir argument and keep only positional arguments for test specifiers
    parser.add_argument(
        "test_specifiers",
        nargs="*",
        default=["all"],
        help="Test specifiers in unittest-style format. Examples:\n"
        "  test_module                      # Run all tests in a module\n"
        "  test_module.test_function        # Run a specific test function\n"
        "  path/to/test_file.py             # Run all tests in a file\n"
        "  path/to/directory                # Run all tests in a directory\n"
        "  all                              # Run all tests in current directory (default)",
    )

    # Logging options
    log_group = parser.add_argument_group("Logging Options")
    log_group.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging (includes logs for all tests)",
    )
    log_group.add_argument("--log-file", help="Log file path (default: no file logging)")

    args = parser.parse_args()

    # Configure logging using our new setup function
    setup_logging(verbose=args.verbose, log_file=args.log_file)

    # Run tests
    try:
        logger.debug("Starting test execution")

        # Create a new event loop with custom executor shutdown timeout
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Run the main coroutine with our custom loop
        loop.run_until_complete(run_ble_tests(args))

        # Perform manual cleanup after run completes
        pending = asyncio.all_tasks(loop)
        if pending:
            logger.debug(f"Cancelling {len(pending)} pending tasks")
            for task in pending:
                task.cancel()

            # Wait briefly for tasks to acknowledge cancellation
            loop.run_until_complete(asyncio.wait(pending, timeout=2.0, loop=loop))

        # Close the loop
        try:
            loop.close()
        except Exception as e:
            logger.debug(f"Error closing loop: {e}")

        logger.debug("Test execution completed normally")

    except KeyboardInterrupt:
        logger.debug("Test execution interrupted by user")
        console.print("\n[bold yellow]Test execution interrupted![/bold yellow]")

        # Force shutdown of any running tasks and thread pools
        if "loop" in locals():
            try:
                # Cancel all remaining tasks
                remaining = asyncio.all_tasks(loop)
                if remaining:
                    logger.debug(f"Cancelling {len(remaining)} remaining tasks due to keyboard interrupt")
                    for task in remaining:
                        task.cancel()

                    # Short wait for cancellation
                    try:
                        loop.run_until_complete(asyncio.wait(remaining, timeout=1.0, loop=loop))
                    except Exception:
                        pass  # nosec B110

                # Close the loop
                try:
                    loop.close()
                except Exception:
                    pass  # nosec B110
            except Exception as e:
                logger.debug(f"Error during keyboard interrupt cleanup: {e}")

    except Exception as e:
        logger.error(f"Error during test execution: {e}")
        console.print(f"\n[bold red]Error: {str(e)}[/bold red]")
        if args.verbose:
            console.print_exception()
    finally:
        # Ensure all loggers have flushed their output
        for handler in logging.root.handlers:
            handler.flush()

        # Log clean exit
        logger.debug("Exiting program")

        return 0


if __name__ == "__main__":
    sys.exit(main())
