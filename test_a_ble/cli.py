"""Command Line Interface for BLE Testing Framework."""

import argparse
import asyncio
import concurrent.futures
import contextlib
import logging
import sys
import time
from dataclasses import dataclass
from typing import Any

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

TIME_BETWEEN_UPDATES = 3.0


@dataclass
class DeviceSelectionContext:
    """Context class for device selection to share state between functions."""

    ble_manager: BLEManager
    discovered_devices: list[bleak.BLEDevice]
    stop_event: asyncio.Event
    ui_update_needed: asyncio.Event
    scan_task: asyncio.Task
    ui_task: asyncio.Task
    timeout: float


def get_console() -> Console:
    """Return the global console object for rich output."""
    return console


async def _handle_device_selection(
    device_index: int, discovered_devices: list[bleak.BLEDevice], ble_manager: BLEManager
) -> tuple[bool, bool]:
    """Handle selection of a device by its index.

    Args:
        device_index: Index of the selected device
        discovered_devices: List of discovered devices
        ble_manager: BLE Manager instance

    Returns:
        Tuple of (connected successfully, user quit)
    """
    if 0 <= device_index < len(discovered_devices):
        device = discovered_devices[device_index]
        console.print(
            f"[bold]Connecting to {device.name or 'Unknown'} ({device.address})...[/bold]",
        )
        connected = await ble_manager.connect_to_device(device)

        if connected:
            console.print(f"[bold green]Successfully connected to {device.address}![/bold green]")
            return True, False  # Connected, not user quit
        console.print(f"[bold red]Failed to connect to {device.address}![/bold red]")
        return False, False  # Not connected, not user quit

    console.print(f"[bold red]Invalid device number: {device_index + 1}![/bold red]")
    return False, False  # Not connected, not user quit


async def _scan_for_devices(device_found_callback: callable, stop_event: asyncio.Event, timeout: float) -> None:
    """Scan for BLE devices.

    Args:
        device_found_callback: Callback function for when a device is found
        stop_event: Event to signal when to stop scanning
        timeout: Maximum scan duration in seconds
    """
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


async def _update_device_table_ui(
    discovered_devices: list[bleak.BLEDevice],
    ble_manager: BLEManager,
    timeout: float,
    ui_update_needed: asyncio.Event,
    stop_event: asyncio.Event,
) -> None:
    """Update the UI with the current list of discovered devices.

    Args:
        discovered_devices: List of discovered devices
        ble_manager: BLE Manager instance
        timeout: Maximum scan duration in seconds
        ui_update_needed: Event to signal when UI needs updating
        stop_event: Event to signal when to stop scanning
    """
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
            except TimeoutError:
                # Force update every 3 seconds regardless of signal
                if time.time() - last_update_time >= TIME_BETWEEN_UPDATES:
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

            # Create and display the table
            _display_device_table(discovered_devices, ble_manager, timeout)

        except Exception:
            logger.exception("Error updating UI")
            await asyncio.sleep(0.5)  # Avoid tight loop on error


def _display_device_table(discovered_devices: list[bleak.BLEDevice], ble_manager: BLEManager, timeout: float) -> None:
    """Display a table of discovered devices.

    Args:
        discovered_devices: List of discovered devices
        ble_manager: BLE Manager instance
        timeout: Maximum scan duration in seconds
    """
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

    # Clear console and redraw
    console.clear()
    console.print("[bold]Scanning for BLE devices...[/bold]")
    console.print(f"[dim]Scan will continue for up to {timeout} seconds[/dim]")
    if discovered_devices:
        console.print(table)
        console.print(
            "[bold yellow]Enter a device number to select it immediately, press Enter for options, or wait "
            "for scan to complete[/bold yellow]",
        )
    else:
        console.print("[dim]No devices found yet...[/dim]")
        console.print(
            "[bold yellow]Press Enter for options or wait for devices to be discovered[/bold yellow]",
        )


