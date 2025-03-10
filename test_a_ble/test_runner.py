"""
Test Runner.

Discovers and executes BLE tests
"""

import asyncio
import fnmatch
import importlib
import importlib.util
import inspect
import logging
import os
import re
import sys
import traceback
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple, Union

from .ble_manager import BLEManager
from .test_context import TestContext, TestException, TestFailure, TestSkip, TestStatus

logger = logging.getLogger(__name__)

# Type for test function
TestFunction = Callable[[BLEManager, TestContext], Coroutine[Any, Any, None]]

# Type for test item: a test function or (class_name, class_obj, method) tuple
TestItem = Union[Callable, Tuple[str, Any, Callable]]
# Type for test: (test_name, test_item)
TestNameItem = Tuple[str, TestItem]


class TestRunner:
    """Discovers and runs tests against BLE devices."""

    def __init__(self, ble_manager: BLEManager):
        """Initialize the test runner."""
        self.ble_manager = ble_manager
        self.test_context = TestContext(ble_manager)

    def _is_package(self, path: str) -> bool:
        """
        Check if a directory is a Python package (has __init__.py file).

        Args:
            path: Path to check

        Returns:
            True if the path is a Python package, False otherwise
        """
        return os.path.isdir(path) and os.path.exists(os.path.join(path, "__init__.py"))

    def _import_package(self, package_path: str, base_package: str = "") -> str:
        """
        Import a Python package and all its parent packages.

        Args:
            package_path: Absolute path to the package
            base_package: Base package name

        Returns:
            The imported package name
        """
        logger.debug(f"Importing package: {package_path}")

        # Get the package name from the path
        package_name = os.path.basename(package_path)

        # Construct the full package name
        if base_package:
            full_package_name = f"{base_package}.{package_name}"
        else:
            full_package_name = package_name

        # Check if package is already imported
        if full_package_name in sys.modules:
            logger.debug(f"Package {full_package_name} already imported")
            return full_package_name

        # Find the __init__.py file
        init_path = os.path.join(package_path, "__init__.py")

        if not os.path.exists(init_path):
            raise ImportError(f"No __init__.py found in {package_path}")

        try:
            # Import the package
            spec = importlib.util.spec_from_file_location(full_package_name, init_path)
            if not spec or not spec.loader:
                raise ImportError(f"Failed to load module spec for {init_path}")

            module = importlib.util.module_from_spec(spec)
            sys.modules[full_package_name] = module

            # Execute the module
            spec.loader.exec_module(module)
            logger.debug(f"Successfully imported package: {full_package_name}")

            return full_package_name
        except Exception as e:
            raise ImportError(f"Error importing package {full_package_name}: {str(e)}") from e

    def _find_and_import_nearest_package(self, path: str) -> Optional[Tuple[str, str]]:
        """
        Find the nearest package in the given path and import it.

        Args:
            path: Path to search for a package

        Returns:
            Tuple of (package_name, package_dir) if a package is found, None otherwise
        """
        current_dir = path
        parent_count = 0

        # Check up to 2 parent directories for __init__.py
        while parent_count < 2:
            if self._is_package(current_dir):
                # Found a module - use this as our base
                package_dir = current_dir
                package_name = os.path.basename(current_dir)
                logger.debug(f"Found package: {package_name} at {package_dir}")

                try:
                    self._import_package(current_dir)
                    return package_name, package_dir
                except ImportError as e:
                    logger.error(f"Error importing package {current_dir}: {str(e)}")
                    raise

            # Move up to the parent directory
            parent_dir = os.path.dirname(current_dir)
            if parent_dir == current_dir:  # We've reached the root
                return None

            current_dir = parent_dir
            parent_count += 1

        return None

    def _discover_tests_from_specifier(self, test_specifier: str) -> List[Tuple[str, List[TestNameItem]]]:
        """
        Parse a test specifier.

        Args:
            test_specifier: Test specifier

        Returns:
            List of tuples (module_name, test_items) where test_items is a list of tuples (test_name, test_item) where
            test_item is a test function or (class, method) tuple
        """

        def check_if_file_exists(test_dir: str, test_file: str) -> Optional[Tuple[str, str]]:
            """
            Check if a file exists in the given directory.

            Returns:
                Tuple of (test_dir, test_file) if the file exists, None otherwise
            """
            if test_file is None:
                return None
            if not os.path.isdir(test_dir):
                return None
            if not test_file.endswith(".py"):
                test_file = test_file + ".py"
            if os.path.isfile(os.path.join(test_dir, test_file)):
                return (test_dir, test_file)
            if os.path.isfile(os.path.join(test_dir, "tests", test_file)):
                return (os.path.join(test_dir, "tests"), test_file)
            return None

        def check_wildcard_match(test_wildcard: Optional[str], test_string: str) -> bool:
            """
            Check if the test string matches the test wildcard.

            Args:
                test_wildcard: Wildcard to match against
                test_string: String to match

            Returns:
                True if the test string matches the test wildcard, False otherwise
            """
            return test_wildcard is None or fnmatch.fnmatch(test_string, test_wildcard)

        def find_files_matching_wildcard(test_dir: str, test_file_wildcard: Optional[str] = None) -> List[str]:
            """
            Find files matching the wildcard (or any file if test_file_wildcard is None) in the given directory.

            Args:
                test_dir: Directory to search in
                test_file_wildcard: Wildcard to match against, or None to match any file

            Returns:
                List of files matching the wildcard
            """
            if not os.path.isdir(test_dir):
                return None
            # list files in test_dir that match the wildcard
            files = []
            for file in os.listdir(test_dir):
                if file.endswith(".py") and check_wildcard_match(test_file_wildcard, file):
                    files.append(file)
            return files

        def find_tests_in_module(
            package_dir: str,
            package_path: str,
            import_name: str,
            test_dir: str,
            test_file: str,
            method_or_wildcard: Optional[str] = None,
        ) -> List[TestNameItem]:
            """
            Find tests in the given module.

            Args:
                package_dir: Directory of the package
                package_path: Path to the package (in dot notation)
                import_name: Import name of the module
                method_or_wildcard: Method name or wildcard of the tests to
                                    find, or None to find all tests in the module

            Returns:
                List of tuples (test_name, test_item) where test_item is a test function or (class, method) tuple
            """
            file_path = os.path.join(test_dir, test_file)
            try:
                # Try to import the module using importlib.import_module first
                try:
                    if package_dir is not None:
                        # If we have a module, try to use standard import
                        module = importlib.import_module(import_name)
                        logger.debug(f"Imported {import_name} using import_module")
                    else:
                        # No module structure, use direct file import
                        raise ImportError("Not in a package, using spec_from_file_location")

                except ImportError:
                    # Fallback to the file-based import method
                    spec = importlib.util.spec_from_file_location(import_name, file_path)

                    if not spec or not spec.loader:
                        raise ImportError(f"Failed to load module spec for {file_path}")

                    module = importlib.util.module_from_spec(spec)
                    # Add the module to sys.modules to allow relative imports
                    sys.modules[import_name] = module

                    # Execute the module
                    spec.loader.exec_module(module)
                    logger.debug(f"Imported {import_name} using spec_from_file_location")

                # Use the relative path from test_dir as the module prefix for test names
                rel_path = os.path.relpath(file_path, test_dir)
                rel_module = os.path.splitext(rel_path)[0].replace(os.path.sep, ".")

                # First, discover test classes
                class_tests = []
                for class_name, class_obj in module.__dict__.items():
                    # Check if it's a class and follows naming convention
                    if inspect.isclass(class_obj) and (
                        class_name.startswith("Test")
                        or (hasattr(class_obj, "_is_test_class") and class_obj._is_test_class)
                    ):
                        # Store class for later use
                        class_full_name = f"{rel_module}.{class_name}"
                        logger.debug(f"Discovered test class: {class_full_name}")

                        # Discover test methods in the class and collect with source line numbers
                        class_method_tests = []
                        for method_name, method_obj in inspect.getmembers(class_obj, predicate=inspect.isfunction):
                            if not check_wildcard_match(method_or_wildcard, method_name):
                                continue

                            # Check if the method is a test method
                            is_test = (
                                hasattr(method_obj, "_is_ble_test") and method_obj._is_ble_test
                            ) or method_name.startswith("test_")

                            if is_test:
                                # Check if the method is a coroutine function
                                if asyncio.iscoroutinefunction(method_obj) or inspect.iscoroutinefunction(method_obj):
                                    test_name = f"{class_full_name}.{method_name}"

                                    # Get line number for sorting
                                    line_number = inspect.getsourcelines(method_obj)[1]

                                    # Store tuple of (test_name, class_name, class_obj, method, line_number)
                                    class_method_tests.append(
                                        (
                                            test_name,
                                            class_full_name,
                                            class_obj,
                                            method_obj,
                                            line_number,
                                        )
                                    )
                                    logger.debug(f"Discovered class test method: {test_name} at line {line_number}")
                                else:
                                    logger.warning(
                                        f"Method {method_name} in class {class_full_name} is not a coroutine function, "
                                        "skipping"
                                    )

                        # Sort class methods by line number to preserve definition order
                        class_method_tests.sort(key=lambda x: x[4])

                        # Add sorted methods to class_tests
                        class_tests.extend(class_method_tests)

                # Then, discover standalone test functions
                function_tests = []
                for name, obj in module.__dict__.items():
                    if not check_wildcard_match(method_or_wildcard, name):
                        continue

                    # Check if the function is decorated with @ble_test or starts with test_
                    is_test = (hasattr(obj, "_is_ble_test") and obj._is_ble_test) or name.startswith("test_")

                    if is_test and callable(obj) and not inspect.isclass(obj):
                        # Don't process methods that belong to test classes (already handled)
                        if any(t[2] == obj for t in class_tests):
                            continue

                        # Check if the function is a coroutine function
                        if asyncio.iscoroutinefunction(obj) or inspect.iscoroutinefunction(obj):
                            test_name = f"{rel_module}.{name}"

                            # Get line number for sorting
                            line_number = inspect.getsourcelines(obj)[1]

                            # Store tuple of (test_name, function, line_number)
                            function_tests.append((test_name, obj, line_number))
                            logger.debug(f"Discovered standalone test: {test_name} at line {line_number}")
                        else:
                            logger.warning(f"Function {name} in {file_path} is not a coroutine function, skipping")

                # Sort standalone functions by line number
                function_tests.sort(key=lambda x: x[2])

                tests = []
                # Add class tests to the order list first
                for test_name, class_name, class_obj, method_obj, _ in class_tests:
                    tests.append((test_name, (class_name, class_obj, method_obj)))

                # Then add standalone function tests to maintain file definition order
                for test_name, obj, _ in function_tests:
                    tests.append((test_name, obj))

                return tests

            except ImportError as e:
                logger.error(f"Import error loading module {import_name}: {str(e)}")
                logger.info(f"File path: {file_path}")
                logger.info(f"Current sys.path: {sys.path}")

                raise
            except Exception as e:
                logger.error(f"Error loading module {import_name}: {str(e)}")
                logger.debug(f"Exception details: {traceback.format_exc()}")
                raise

        def find_tests_in_file(
            package_dir: Optional[str],
            test_dir: str,
            test_file: str,
            method_or_wildcard: Optional[str] = None,
        ) -> List[TestNameItem]:
            """
            Find tests in the given file.

            Args:
                package_dir: Directory of the package
                test_dir: Directory of the test
                test_file: File to find tests in
                method_or_wildcard: Method name or wildcard of the tests to find, or None to find all tests in the file

            Returns:
                List of tuples (test_name, test_item) where test_item is a test function or (class, method) tuple
            """
            # first we need to import the test file. If we are in a package, we need to import the file from the
            # package, otherwise we need to import the file from the test directory
            if package_dir is not None:
                # find additional path beyond package_dir to the file
                rel_path = os.path.relpath(test_dir, package_dir)
                package_name = os.path.basename(package_dir)
                if rel_path == ".":
                    # File is directly in the module directory
                    package_path = None
                    import_name = f"{package_name}.{test_file}"
                else:
                    # File is in a subdirectory
                    package_path = rel_path.replace(os.path.sep, ".")
                    import_name = f"{package_name}.{package_path}.{test_file}"

            else:
                # No module structure, just import the file directly
                package_path = None
                import_name = os.path.basename(test_file)
                # Add the test directory to sys.path to allow importing modules from it
                if test_dir not in sys.path:
                    sys.path.insert(0, test_dir)
                    logger.debug(f"Added {test_dir} to sys.path")

            return find_tests_in_module(
                package_dir,
                package_path,
                import_name,
                test_dir,
                test_file,
                method_or_wildcard,
            )

        tests = {}
        # Split the specifier by both '.' and '/' or '\' to handle different path formats
        path_parts = re.split(r"[./\\]", test_specifier)
        starts_with_slash = (
            test_specifier[0] if test_specifier.startswith("/") or test_specifier.startswith("\\") else ""
        )

        # If the specifier is empty after splitting, skip it
        if not path_parts or all(not part for part in path_parts):
            logger.warning(f"Warning: Empty specifier after splitting: '{test_specifier}'")
            return tests

        # Check if the last path part contains a wildcard
        wildcard = None
        if path_parts and "*" in path_parts[-1]:
            wildcard = path_parts[-1]
            path_parts = path_parts[:-1]
            logger.debug(f"Extracted wildcard '{wildcard}' from path parts")

        test_dir = None
        test_file = None
        test_method = None

        for i in range(min(3, len(path_parts))):
            # create a possible path from the path_parts
            possible_path = os.path.join(*path_parts[:-i]) if i > 0 else os.path.join(*path_parts)
            logger.debug(f"possible_path {i}: {possible_path}")
            if starts_with_slash:
                possible_path = starts_with_slash + possible_path
            if os.path.isdir(possible_path):
                test_dir = possible_path
                if i > 1:
                    test_file = path_parts[-i]
                    test_method = path_parts[-i + 1]
                elif i > 0:
                    test_file = path_parts[-i]
                    test_method = None
                else:
                    test_file = None
                    test_method = None
                break
            tmp_dir = os.path.dirname(possible_path)
            tmp_file = os.path.basename(possible_path)
            if result := check_if_file_exists(tmp_dir, tmp_file):
                test_dir, test_file = result
                logger.debug(f"Found test_dir: {test_dir}, test_file: {test_file}")
                if i > 0:
                    test_method = path_parts[-i]
                else:
                    test_method = None
                break
        if test_dir is None:
            # Not found a dir yet, so specifier is not dir or file in current directory
            test_dir = os.getcwd()
            test_file = None
            if test_specifier == "all":
                logger.debug(f"Finding all tests in {test_dir}")
            elif len(path_parts) > 0 and (result := check_if_file_exists(test_dir, path_parts[-1])):
                test_dir, test_file = result
                logger.debug(f"Found test_dir: {test_dir}, test_file: {test_file}")

        test_dir = os.path.abspath(test_dir)

        logger.debug(f"test_dir: {test_dir}, test_file: {test_file}, test_method: {test_method}")

        if test_file is None:  # find all files in test_dir
            test_file_wildcard = wildcard if test_method is None else None
            test_files = find_files_matching_wildcard(test_dir, test_file_wildcard or "test_*")
            if not test_files:
                if os.path.isdir(os.path.join(test_dir, "tests")):
                    test_dir = os.path.join(test_dir, "tests")
                    test_files = find_files_matching_wildcard(test_dir, test_file_wildcard or "test_*")
                if not test_files:
                    test_files = find_files_matching_wildcard(test_dir, "test_*")
                    if not test_files:
                        raise ValueError(f"No test files found in {test_dir}")
                    test_method = wildcard
                    test_file_wildcard = None
            if test_file_wildcard is not None:
                # do not reuse wildcard for method search
                wildcard = None
        else:
            test_files = [test_file]

        if test_method is None and wildcard is not None:
            test_method = wildcard

        logger.debug(f"Discovering tests in test_dir: {test_dir}, test_file: {test_file}, test_method: {test_method}")
        package_name, package_dir = self._find_and_import_nearest_package(test_dir)
        tests = []
        for test_file in test_files:
            module_name = os.path.splitext(os.path.basename(test_file))[0]
            module_tests = find_tests_in_file(package_dir, test_dir, test_file, test_method)
            tests.append((module_name, module_tests))

        tests.sort(key=lambda x: x[0])

        return tests

    def discover_tests(self, test_specifiers: List[str]) -> List[Tuple[str, List[TestNameItem]]]:
        """
        Discover test modules with the given specifiers.

        Args:
            test_specifiers: List of test specifiers

        Returns:
            Dictionary mapping test names to test functions or (class, method) tuples
        """
        tests = []
        for test_specifier in test_specifiers:
            tests.extend(self._discover_tests_from_specifier(test_specifier))
        return tests

    async def run_test(self, test_name: str, test_item: TestItem) -> Dict[str, Any]:
        """
        Run a single test by name.

        Args:
            test_name: Name of the test to run

        Returns:
            Test result dictionary
        """
        # Check if test is already in results (might have been directly started by another test)
        if (
            test_name in self.test_context.test_results
            and self.test_context.test_results[test_name]["status"] != TestStatus.RUNNING.value
        ):
            logger.debug(f"Test {test_name} already has results, skipping")
            return self.test_context.test_results[test_name]

        # Get the test description
        test_description = None

        # Handle class method tests
        test_class_instance = None
        if isinstance(test_item, tuple):
            class_name, class_obj, method = test_item

            # Check if method has description
            if hasattr(method, "_test_description") and method._test_description:
                test_description = method._test_description
            else:
                # Use the method name
                test_description = method.__name__

            # Create an instance of the test class
            test_class_instance = class_obj()

        # Handle standalone test functions
        else:
            test_func = test_item

            # Get the test description - either from the decorated function or use the function name
            if hasattr(test_func, "_test_description") and test_func._test_description:
                test_description = test_func._test_description
            else:
                # Use the base name without the module part
                test_description = test_name.split(".")[-1]

        # Display a clear message showing which test is running with visual enhancements
        print("\n")  # Add space before test for separation
        self.test_context.print(f"\033[1m\033[4mRunning test: {test_description}\033[0m")
        print("")  # Add space after header

        # Automatically start the test - don't rely on test function to do this
        self.test_context.start_test(test_description)

        result = None
        try:
            # If this is a class method test, call setUp if it exists
            if test_class_instance:
                class_name, class_obj, method = test_item

                # Call setUp if it exists
                if hasattr(test_class_instance, "setUp") and callable(test_class_instance.setUp):
                    if asyncio.iscoroutinefunction(test_class_instance.setUp):
                        logger.debug(f"Calling async setUp for {class_name}")
                        await test_class_instance.setUp(self.ble_manager, self.test_context)
                    else:
                        logger.debug(f"Calling sync setUp for {class_name}")
                        test_class_instance.setUp(self.ble_manager, self.test_context)

                # Run the test method
                logger.debug(f"Executing class test method: {test_name}")
                await method(test_class_instance, self.ble_manager, self.test_context)
            else:
                # Run standalone test function
                logger.debug(f"Executing standalone test: {test_name}")
                await test_func(self.ble_manager, self.test_context)

            # Test completed without exceptions - mark as pass
            result = self.test_context.end_test(TestStatus.PASS)

        except TestFailure as e:
            logger.error(f"Test {test_name} failed: {str(e)}")
            result = self.test_context.end_test(TestStatus.FAIL, str(e))

        except TestSkip as e:
            logger.info(f"Test {test_name} skipped: {str(e)}")
            result = self.test_context.end_test(TestStatus.SKIP, str(e))

        except TestException as e:
            logger.error(f"Test {test_name} error: {str(e)}")
            result = self.test_context.end_test(e.status, str(e))

        except AssertionError as e:
            logger.error(f"Test {test_name} failed: {str(e)}")
            result = self.test_context.end_test(TestStatus.FAIL, str(e))

        except TimeoutError as e:
            # Handle timeout errors gracefully without showing traceback
            logger.error(f"Test {test_name} error: {str(e)}")
            result = self.test_context.end_test(TestStatus.ERROR, str(e))

        except Exception as e:
            logger.error(f"Error running test {test_name}: {str(e)}")
            traceback.print_exc()
            result = self.test_context.end_test(TestStatus.ERROR, str(e))

        finally:
            # If this is a class method test, call tearDown if it exists
            if test_class_instance:
                try:
                    if hasattr(test_class_instance, "tearDown") and callable(test_class_instance.tearDown):
                        if asyncio.iscoroutinefunction(test_class_instance.tearDown):
                            logger.debug(f"Calling async tearDown for {class_name}")
                            await test_class_instance.tearDown(self.ble_manager, self.test_context)
                        else:
                            logger.debug(f"Calling sync tearDown for {class_name}")
                            test_class_instance.tearDown(self.ble_manager, self.test_context)
                except Exception as e:
                    logger.error(f"Error in tearDown for {test_name}: {str(e)}")
                    # Don't override test result if tearDown fails

            # Clean up subscriptions after test is complete
            await self.test_context.unsubscribe_all()

        return result

    async def run_tests(self, tests: List[TestNameItem]) -> Dict[str, Any]:
        """
        Run multiple tests in the order they were defined in the source code.

        Args:
            tests: List of tests to run

        Returns:
            Summary of test results
        """
        try:
            # Run each test in the order they were defined
            for test_name, test_item in tests:
                await self.run_test(test_name, test_item)

            # Return summary
            return self.test_context.get_test_summary()
        finally:
            # Ensure all tasks are cleaned up
            await self.test_context.cleanup_tasks()
