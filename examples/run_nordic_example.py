#!/usr/bin/env python3
"""
Run Nordic Blinky Example.

This script demonstrates how to run the Nordic Blinky example tests programmatically.
"""
import asyncio
import logging
import os
import sys

from rich.console import Console
from rich.logging import RichHandler

from test_a_ble.ble_manager import BLEManager
from test_a_ble.test_runner import TestRunner

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)],
)
logger = logging.getLogger("nordic_example")
console = Console()


async def run_blinky_tests(device_name: str = None, device_address: str = None):
    """Run the Nordic Blinky example tests."""
    console.print("[bold]Nordic Blinky Example Test Runner[/bold]\n")

    # Create BLE manager
    ble_manager = BLEManager()

    # Discover devices
    console.print("[bold]Discovering BLE devices...[/bold]")
    devices = await ble_manager.discover_devices(timeout=5.0, name_filter=device_name, address_filter=device_address)

    if not devices:
        console.print("[bold red]No devices found![/bold red]")
        return

    # Display found devices
    console.print(f"[bold green]Found {len(devices)} devices:[/bold green]")
    for i, device in enumerate(devices):
        console.print(f"{i+1}. {device.name or 'Unknown'} ({device.address})")

    # Connect to first matching device
    target_device = devices[0]
    console.print(f"[bold]Connecting to {target_device.name or 'Unknown'} ({target_device.address})...[/bold]")

    connected = await ble_manager.connect_to_device(target_device)
    if not connected:
        console.print("[bold red]Failed to connect![/bold red]")
        return

    console.print(f"[bold green]Connected to {target_device.address}![/bold green]")

    try:
        # Discover services
        await ble_manager.discover_services()

        # Create test runner
        test_runner = TestRunner(ble_manager)

        # Get the path to the nordic blinky tests directory
        # This ensures it works both when installed and when run from source
        current_dir = os.path.dirname(os.path.abspath(__file__))
        test_dir = os.path.join(current_dir, "nordic_blinky", "tests")

        console.print(f"[bold]Discovering tests in {test_dir}...[/bold]")

        tests = test_runner.discover_tests(test_dir)
        if not tests:
            console.print("[bold red]No tests found![/bold red]")
            return

        console.print(f"[bold]Found {len(tests)} tests:[/bold]")
        for test_name in tests:
            console.print(f"- {test_name}")

        # Run tests
        console.print("[bold]Running tests...[/bold]")
        results = await test_runner.run_tests()

        # Print summary
        console.print("\n[bold]Test Results:[/bold]")
        passed = results.get("passed_tests", 0)
        failed = results.get("failed_tests", 0)
        total = results.get("total_tests", 0)

        console.print(
            f"[bold]Total:[/bold] {total} | [bold green]Passed:[/bold green] {passed} | [bold red]Failed:[/bold red]"
            f" {failed}"
        )

    finally:
        # Disconnect
        console.print("[bold]Disconnecting...[/bold]")
        await ble_manager.disconnect()
        console.print("[bold]Disconnected[/bold]")


def main():
    """Execute the main function."""
    # Parse arguments
    device_name = None
    device_address = None

    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            if ":" in arg:  # Likely an address
                device_address = arg
            else:
                device_name = arg

    # Run tests
    try:
        asyncio.run(run_blinky_tests(device_name, device_address))
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Test execution interrupted![/bold yellow]")
    except Exception as e:
        console.print(f"\n[bold red]Error: {str(e)}[/bold red]")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