async def _show_selection_menu(
    discovered_devices: list[bleak.BLEDevice], ble_manager: BLEManager, timeout: float
) -> tuple[bool, bool]:
    """Show a selection menu after scanning completes.

    Args:
        discovered_devices: List of discovered devices
        ble_manager: BLE Manager instance
        timeout: Maximum scan duration in seconds

    Returns:
        Tuple of (connected successfully, user quit)
    """
    if not discovered_devices:
        console.print("[bold red]No devices found![/bold red]")
        rescan = console.input("[bold yellow]Press 'r' to rescan or any other key to quit: [/bold yellow]")
        if rescan.lower() == "r":
            # Clear previous state before rescanning
            discovered_devices.clear()
            ble_manager.advertisement_data_map.clear()
            ble_manager.discovered_devices.clear()
            return await dynamic_device_selection(ble_manager, timeout)
        return False, False  # Not connected, not user quit

    # Build a final table for selection
    _display_device_table(discovered_devices, ble_manager, timeout)

    # Default return values
    connected, user_quit = False, False

    selection_loop = True
    while selection_loop:
        selection = console.input(
            "\n[bold yellow]Enter device number to connect, 'r' to rescan, or 'q' to quit: [/bold yellow]",
        )

        if selection.lower() == "q":
            connected, user_quit = False, True  # Not connected, user quit
            selection_loop = False
        elif selection.lower() == "r":
            # Reset and restart scanning
            discovered_devices.clear()
            ble_manager.advertisement_data_map.clear()
            ble_manager.discovered_devices.clear()
            return await dynamic_device_selection(ble_manager, timeout)
        else:
            try:
                index = int(selection) - 1
                connected, user_quit = await _handle_device_selection(index, discovered_devices, ble_manager)

                if connected:
                    selection_loop = False
                elif not user_quit:
                    # Ask if user wants to try again
                    retry = console.input("[bold yellow]Try again? (y/n): [/bold yellow]")
                    if retry.lower() == "y":
                        # Restart scanning
                        discovered_devices.clear()
                        ble_manager.advertisement_data_map.clear()
                        ble_manager.discovered_devices.clear()
                        return await dynamic_device_selection(ble_manager, timeout)
                    connected, user_quit = False, True  # User quit
                    selection_loop = False
            except ValueError:
                console.print("[bold red]Please enter a number, 'r', or 'q'![/bold red]")

    return connected, user_quit


async def _handle_user_input(
    user_input: str,
    ctx: DeviceSelectionContext,
) -> tuple[bool, bool, bool]:
    """Handle user input during device scanning.

    Args:
        user_input: Input from the user
        ctx: Device selection context

    Returns:
        Tuple of (break_loop, connected_successfully, user_quit)
    """
    # Check if the input is a device number
    if user_input.strip():
        try:
            device_index = int(user_input.strip()) - 1

            # Stop scanning first
            ctx.stop_event.set()
            await asyncio.wait_for(
                asyncio.gather(ctx.scan_task, ctx.ui_task, return_exceptions=True),
                timeout=2.0,
            )

            try:
                # Try to connect to the selected device
                connected, user_quit = await _handle_device_selection(
                    device_index, ctx.discovered_devices, ctx.ble_manager
                )
            except ValueError:
                # Not a number, treat as invalid input
                console.print(
                    f"[bold red]Invalid input: {user_input}. Press Enter or enter a device number.[/bold red]",
                )
                await asyncio.sleep(1)  # Brief pause so user can see the error
                # Continue scanning
                ctx.ui_update_needed.set()  # Force UI refresh
                return False, False, False
            else:
                return True, connected, user_quit
        except ValueError:
            # Not a number, treat as invalid input
            console.print(
                f"[bold red]Invalid input: {user_input}. Press Enter or enter a device number.[/bold red]",
            )
            await asyncio.sleep(1)  # Brief pause so user can see the error
            # Continue scanning
            ctx.ui_update_needed.set()  # Force UI refresh
            return False, False, False
    else:
        # Empty input (just Enter key) - stop scanning and show menu
        ctx.stop_event.set()
        await asyncio.wait_for(
            asyncio.gather(ctx.scan_task, ctx.ui_task, return_exceptions=True),
            timeout=2.0,
        )
        return True, False, False


