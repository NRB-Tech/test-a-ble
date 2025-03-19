"""Test Runner.

Discovers and executes BLE tests
"""

import asyncio
import logging
import traceback
from collections.abc import Callable
from typing import Any

from .ble_manager import BLEManager
from .test_context import TestContext, TestException, TestFailure, TestSkip, TestStatus
from .test_discovery import TestFunction, TestItem, TestNameItem, discover_tests_from_specifier

logger = logging.getLogger(__name__)


class TestRunner:
    """Discovers and runs tests against BLE devices."""

    def __init__(self, ble_manager: BLEManager):
        """Initialize the test runner.

        Args:
            ble_manager: BLE manager instance to use for tests
        """
        self.ble_manager = ble_manager
        self.test_context = TestContext(ble_manager)

    def discover_tests(self, test_specifiers: list[str]) -> list[tuple[str, list[TestNameItem]]]:
        """Discover test modules with the given specifiers.

        Args:
            test_specifiers: List of test specifiers

        Returns:
            List of tuples containing module names and their test items
        """
        tests = []
        for test_specifier in test_specifiers:
            tests.extend(discover_tests_from_specifier(test_specifier))
        return tests

    async def run_test(self, test_name: str, test_item: TestItem) -> dict[str, Any]:
        """Run a single test by name.

        Args:
            test_name: Name of the test to run
            test_item: Test item to run (function or class method tuple)

        Returns:
            Test result dictionary
        """
        # Check if test is already in results
        if (
            test_name in self.test_context.test_results
            and self.test_context.test_results[test_name]["status"] != TestStatus.RUNNING.value
        ):
            logger.debug(f"Test {test_name} already has results, skipping")
            return self.test_context.test_results[test_name]

        test_description = self._get_test_description(test_name, test_item)
        test_class_instance = None

        # Display test header
        print("\n")
        self.test_context.print(f"\033[1m\033[4mRunning test: {test_description}\033[0m")
        print("")

        self.test_context.start_test(test_description)

        try:
            if isinstance(test_item, tuple):
                test_class_instance = await self._run_class_test(test_item)
            else:
                await self._run_standalone_test(test_item)

            result = self.test_context.end_test(TestStatus.PASS)

        except (TestFailure, AssertionError) as e:
            logger.exception(f"Test {test_name} failed")
            result = self.test_context.end_test(TestStatus.FAIL, str(e))

        except TestSkip as e:
            logger.info(f"Test {test_name} skipped")
            result = self.test_context.end_test(TestStatus.SKIP, str(e))

        except TestException as e:
            logger.exception(f"Test {test_name} error")
            result = self.test_context.end_test(e.status, str(e))

        except TimeoutError as e:
            logger.exception(f"Test {test_name} error")
            result = self.test_context.end_test(TestStatus.ERROR, str(e))

        except Exception as e:
            logger.exception(f"Error running test {test_name}")
            traceback.print_exc()
            result = self.test_context.end_test(TestStatus.ERROR, str(e))

        finally:
            if test_class_instance:
                await self._run_teardown(test_class_instance, test_name)
            await self.test_context.unsubscribe_all()

        return result

    async def run_tests(self, tests: list[TestNameItem]) -> dict[str, Any]:
        """Run multiple tests in the order they were defined in the source code.

        Args:
            tests: List of tests to run

        Returns:
            Summary of test results
        """
        try:
            for test_name, test_item in tests:
                await self.run_test(test_name, test_item)
            return self.test_context.get_test_summary()
        finally:
            await self.test_context.cleanup_tasks()

    def _get_test_description(self, test_name: str, test_item: TestItem) -> str:
        """Get the description for a test.

        Args:
            test_name: Name of the test
            test_item: Test item (function or class method tuple)

        Returns:
            Test description string
        """
        if isinstance(test_item, tuple):
            _, _, method = test_item
            if hasattr(method, "_test_description") and method._test_description:
                return method._test_description
            return method.__name__

        test_func = test_item
        if hasattr(test_func, "_test_description") and test_func._test_description:
            return test_func._test_description
        return test_name.split(".")[-1]

    async def _run_class_test(self, test_item: tuple[str, Any, Callable]) -> Any:
        """Run a class-based test.

        Args:
            test_item: Tuple of (class_name, class_obj, method)

        Returns:
            Test class instance
        """
        class_name, class_obj, method = test_item
        test_class_instance = class_obj()

        # Run setUp if it exists
        if hasattr(test_class_instance, "setUp"):
            await self._run_setup(test_class_instance, class_name)

        # Run the test method
        logger.debug(f"Executing class test method: {class_name}.{method.__name__}")
        await method(test_class_instance, self.ble_manager, self.test_context)

        return test_class_instance

    async def _run_standalone_test(self, test_func: TestFunction) -> None:
        """Run a standalone test function.

        Args:
            test_func: Test function to run
        """
        logger.debug(f"Executing standalone test: {test_func.__name__}")
        await test_func(self.ble_manager, self.test_context)

    async def _run_setup(self, test_class_instance: Any, class_name: str) -> None:
        """Run the setUp method of a test class.

        Args:
            test_class_instance: Test class instance
            class_name: Name of the test class
        """
        setup = test_class_instance.setUp
        if asyncio.iscoroutinefunction(setup):
            logger.debug(f"Calling async setUp for {class_name}")
            await setup(self.ble_manager, self.test_context)
        else:
            logger.debug(f"Calling sync setUp for {class_name}")
            setup(self.ble_manager, self.test_context)

    async def _run_teardown(self, test_class_instance: Any, test_name: str) -> None:
        """Run the tearDown method of a test class.

        Args:
            test_class_instance: Test class instance
            test_name: Name of the test
        """
        try:
            if hasattr(test_class_instance, "tearDown"):
                teardown = test_class_instance.tearDown
                if asyncio.iscoroutinefunction(teardown):
                    logger.debug(f"Calling async tearDown for {test_name}")
                    await teardown(self.ble_manager, self.test_context)
                else:
                    logger.debug(f"Calling sync tearDown for {test_name}")
                    teardown(self.ble_manager, self.test_context)
        except Exception:
            logger.exception(f"Error in tearDown for {test_name}")
