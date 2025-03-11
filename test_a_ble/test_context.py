"""
Test Context for BLE tests.

Provides environment for test execution.
"""

import asyncio
import logging
import time
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.shortcuts import PromptSession

from .ble_manager import BLEManager

logger = logging.getLogger(__name__)


# Decorator for test functions
def ble_test(description=None):
    """
    Decorate a BLE test function.

    Args:
        description: Description of the test (optional, will use function name if not provided)

    Returns:
        Decorated function
    """

    def decorator(func):
        # Set attributes on the function
        func._is_ble_test = True
        func._test_description = description

        return func

    # Handle case where decorator is used without arguments
    if callable(description):
        func = description
        description = None
        return decorator(func)

    return decorator


# Decorator for test classes
def ble_test_class(description=None):
    """
    Decorate a BLE test class.

    Args:
        description: Description of the test class (optional, will use class name if not provided)

    Returns:
        Decorated class
    """

    def decorator(cls):
        # Set attributes on the class
        cls._is_test_class = True
        cls._test_description = description

        return cls

    # Handle case where decorator is used without arguments
    if callable(description):
        cls = description
        description = None
        return decorator(cls)

    return decorator


class TestStatus(Enum):
    """Enum for test execution status."""

    PASS = "pass"  # nosec B105
    FAIL = "fail"
    SKIP = "skip"
    ERROR = "error"
    RUNNING = "running"

    def __str__(self):
        """Return the string representation of the test status."""
        return self.value


class TestException(Exception):
    """Base class for test exceptions."""

    status = TestStatus.ERROR

    def __init__(self, message=""):
        """Initialize the test exception."""
        self.message = message
        super().__init__(message)


class TestFailure(TestException):
    """Exception raised when a test fails."""

    status = TestStatus.FAIL


class TestSkip(TestException):
    """Exception raised when a test is skipped."""

    status = TestStatus.SKIP


class NotificationResult(Enum):
    """Enum for notification evaluation results."""

    IGNORE = "ignore"  # Not what we're looking for, continue waiting
    MATCH = "match"  # Found what we were looking for, success
    FAIL = "fail"  # Found something that indicates a failure condition

    def __str__(self):
        """Return the string representation of the notification result."""
        return self.value


# Type alias for notification expected value
# Can be bytes for exact matching, a callable for custom evaluation, or None to match any notification
# The callable should return a boolean (pass or fail), a notification result enum, or a tuple of
# (NotificationResult, str)
# If the callable returns a NotificationResult of FAIL, the reason should be provided in the str
NotificationExpectedValue = Optional[
    Union[
        bytes,
        Callable[[bytes], Union[bool, NotificationResult, Tuple[NotificationResult, str]]],
    ]
]


class NotificationWaiter:
    """Helper class to wait for notifications."""

    def __init__(self, characteristic_uuid: str, expected_value: NotificationExpectedValue = None):
        """Initialize the notification waiter."""
        self.characteristic_uuid = characteristic_uuid
        self.expected_value = expected_value
        self.received_notifications = []
        self.matching_notification = None  # Will store the matching notification data
        self.failure_reason = None  # Will store failure message if applicable
        self.complete_event = asyncio.Event()

    def check_notification(self, data: bytes) -> Tuple[bool, Optional[str]]:
        """
        Check if a notification matches our criteria.

        Args:
            data: The notification data to check

        Returns:
            Tuple of (is_match, failure_reason)
            - is_match: True if the notification matches expected criteria
            - failure_reason: If the notification indicates a failure condition, the reason
        """
        current_expected = self.expected_value

        if current_expected is None:
            # No expected value - any notification is a match
            return True, None

        if callable(current_expected):
            # User provided a lambda/function to evaluate the notification
            try:
                result = current_expected(data)
                if isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], NotificationResult):
                    # Handle tuple return format: (NotificationResult, Optional[str])
                    notification_result, reason = result
                    if notification_result == NotificationResult.MATCH:
                        return True, None
                    elif notification_result == NotificationResult.FAIL:
                        return (
                            False,
                            reason or f"Notification evaluated as failure condition: {data.hex()}",
                        )
                    else:  # IGNORE
                        return False, None
                elif isinstance(result, NotificationResult):
                    # Handle direct NotificationResult enum
                    if result == NotificationResult.MATCH:
                        return True, None
                    elif result == NotificationResult.FAIL:
                        return (
                            False,
                            f"Notification evaluated as failure condition: {data.hex()}",
                        )
                    else:  # IGNORE
                        return False, None
                else:
                    # True = match, False = ignore (not a failure)
                    return bool(result), None
            except Exception as e:
                # If the function raises an exception, log it but don't fail
                logger.error(f"Error in notification evaluation function: {e}")
                return False, None
        else:
            # Direct comparison with expected bytes
            return (
                data == current_expected,
                f"Notification {data.hex()} ≠ {current_expected.hex()} expected value",
            )

    def on_notification(self, data) -> bool:
        """
        Handle a notification.

        Args:
            data: The notification data

        Returns:
            True if the notification matches the expected value, False otherwise
        """
        if self.complete_event.is_set():
            return False

        # Store all notifications we receive
        self.received_notifications.append(data)

        # Check immediately if this is the notification we're waiting for
        is_match, failure_reason = self.check_notification(data)

        if is_match:
            logger.debug("Found matching notification in callback - setting event")
            self.matching_notification = data
            self.complete_event.set()
            return True
        elif failure_reason:
            # We have a failure condition from the notification
            logger.debug(f"Notification indicates failure: {failure_reason}")
            self.failure_reason = failure_reason
            self.complete_event.set()
            return False
        else:
            logger.debug("Notification in callback didn't match criteria")
            return False