async def _cleanup_tasks(stop_event: asyncio.Event, scan_task: asyncio.Task, ui_task: asyncio.Task) -> None:
    """Clean up running tasks.

    Args:
        stop_event: Event to signal when to stop scanning
        scan_task: Scanning task
        ui_task: UI update task
    """
    # Make sure scanning is stopped
    stop_event.set()

    # Cancel any running tasks
    if not scan_task.done():
        scan_task.cancel()
        with contextlib.suppress(TimeoutError, asyncio.CancelledError):
            await asyncio.wait_for(scan_task, timeout=1.0)

    if not ui_task.done():
        ui_task.cancel()
        with contextlib.suppress(TimeoutError, asyncio.CancelledError):
            await asyncio.wait_for(ui_task, timeout=1.0)


async def dynamic_device_selection(ble_manager: BLEManager, timeout: float = 10.0) -> tuple[bool, bool]:
    """Interactive device discovery with real-time updates and concurrent user input.

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
        "complete[/bold yellow]",
    )

    # Keep track of discovered devices in order of discovery
    discovered_devices: list[bleak.BLEDevice] = []

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

    # Create the tasks
    scan_task = asyncio.create_task(_scan_for_devices(device_found_callback, stop_event, timeout))
    ui_task = asyncio.create_task(
        _update_device_table_ui(discovered_devices, ble_manager, timeout, ui_update_needed, stop_event)
    )

    # Create the context
    ctx = DeviceSelectionContext(
        ble_manager=ble_manager,
        discovered_devices=discovered_devices,
        stop_event=stop_event,
        ui_update_needed=ui_update_needed,
        scan_task=scan_task,
        ui_task=ui_task,
        timeout=timeout,
    )

    connected, user_quit = False, False

    # Set up input handling
    try:
        while not scan_task.done():
            try:
                # Wait for user input
                user_input = await asyncio.to_thread(console.input, "")

                # Handle user input
                break_loop, connected, user_quit = await _handle_user_input(user_input, ctx)

                if break_loop:
                    break

            except TimeoutError:
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
        # Clean up tasks
        await _cleanup_tasks(stop_event, scan_task, ui_task)

    # If we didn't connect during scanning, show the selection menu
    if not connected:
        # Save discovered devices to the BLE manager
        ble_manager.discovered_devices = discovered_devices.copy()
        return await _show_selection_menu(discovered_devices, ble_manager, timeout)

    return connected, user_quit


async def connect_to_device(
    ble_manager: BLEManager,
    address: str | None = None,
    name: str | None = None,
    interactive: bool = False,
    scan_timeout: float = 10.0,
) -> tuple[bool, bool]:
    """Connect to a BLE device by address, name, or interactively.

    Args:
        ble_manager: BLE Manager instance
        address: Optional device address to connect to
        name: Optional device name to connect to
        interactive: Whether to use interactive mode for device selection
        scan_timeout: Scan timeout in seconds

    Returns:
        Tuple of (connected successfully, user quit)
    """
    connected, user_quit = False, False

    # Interactive mode
    if interactive and not address and not name:
        # Use dynamic device selection instead of the old interactive selection
        connected, user_quit = await dynamic_device_selection(ble_manager, scan_timeout)

    # Connect by address
    elif address:
        console.print(f"[bold]Connecting to device with address {address}...[/bold]")
        connected = await ble_manager.connect_to_device(address)

        if connected:
            console.print(f"[bold green]Successfully connected to {address}![/bold green]")
        else:
            console.print(f"[bold red]Failed to connect to {address}![/bold red]")

    # Connect by name
    elif name:
        console.print(f"[bold]Searching for device with name '{name}'...[/bold]")
        devices = await ble_manager.discover_devices(timeout=scan_timeout, name_filter=name)

        if not devices:
            console.print(f"[bold red]No devices found with name '{name}'![/bold red]")
        else:
            # Connect to the first matching device
            device = devices[0]
            console.print(f"[bold]Connecting to {device.name} ({device.address})...[/bold]")
            connected = await ble_manager.connect_to_device(device)

            if connected:
                console.print(f"[bold green]Successfully connected to {device.address}![/bold green]")
            else:
                console.print(f"[bold red]Failed to connect to {device.address}![/bold red]")

    # No connection method specified
    else:
        console.print("[bold red]No device specified for connection![/bold red]")

    return connected, user_quit


def print_test_results(results: dict[str, Any], verbose=False):
    """Print formatted test results.

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


