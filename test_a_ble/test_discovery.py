"""Test Discovery.

Functions for discovering and importing test files.
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
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

from .ble_manager import BLEManager
from .test_context import TestContext

logger = logging.getLogger(__name__)

# Type for test function
TestFunction = Callable[[BLEManager, TestContext], Coroutine[Any, Any, None]]

# Type for test item: a test function or (class_name, class_obj, method) tuple
TestItem = Callable | tuple[str, Any, Callable]
# Type for test: (test_name, test_item)
TestNameItem = tuple[str, TestItem]

MAX_IMPORT_PARENT_DIRECTORIES = 2


class NoTestFilesFoundError(ValueError):
    """Exception raised when no test files are found in a directory."""

    pass


def _is_package(path: Path) -> bool:
    """Check if a directory is a Python package (has __init__.py file).

    Args:
        path: Path to check

    Returns:
        True if the path is a Python package, False otherwise
    """
    return path.is_dir() and (path / "__init__.py").exists()


def _import_package(package_path: Path, base_package: str = "") -> str:
    """Import a Python package and all its parent packages.

    Args:
        package_path: Path to the package
        base_package: Base package name

    Returns:
        The imported package name
    """
    logger.debug(f"Importing package: {package_path}")

    # Get the package name from the path
    package_name = package_path.name

    # Construct the full package name
    full_package_name = f"{base_package}.{package_name}" if base_package else package_name

    # Check if package is already imported
    if full_package_name in sys.modules:
        logger.debug(f"Package {full_package_name} already imported")
        return full_package_name

    # Find the __init__.py file
    init_path = Path(package_path) / "__init__.py"

    if not init_path.exists():
        raise ImportError(f"No __init__.py found in {package_path}")

    try:
        # Import the package
        spec = importlib.util.spec_from_file_location(full_package_name, init_path)
        if not spec or not spec.loader:
            # Use a function to abstract the raise
            _raise_import_error(f"Failed to load module spec for {init_path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[full_package_name] = module

        # Execute the module
        spec.loader.exec_module(module)
        logger.debug(f"Successfully imported package: {full_package_name}")
    except Exception as e:
        raise ImportError(f"Error importing package {full_package_name}") from e
    else:
        return full_package_name


def _raise_import_error(message: str) -> None:
    """Raise an ImportError with the given message.

    Args:
        message: Error message

    Raises:
        ImportError: Always raised with the provided message
    """
    raise ImportError(message)


def find_and_import_nearest_package(path: Path) -> tuple[str, Path] | None:
    """Find the nearest package in the given path and import it.

    Args:
        path: Path to search for a package

    Returns:
        Tuple of (package_name, package_dir) if a package is found, None otherwise
    """
    current_dir = path
    parent_count = 0

    # Check up to 2 parent directories for __init__.py
    while parent_count < MAX_IMPORT_PARENT_DIRECTORIES:
        if _is_package(current_dir):
            # Found a module - use this as our base
            package_dir = current_dir
            package_name = current_dir.name
            logger.debug(f"Found package: {package_name} at {package_dir}")

            try:
                _import_package(current_dir)
            except ImportError:
                logger.exception(f"Error importing package {current_dir}")
                raise
            else:
                return package_name, package_dir

        # Move up to the parent directory
        parent_dir = current_dir.parent
        if parent_dir == current_dir:  # We've reached the root
            return None

        current_dir = parent_dir
        parent_count += 1

    return None


def _check_if_file_exists(test_dir: Path, test_file: str) -> tuple[Path, str] | None:
    """Check if a file exists in the given directory.

    Returns:
        Tuple of (test_dir, test_file) if the file exists, None otherwise
    """
    print(f"Test dir: {test_dir}, test file: {test_file}")
    if test_file is None:
        return None
    if not test_dir.is_dir():
        return None
    if not test_file.endswith(".py"):
        test_file = test_file + ".py"
    if (test_dir / test_file).exists():
        return (test_dir, test_file)
    if (test_dir / "tests" / test_file).exists():
        return (test_dir / "tests", test_file)
    return None


def _check_wildcard_match(test_wildcard: str | None, test_string: str) -> bool:
    """Check if the test string matches the test wildcard.

    Args:
        test_wildcard: Wildcard to match against
        test_string: String to match

    Returns:
        True if the test string matches the test wildcard, False otherwise
    """
    return test_wildcard is None or fnmatch.fnmatch(test_string, test_wildcard)


def _find_files_matching_wildcard(test_dir: Path, test_file_wildcard: str | None = None) -> list[str]:
    """Find files matching the wildcard (or any file if test_file_wildcard is None) in the given directory.

    Args:
        test_dir: Directory to search in
        test_file_wildcard: Wildcard to match against, or None to match any file

    Returns:
        List of files matching the wildcard
    """
    if not test_dir.is_dir():
        return []

    # list files in test_dir that match the wildcard
    files = []
    for file_path in test_dir.iterdir():
        if (
            file_path.is_file()
            and file_path.name.endswith(".py")
            and _check_wildcard_match(test_file_wildcard, file_path.name)
        ):
            files.append(file_path.name)
    return files


def _import_module_from_file(import_name: str, file_path: Path) -> Any:
    """Import a module from a file path.

    Args:
        import_name: Name to use for the imported module
        file_path: Path to the file to import

    Returns:
        The imported module

    Raises:
        ImportError: If the module cannot be imported
    """
    spec = importlib.util.spec_from_file_location(import_name, file_path)

    if not spec or not spec.loader:
        raise ImportError(f"Failed to load module spec for {file_path}")

    module = importlib.util.module_from_spec(spec)
    # Add the module to sys.modules to allow relative imports
    sys.modules[import_name] = module

    # Execute the module
    spec.loader.exec_module(module)
    logger.debug(f"Imported {import_name} using spec_from_file_location")

    return module


def _find_tests_in_module(
    package_dir: Path | None,
    import_name: str,
    test_dir: Path,
    test_file: str,
    method_or_wildcard: str | None = None,
) -> list[TestNameItem]:
    """Find tests in the given module.

    Args:
        package_dir: Directory of the package
        import_name: Import name of the module
        test_dir: Directory of the test
        test_file: File to find tests in
        method_or_wildcard: Method name or wildcard of the tests to find

    Returns:
        List of tuples (test_name, test_item) where test_item is a test function or (class, method) tuple
    """
    file_path = test_dir / test_file

    # Import the module
    try:
        if package_dir is not None:
            # Standard package import
            try:
                module = importlib.import_module(import_name)
                logger.debug(f"Imported {import_name} using import_module")
            except ImportError:
                # Fall back to file-based import
                module = _import_module_from_file(import_name, file_path)
        else:
            # Direct file import (no package)
            module = _import_module_from_file(import_name, file_path)
    except ImportError:
        logger.exception(f"Import error loading module {import_name}")
        logger.info(f"File path: {file_path}")
        logger.info(f"Current sys.path: {sys.path}")
        raise
    except Exception:
        logger.exception(f"Error loading module {import_name}")
        logger.debug(f"Exception details: {traceback.format_exc()}")
        raise

    # Use the relative path from test_dir as the module prefix for test names
    rel_path = file_path.relative_to(test_dir)
    rel_module = rel_path.with_suffix("").as_posix().replace(os.path.sep, ".")

    # First, discover test classes
    class_tests = []
    for class_name, class_obj in module.__dict__.items():
        # Check if it's a class and follows naming convention
        if inspect.isclass(class_obj) and (
            class_name.startswith("Test") or (hasattr(class_obj, "_is_test_class") and class_obj._is_test_class)
        ):
            # Store class for later use
            class_full_name = f"{rel_module}.{class_name}"
            logger.debug(f"Discovered test class: {class_full_name}")

            # Discover test methods in the class and collect with source line numbers
            class_method_tests = []
            for method_name, method_obj in inspect.getmembers(class_obj, predicate=inspect.isfunction):
                if not _check_wildcard_match(method_or_wildcard, method_name):
                    continue

                # Check if the method is a test method
                is_test = (hasattr(method_obj, "_is_ble_test") and method_obj._is_ble_test) or method_name.startswith(
                    "test_",
                )

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
                            ),
                        )
                        logger.debug(f"Discovered class test method: {test_name} at line {line_number}")
                    else:
                        logger.warning(
                            f"Method {method_name} in class {class_full_name} is not a coroutine function, skipping",
                        )

            # Sort class methods by line number to preserve definition order
            class_method_tests.sort(key=lambda x: x[4])

            # Add sorted methods to class_tests
            class_tests.extend(class_method_tests)

    # Then, discover standalone test functions
    function_tests = []
    for name, obj in module.__dict__.items():
        if not _check_wildcard_match(method_or_wildcard, name):
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

    tests: list[tuple[str, TestItem]] = []
    # Add class tests to the order list first
    for test_name, class_name, class_obj, method_obj, _ in class_tests:
        tests.append((test_name, (class_name, class_obj, method_obj)))

    # Then add standalone function tests to maintain file definition order
    for test_name, obj, _ in function_tests:
        tests.append((test_name, obj))

    return tests


def _find_tests_in_file(
    package_dir: Path | None,
    test_dir: Path,
    test_file: str,
    method_or_wildcard: str | None = None,
) -> list[TestNameItem]:
    """Find tests in the given file.

    Args:
        package_dir: Directory of the package
        test_dir: Directory of the test
        test_file: File to find tests in
        method_or_wildcard: Method name or wildcard of the tests to find

    Returns:
        List of tuples (test_name, test_item) where test_item is a test function or (class, method) tuple
    """
    # first we need to import the test file. If we are in a package, we need to import the file from the
    # package, otherwise we need to import the file from the test directory
    if package_dir is not None:
        # find additional path beyond package_dir to the file
        rel_path = test_dir.relative_to(package_dir)
        package_name = package_dir.name
        if rel_path == ".":
            # File is directly in the module directory
            package_path = None
            import_name = f"{package_name}.{test_file}"
        else:
            # File is in a subdirectory
            package_path = rel_path.as_posix().replace(os.path.sep, ".")
            import_name = f"{package_name}.{package_path}.{test_file}"

    else:
        # No module structure, just import the file directly
        package_path = None
        import_name = Path(test_file).stem
        # Add the test directory to sys.path to allow importing modules from it
        if test_dir not in sys.path:
            sys.path.insert(0, str(test_dir))
            logger.debug(f"Added {test_dir} to sys.path")

    return _find_tests_in_module(
        package_dir,
        import_name,
        test_dir,
        test_file,
        method_or_wildcard,
    )


def discover_tests_from_specifier(test_specifier: str) -> list[tuple[str, list[TestNameItem]]]:
    """Parse a test specifier.

    Args:
        test_specifier: Test specifier

    Returns:
        List of tuples (module_name, test_items) where test_items is a list of tuples (test_name, test_item) where
        test_item is a test function or (class, method) tuple
    """
    tests: list[tuple[str, list[TestNameItem]]] = []
    # Split the specifier by both '.' and '/' or '\' to handle different path formats
    path_parts = re.split(r"[./\\]", test_specifier)
    starts_with_slash = test_specifier[0] if test_specifier.startswith("/") or test_specifier.startswith("\\") else ""

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
        possible_path = Path(*path_parts[:-i]) if i > 0 else Path(*path_parts)
        logger.debug(f"possible_path {i}: {possible_path}")
        if starts_with_slash:
            possible_path = Path(starts_with_slash + str(possible_path))
        if possible_path.is_dir():
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
        tmp_dir = possible_path.parent
        tmp_file = possible_path.name
        if result := _check_if_file_exists(tmp_dir, tmp_file):
            test_dir, test_file = result
            logger.debug(f"Found test_dir: {test_dir}, test_file: {test_file}")
            test_method = path_parts[-i] if i > 0 else None
            break
    if test_dir is None:
        # Not found a dir yet, so specifier is not dir or file in current directory
        test_dir = Path.cwd()
        test_file = None
        if test_specifier == "all":
            logger.debug(f"Finding all tests in {test_dir}")
        elif len(path_parts) > 0 and (result := _check_if_file_exists(test_dir, path_parts[-1])):
            test_dir, test_file = result
            logger.debug(f"Found test_dir: {test_dir}, test_file: {test_file}")

    logger.debug(f"test_dir: {test_dir}, test_file: {test_file}, test_method: {test_method}")

    if test_file is None:  # find all files in test_dir
        test_file_wildcard = wildcard if test_method is None else None
        test_files = _find_files_matching_wildcard(test_dir, test_file_wildcard or "test_*")
        if not test_files:
            if (test_dir / "tests").is_dir():
                test_dir = test_dir / "tests"
                test_files = _find_files_matching_wildcard(test_dir, test_file_wildcard or "test_*")
            if not test_files:
                test_files = _find_files_matching_wildcard(test_dir, "test_*")
                if not test_files:
                    raise NoTestFilesFoundError()
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
    if pkg_result := find_and_import_nearest_package(test_dir):
        package_name, package_dir = pkg_result
    else:
        package_dir = None

    for test_file in test_files:
        module_name = Path(test_file).stem
        module_tests = _find_tests_in_file(package_dir, test_dir, test_file, test_method)
        tests.append((module_name, module_tests))

    tests.sort(key=lambda x: x[0])

    return tests