class NotificationSubscription:
    """A helper class to manage notification subscriptions and waiters."""

    def __init__(self, characteristic_uuid: str, initial_waiter: NotificationWaiter = None):
        """Initialize the notification subscription."""
        self.characteristic_uuid = characteristic_uuid
        self.waiter = initial_waiter
        self.collected_notifications = []

    def on_notification(self, data):
        """Handle a notification."""
        self.collected_notifications.append(data)
        logger.debug(
            f"Notification callback received: {data.hex() if data else 'None'}, "
            f"{len(self.collected_notifications)} notifications collected"
        )
        if self.waiter is None:
            return

        if self.waiter.on_notification(data):
            self.collected_notifications.clear()

    def set_waiter(self, waiter: NotificationWaiter, process_collected_notifications: bool = True):
        """Set the waiter for the subscription."""
        self.waiter = waiter
        if process_collected_notifications:
            logger.debug(f"Processing {len(self.collected_notifications)} collected notifications")
            for i in range(len(self.collected_notifications)):
                if self.waiter.on_notification(self.collected_notifications[i]):
                    # If we found a match, clear all notifications up to and including the current one
                    self.collected_notifications = self.collected_notifications[i + 1 :]
                    break

    def clear_waiter(self):
        """Clear the waiter for the subscription."""
        self.waiter = None