async def _connect_by_address(address: str, ble_manager: BLEManager, _timeout: float) -> bool:
    """Connect to a device using its address.

    Args:
        address: Device address
        ble_manager: BLE Manager instance
        _timeout: Scan timeout in seconds (unused, but kept for API consistency)

    Returns:
        True if successfully connected, False otherwise
    """
    console.print(f"[bold]Connecting to device with address {address}...[/bold]")
    connected = await ble_manager.connect_to_device(address)
    if not connected:
        console.print(f"[bold red]Failed to connect to {address}![/bold red]")
    return connected


async def _connect_by_name(name: str, ble_manager: BLEManager, timeout: float) -> bool:
    """Connect to a device using its name.

    Args:
        name: Device name (partial match)
        ble_manager: BLE Manager instance
        timeout: Scan timeout in seconds

    Returns:
        True if successfully connected, False otherwise
    """
    console.print(f"[bold]Searching for device with name '{name}'...[/bold]")
    devices = await ble_manager.discover_devices(timeout=timeout)
    matching_devices = [d for d in devices if name.lower() in (d.name or "").lower()]
    if not matching_devices:
        console.print(f"[bold red]No devices found with name containing '{name}'![/bold red]")
        return False

    device = matching_devices[0]
    console.print(f"[bold]Connecting to {device.name} ({device.address})...[/bold]")
    connected = await ble_manager.connect_to_device(device)
    if not connected:
        console.print(f"[bold red]Failed to connect to {device.address}![/bold red]")
    return connected


async def _run_test_modules(test_runner: TestRunner, all_tests: list) -> dict:
    """Run all discovered test modules.

    Args:
        test_runner: TestRunner instance
        all_tests: List of (module_name, tests) tuples

    Returns:
        Dict containing aggregated test results
    """
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

    return all_results


async def _cleanup_loop_resources(loop: asyncio.AbstractEventLoop) -> None:
    """Clean up asyncio resources from the event loop.

    Args:
        loop: The event loop to clean
    """
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


async def _discover_and_count_tests(test_runner: TestRunner, test_specifiers: list[str]) -> tuple[list, int]:
    """Discover tests and count them.

    Args:
        test_runner: TestRunner instance
        test_specifiers: List of test specifier strings

    Returns:
        Tuple of (list of test modules, total test count)
    """
    all_tests = test_runner.discover_tests(test_specifiers)
    if not all_tests:
        console.print("[bold red]No tests were discovered in any specified directories![/bold red]")
        console.print("[dim]Check that your test files begin with 'test_' and are in the correct location.[/dim]")
        return [], 0

    # Count total tests
    total_tests = sum(len(tests) for _, tests in all_tests)
    console.print(f"[bold]Found {total_tests} test(s) in {len(all_tests)} module(s)[/bold]")

    return all_tests, total_tests


async def _attempt_device_connection(args) -> tuple[BLEManager, bool]:
    """Attempt to connect to a device using the provided arguments.

    Args:
        args: Command line arguments

    Returns:
        Tuple of (BLEManager instance, connection success)
    """
    # Create BLE manager
    ble_manager = BLEManager()
    connected = False

    # Connect to device based on provided options
    if args.address:
        connected = await _connect_by_address(args.address, ble_manager, args.scan_timeout)
    elif args.name:
        connected = await _connect_by_name(args.name, ble_manager, args.scan_timeout)
    else:
        # Interactive discovery
        console.print("[bold]No device address or name specified, starting interactive device discovery...[/bold]")
        connected, user_quit = await connect_to_device(
            ble_manager,
            interactive=True,
            scan_timeout=args.scan_timeout,
        )
        if not connected and user_quit:
            console.print("[bold yellow]User quit device selection![/bold yellow]")

    if not connected:
        console.print("[bold red]Failed to connect to device![/bold red]")

    return ble_manager, connected


async def _perform_cleanup(test_runner: TestRunner, ble_manager: BLEManager, connected: bool):
    """Perform cleanup operations.

    Args:
        test_runner: TestRunner instance
        ble_manager: BLEManager instance
        connected: Whether a device is connected
    """
    # Clean up test context tasks
    try:
        await test_runner.test_context.cleanup_tasks()
    except Exception:
        logger.exception("Error cleaning up test context")

    # Disconnect from device
    if connected:
        console.print("[bold]Disconnecting from device...[/bold]")
        try:
            await ble_manager.disconnect()
        except Exception:
            logger.exception("Error during disconnect")

    # Clean up loop resources
    loop = asyncio.get_running_loop()
    await _cleanup_loop_resources(loop)

    # Log completion
    logger.debug("Cleanup complete, exiting run_ble_tests")


async def run_ble_tests(args):
    """Run BLE tests based on command line arguments."""
    # Create console for rich output
    console = get_console()

    # Create a TestRunner instance and BLE manager
    ble_manager, test_runner = None, None
    connected = False

    try:
        # Create test runner
        ble_manager, connected = await _attempt_device_connection(args)
        test_runner = TestRunner(ble_manager)

        # Exit if not connected
        if not connected:
            return

        # Discover tests
        all_tests, total_count = await _discover_and_count_tests(test_runner, args.test_specifiers)
        if not all_tests:
            return

        # Run all tests and collect results
        all_results = await _run_test_modules(test_runner, all_tests)

        # Print consolidated results
        if all_results["total_tests"] > 0:
            print_test_results(all_results, args.verbose)
        else:
            console.print("[bold red]No tests were run![/bold red]")

    finally:
        # Perform cleanup if test_runner was created
        if test_runner and ble_manager:
            await _perform_cleanup(test_runner, ble_manager, connected)


def _create_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser.

    Returns:
        Configured ArgumentParser
    """
    parser = argparse.ArgumentParser(
        description="BLE IoT Device Testing Tool - Discovers and runs tests for BLE devices. "
        "If no device address or name is provided, interactive device discovery will be used.",
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
    parser.add_argument_group("Test Options")
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

    return parser


def _cleanup_loop_on_interrupt(loop: asyncio.AbstractEventLoop):
    """Clean up the event loop after a keyboard interrupt.

    Args:
        loop: The event loop to clean up
    """
    try:
        # Cancel all remaining tasks
        remaining = asyncio.all_tasks(loop)
        if remaining:
            logger.debug(f"Cancelling {len(remaining)} remaining tasks due to keyboard interrupt")
            for task in remaining:
                task.cancel()

            # Short wait for cancellation
            with contextlib.suppress(Exception):
                loop.run_until_complete(asyncio.wait(remaining, timeout=1.0, loop=loop))

        # Close the loop
        with contextlib.suppress(Exception):
            loop.close()
    except Exception:
        logger.exception("Error during keyboard interrupt cleanup")


def _run_main_program(args):
    """Run the main program with the given arguments.

    Args:
        args: Parsed command-line arguments
    """
    # Configure logging
    setup_logging(verbose=args.verbose, log_file=args.log_file)

    logger.debug("Starting test execution")

    # Create a new event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        # Run the main coroutine
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

        # Clean up the loop
        _cleanup_loop_on_interrupt(loop)

    except Exception as e:
        logger.exception("Error during test execution")
        console.print(f"\n[bold red]Error: {e!s}[/bold red]")
        if args.verbose:
            console.print_exception()


def main():
    """Execute the main function."""
    parser = _create_parser()
    args = parser.parse_args()

    try:
        # Run the main program
        _run_main_program(args)
    finally:
        # Ensure all loggers have flushed their output
        for handler in logging.root.handlers:
            handler.flush()

        # Log clean exit
        logger.debug("Exiting program")

    return 0


if __name__ == "__main__":
    sys.exit(main())