class TestContext:
    """
    Context for test execution.

    Provides access to the BLE device and helper methods for test operations.
    """

    def __init__(self, ble_manager: BLEManager):
        """Initialize the test context."""
        self.ble_manager = ble_manager
        self.start_time = time.time()
        self.test_results: Dict[str, Dict[str, Any]] = {}
        self.current_test: Optional[str] = None
        self.notification_subscriptions: Dict[str, NotificationSubscription] = {}

    def print_formatted_box(self, title: str, messages: List[str]) -> None:
        """
        Print a formatted box with consistent alignment.

        Args:
            title: The title to display at the top of the box
            messages: List of message lines to display in the box
        """
        # Box width (including borders)
        box_width = 80
        content_width = box_width - 4  # Allow for borders and spaces

        # Print top border
        print("\n╔" + "═" * (box_width - 2) + "╗")

        # Print title if provided
        if title:
            # Ensure title fits in box with proper padding
            if len(title) > content_width:
                title = title[: content_width - 3] + "..."

            padding = " " * (content_width - len(title))
            print(f"║ {title}{padding} ║")

        # Print messages
        for message in messages:
            # Pre-process message to handle newlines properly
            message_parts = message.split("\n")
            for part in message_parts:
                # Split long lines into multiple lines with word wrap
                remaining = part
                while remaining:
                    if len(remaining) <= content_width:
                        # Line fits, use it completely
                        line = remaining
                        remaining = ""
                    else:
                        # Try to break at word boundary
                        split_pos = remaining[:content_width].rfind(" ")
                        if split_pos <= 0:  # No space found or at beginning, just split at max length
                            split_pos = content_width

                        line = remaining[:split_pos].rstrip()
                        remaining = remaining[split_pos:].lstrip() if split_pos < len(remaining) else ""

                    # Ensure padding for a uniform right edge
                    padding = " " * (content_width - len(line))
                    print(f"║ {line}{padding} ║")

        # Print bottom border
        print("╚" + "═" * (box_width - 2) + "╝")

    def print(self, message: str) -> None:
        """
        Print a message directly to the console for user-facing output.

        Use this for information that should always be visible to the user,
        regardless of log level settings.

        Args:
            message: The message to display to the user
        """
        # Print the message with ANSI codes intact
        print(message)

        # Strip ANSI escape codes for logging
        import re

        ansi_escape = re.compile(r"\033\[[0-9;]*[a-zA-Z]")
        clean_message = ansi_escape.sub("", message)

        # Also log the message at INFO level for record keeping
        logger.info(clean_message)

        # Store in test results with level information
        if self.current_test:
            self.test_results[self.current_test]["logs"].append(
                {
                    "timestamp": time.time(),
                    "level": "USER",  # Special level to mark user-facing output
                    "message": clean_message,
                }
            )

    def prompt_user(self, message: str) -> str:
        """
        Display a prompt to the user and wait for input.

        Args:
            message: The message to display to the user

        Returns:
            User's input response
        """
        # Use the formatted box function
        self.print_formatted_box("USER ACTION REQUIRED", [message])

        response = input("Enter your response and press Enter to continue: ")
        logger.info(f"User response: {response}")
        return response

    def start_test(self, test_name: str) -> None:
        """
        Start a new test and record the start time.

        Args:
            test_name: Name of the test being started
        """
        self.current_test = test_name
        self.test_results[test_name] = {
            "start_time": time.time(),
            "status": TestStatus.RUNNING.value,
            "duration": 0,
            "logs": [],
        }
        logger.debug(f"Starting test: {test_name}")

    async def unsubscribe_all(self) -> None:
        """
        Unsubscribe from all active notification subscriptions.

        Call this at the end of a test to clean up resources.
        """
        if not self.notification_subscriptions:
            return

        # Make a copy of the keys since we'll be modifying the dictionary
        characteristics = list(self.notification_subscriptions.keys())

        for characteristic_uuid in characteristics:
            try:
                logger.debug(f"Unsubscribing from {characteristic_uuid}")
                await self.ble_manager.unsubscribe_from_characteristic(characteristic_uuid)
                # Remove from subscriptions
                self.notification_subscriptions.pop(characteristic_uuid, None)
                logger.debug(f"Successfully unsubscribed from {characteristic_uuid}")
            except Exception as e:
                logger.error(f"Error unsubscribing from {characteristic_uuid}: {str(e)}")

        logger.debug(f"Unsubscribed from all {len(characteristics)} active characteristics")

    async def cleanup_tasks(self):
        """
        Clean up any remaining async tasks created during testing.

        This should be called before program exit.
        """
        # Unsubscribe from all notifications
        await self.unsubscribe_all()

        # Clear any remaining state
        logger.debug("Cleanup tasks completed")

    def end_test(self, status: Union[TestStatus, str], message: str = "") -> Dict[str, Any]:
        """
        End the current test and record results.

        Args:
            status: Test status (TestStatus enum or string value)
            message: Optional message about test result

        Returns:
            Test result details
        """
        if not self.current_test:
            logger.warning("Attempted to end test but no test is currently running")
            return {}

        end_time = time.time()
        test_name = self.current_test

        # Convert string status to enum if needed
        if isinstance(status, str):
            try:
                # Try to convert the string to enum
                status = next(s for s in TestStatus if s.value == status)
            except StopIteration:
                logger.warning(f"Unknown test status '{status}', using as-is")

        # Get the string value if it's an enum
        status_value = status.value if isinstance(status, TestStatus) else status

        # Update test results
        self.test_results[test_name].update(
            {
                "end_time": end_time,
                "duration": end_time - self.test_results[test_name]["start_time"],
                "status": status_value,
                "message": message,
            }
        )

        # Define color codes for different statuses
        status_display = {
            TestStatus.PASS.value: "\033[92mPASSED ✓\033[0m",  # Green
            TestStatus.FAIL.value: "\033[91mFAILED ✗\033[0m",  # Red
            TestStatus.SKIP.value: "\033[93mSKIPPED -\033[0m",  # Yellow
            TestStatus.ERROR.value: "\033[93mERROR !\033[0m",  # Yellow
        }.get(status_value, status_value.upper())

        # Print a simpler message instead of a formatted box
        # Only use formatted boxes for things that need user attention
        duration = self.test_results[test_name]["duration"]
        print("")  # Add space before result for visual separation
        self.print(f"Test {test_name} {status_display} in {duration:.2f}s" + (f": {message}" if message else ""))
        print("")  # Add space after result

        # Also log for record keeping
        logger.info(f"Test {test_name} {status_value}{': ' + message if message else ''}")
        logger.debug(f"Test duration: {self.test_results[test_name]['duration']:.2f} seconds")

        # Reset current test
        self.current_test = None

        # Return the results
        return self.test_results[test_name]

    def log(self, message: str, level: str = "info") -> None:
        """
        Log a message within the current test context.

        Args:
            message: Message to log
            level: Log level (debug, info, warning, error, critical)
        """
        # Convert string level to logging level
        log_level = getattr(logging, level.upper(), logging.INFO)

        # Always store in test results with level information for later retrieval
        if self.current_test:
            self.test_results[self.current_test]["logs"].append(
                {"timestamp": time.time(), "level": level.upper(), "message": message}
            )

        # Only display INFO and DEBUG logs in the console if the test fails
        # WARNING, ERROR, CRITICAL logs are always displayed
        if log_level >= logging.WARNING:  # WARNING=30, ERROR=40, CRITICAL=50
            # Always log warnings, errors, and critical messages
            logger.log(log_level, message)
        else:
            # For INFO and DEBUG logs, we only store them but don't display during test execution
            # They will be displayed in the results summary if the test fails
            pass

    def debug(self, message: str) -> None:
        """Log a debug message within the current test context."""
        self.log(message, level="debug")

    def info(self, message: str) -> None:
        """Log an info message within the current test context."""
        self.log(message, level="info")

    def warning(self, message: str) -> None:
        """Log a warning message within the current test context."""
        self.log(message, level="warning")

    def error(self, message: str) -> None:
        """Log an error message within the current test context."""
        self.log(message, level="error")

    def critical(self, message: str) -> None:
        """Log a critical message within the current test context."""
        self.log(message, level="critical")

    async def subscribe_to_characteristic(
        self,
        characteristic_uuid: str,
        waiter: Optional[NotificationWaiter] = None,
        process_collected_notifications: bool = True,
    ):
        """
        Subscribe to a characteristic and create a waiter if provided.

        Args:
            characteristic_uuid: UUID of characteristic to subscribe to
            waiter: Optional NotificationWaiter instance to use
            process_collected_notifications: If True, process collected notifications
        """
        # Only subscribe if not already subscribed
        if characteristic_uuid not in self.notification_subscriptions:
            try:
                logger.debug(f"Subscribing to characteristic {characteristic_uuid}")
                # Create the waiter first
                sub = NotificationSubscription(characteristic_uuid, waiter)
                self.notification_subscriptions[characteristic_uuid] = sub

                # Now subscribe with on_notification
                await self.ble_manager.subscribe_to_characteristic(characteristic_uuid, sub.on_notification)
                logger.debug(f"Successfully subscribed to {characteristic_uuid}")

                # Short delay to ensure subscription is active
                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"Error subscribing to characteristic: {str(e)}")
                # Remove the waiter if we failed to subscribe
                if characteristic_uuid in self.notification_subscriptions:
                    del self.notification_subscriptions[characteristic_uuid]
                raise RuntimeError(f"Failed to subscribe: {str(e)}")
        else:
            # Already subscribed - reuse the existing subscription
            logger.debug(f"Using existing subscription to {characteristic_uuid}")
            # Get existing subscription and update the waiter
            sub = self.notification_subscriptions[characteristic_uuid]
            if waiter:
                sub.set_waiter(waiter, process_collected_notifications)
            else:
                sub.clear_waiter()

        return sub

    async def create_notification_waiter(
        self,
        characteristic_uuid: str,
        expected_value: NotificationExpectedValue = None,
        process_collected_notifications: bool = True,
    ) -> NotificationWaiter:
        """
        Create a notification waiter for a characteristic.

        Args:
            characteristic_uuid: UUID of characteristic to wait for notification
            expected_value: If provided, validates the notification value. Can be:
                - bytes: exact value to match
                - callable: function that takes the notification data and returns a NotificationResult

        Returns:
            NotificationWaiter instance
        """
        waiter = NotificationWaiter(characteristic_uuid, expected_value)

        await self.subscribe_to_characteristic(characteristic_uuid, waiter, process_collected_notifications)

        return waiter

    def handle_notification_waiter_result(self, waiter: NotificationWaiter, timeout: float) -> Dict[str, Any]:
        """
        Handle the result of a notification waiter.

        Args:
            waiter: The notification waiter to check
            timeout: The timeout value that was used (for error messages)

        Returns:
            Dictionary with notification details if successful:
                'value': The notification value that matched the expected value (bytes)
                'success': True if notification received and matched expected
                'received_notifications': List of all notifications received (list of bytes)

        Raises:
            TestFailure: If a notification indicates a test failure
            TimeoutError: If no notification was received within the timeout period
        """
        if waiter.matching_notification:
            logger.debug(
                "Found matching notification: "
                f"{waiter.matching_notification.hex() if waiter.matching_notification else 'None'}"
            )
            return {
                "value": waiter.matching_notification,
                "success": True,
                "received_notifications": waiter.received_notifications,
            }
        elif waiter.failure_reason:
            # We got a failure notification
            logger.info(f"Test failed due to notification: {waiter.failure_reason}")
            raise TestFailure(waiter.failure_reason)
        elif waiter.received_notifications:
            # We got notifications but none matched our expected value
            logger.info(
                f"Received {len(waiter.received_notifications)} notifications, but none matched the expected value"
            )
            for i, notif in enumerate(waiter.received_notifications):
                logger.debug(f"Notification {i+1}: {notif.hex() if notif else 'None'}")

            # Raise exception for non-matching notifications
            raise TestFailure(
                f"No matching notification received. Got: {', '.join(n.hex() for n in waiter.received_notifications)}"
            )
        else:
            # Raise timeout error with user-friendly message
            raise TimeoutError(f"No notification received within {timeout} seconds")

    async def wait_for_notification(
        self,
        characteristic_uuid: str,
        timeout: float = 10.0,
        expected_value: NotificationExpectedValue = None,
        process_collected_notifications: bool = True,
    ) -> Dict[str, Any]:
        """
        Wait for a notification from a characteristic without user interaction.

        Args:
            characteristic_uuid: UUID of characteristic to wait for notification
            timeout: Maximum time to wait in seconds
            expected_value: If provided, validates the notification value. Can be:
                - bytes: exact value to match
                - callable: function that takes the notification data and returns a NotificationResult

        Returns:
            Dictionary with notification details:
                'value': The notification value
                'success': True if notification received and matched expected
                'received_notifications': List of all notifications received

        Raises:
            TimeoutError: If no notification is received within the timeout
            TestFailure: If a notification is received but doesn't match expected criteria
        """
        waiter = await self.create_notification_waiter(
            characteristic_uuid, expected_value, process_collected_notifications
        )

        try:
            # Create a task that will complete when a notification is received
            notification_future = asyncio.create_task(waiter.complete_event.wait())

            # Wait for notification or timeout
            try:
                await asyncio.wait_for(notification_future, timeout)
                logger.debug("Notification received before timeout")
            except asyncio.TimeoutError:
                logger.info(f"Timed out waiting for notification after {timeout} seconds")
                if notification_future.cancel():
                    logger.debug("Successfully cancelled notification future")
        finally:
            pass  # We'll keep the subscription active for potential future notifications

        return self.handle_notification_waiter_result(waiter, timeout)

    async def wait_for_notification_interactive(
        self,
        characteristic_uuid: str,
        timeout: float = 10.0,
        expected_value: NotificationExpectedValue = None,
    ) -> Dict[str, Any]:
        """
        Wait for a notification from a characteristic with user interaction support.

        This method will display a prompt to the user and wait for a notification.
        The user can type 's' or 'skip' to skip the test, or 'f' or 'fail' to fail it.
        If the user chooses to skip or fail, the appropriate TestSkip or TestFailure
        exception will be raised automatically.

        Args:
            characteristic_uuid: UUID of characteristic to wait for notification
            timeout: Maximum time to wait in seconds
            expected_value: If provided, validates the notification value. Can be:
                - bytes: exact value to match
                - callable: function that takes the notification data and returns a NotificationResult

        Returns:
            Dictionary with notification details:
                'value': The notification value
                'success': True if notification received and matched expected
                'received_notifications': List of all notifications received

        Raises:
            TestSkip: If the user chooses to skip the test
            TestFailure: If the user chooses to fail the test
            TimeoutError: If no notification is received within the timeout
        """

        async def user_input_handler() -> Tuple[str, str]:
            """Handle user input during the waiting period."""
            print("\nThe test will continue automatically when event is detected.")
            print(
                "If nothing happens, type 's' or 'skip' to skip, 'f' or 'fail' to fail the test, or 'd' for debug info."
            )

            session = PromptSession()
            with patch_stdout():
                while True:
                    user_input = None
                    try:
                        user_input = await session.prompt_async()
                    except (EOFError, KeyboardInterrupt):
                        # Handle Ctrl+D and Ctrl+C gracefully
                        user_input = "f"  # Treat as "fail" to abort the test
                    except asyncio.CancelledError:
                        # Task cancelled - exit cleanly
                        logger.debug("User input task cancelled")
                        break
                    except Exception as e:
                        logger.error(f"Error in user input handler: {e}")
                        break

                    # Handle EOF or errors
                    if not user_input:
                        logger.info("Input stream closed or returned empty input")
                        break

                    user_input = user_input.strip().lower()

                    # Process based on user input
                    if user_input in ["s", "skip"]:
                        return ("skip", "User chose to skip the test")
                    elif user_input in ["f", "fail"]:
                        return ("fail", "User reported test failure")
                    elif user_input == "d":
                        # Debug - show received notifications
                        if characteristic_uuid not in self.notification_subscriptions:
                            print(f"No subscription to {characteristic_uuid}")
                            continue

                        sub = self.notification_subscriptions[characteristic_uuid]
                        if sub.waiter is None:
                            print(f"No waiter for {characteristic_uuid}")
                            continue

                        if len(sub.waiter.received_notifications) == 0:
                            print(f"No notifications received for {characteristic_uuid}")
                            continue

                        print(f"Received {len(sub.waiter.received_notifications)} notifications so far:")
                        for i, n in enumerate(sub.waiter.received_notifications):
                            print(f"  Notification {i+1}: {n.hex() if n else 'None'}")
                            is_match, _ = sub.waiter.check_notification(n)
                            if is_match:
                                print("  --> This notification MATCHES the expected criteria")
                            else:
                                print("  --> Does NOT match expected criteria")

                        # Continue waiting - don't break the loop
                    else:
                        print("Invalid input. Type 's' to skip, 'f' to fail, or 'd' for debug info.")

        waiter = await self.create_notification_waiter(characteristic_uuid, expected_value, False)

        # Start user input handler
        user_input_task = asyncio.create_task(user_input_handler())

        # Create a task for monitoring the notification event
        notification_task = asyncio.create_task(waiter.complete_event.wait())

        try:
            # Wait for the first of the tasks to complete or for timeout
            done, pending = await asyncio.wait(
                [notification_task, user_input_task],
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Determine which task completed first
            if notification_task in done:
                logger.info("Notification task completed first")
                return self.handle_notification_waiter_result(waiter, timeout)
            elif user_input_task in done:
                # User input finished first
                user_response, message = user_input_task.result()
                logger.info(f"User input task completed first: {message}")

                # Raise appropriate exception based on user input
                if user_response == "skip":
                    raise TestSkip("User chose to skip test")
                elif user_response == "fail":
                    raise TestFailure("User reported test failure")
            else:
                logger.info("Timeout occurred while waiting for notification or user input")

            # Cancel any pending tasks
            for task in pending:
                task.cancel()

        finally:
            # Make sure all tasks are cancelled
            for task in [notification_task, user_input_task]:
                if not task.done():
                    task.cancel()
                    try:
                        await asyncio.wait_for(task, timeout=0.1)
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        pass

    def get_test_summary(self) -> Dict[str, Any]:
        """
        Generate a summary of all test results.

        Returns:
            Dictionary with test summary statistics
        """
        # Filter out tests that are still in 'running' status - these are duplicate entries
        completed_results = {
            name: result
            for name, result in self.test_results.items()
            if result.get("status") != TestStatus.RUNNING.value
        }

        total_tests = len(completed_results)
        passed_tests = sum(1 for result in completed_results.values() if result["status"] == TestStatus.PASS.value)
        failed_tests = sum(1 for result in completed_results.values() if result["status"] == TestStatus.FAIL.value)
        total_duration = sum(result["duration"] for result in completed_results.values() if "duration" in result)

        return {
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": failed_tests,
            "total_duration": total_duration,
            "results": self.test_results,  # Return all results for debugging, filtering happens in CLI
        }
