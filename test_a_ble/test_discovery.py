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


def _import_test_module(package_dir: Path | None, import_name: str, file_path: Path) -> Any:
    """Import a test module.

    Args:
        package_dir: Directory of the package
        import_name: Import name of the module
        file_path: Path to the module file

    Returns:
        The imported module

    Raises:
        ImportError: If the module cannot be imported
    """
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

    return module


def _find_test_classes(module: Any, rel_module: str, method_or_wildcard: str | None) -> list[tuple]:
    """Find test classes in a module.

    Args:
        module: The module to search
        rel_module: The relative module path
        method_or_wildcard: Method name pattern to match

    Returns:
        List of test class details (sorted by line number)
    """
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
            class_method_tests = _find_test_methods_in_class(class_obj, class_full_name, method_or_wildcard)

            # Add sorted methods to class_tests
            class_tests.extend(class_method_tests)

    return class_tests


def _find_test_methods_in_class(class_obj: Any, class_full_name: str, method_or_wildcard: str | None) -> list[tuple]:
    """Find test methods in a class.

    Args:
        class_obj: The class to search
        class_full_name: Full name of the class
        method_or_wildcard: Method name pattern to match

    Returns:
        List of test method details (sorted by line number)
    """
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
    return class_method_tests


def _find_standalone_test_functions(
    module: Any, rel_module: str, method_or_wildcard: str | None, class_tests: list[tuple]
) -> list[tuple]:
    """Find standalone test functions in a module.

    Args:
        module: The module to search
        rel_module: The relative module path
        method_or_wildcard: Method name pattern to match
        class_tests: Already discovered class tests to avoid duplicates

    Returns:
        List of test function details (sorted by line number)
    """
    function_tests = []
    for name, obj in module.__dict__.items():
        if not _check_wildcard_match(method_or_wildcard, name):
            continue

        # Check if the function is decorated with @ble_test or starts with test_
        is_test = (hasattr(obj, "_is_ble_test") and obj._is_ble_test) or name.startswith("test_")

        if is_test and callable(obj) and not inspect.isclass(obj):
            # Don't process methods that belong to test classes (already handled)
            if any(t[3] == obj for t in class_tests):
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
                logger.warning(f"Function {name} in {rel_module} is not a coroutine function, skipping")

    # Sort standalone functions by line number
    function_tests.sort(key=lambda x: x[2])
    return function_tests


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
    module = _import_test_module(package_dir, import_name, file_path)

    # Use the relative path from test_dir as the module prefix for test names
    rel_path = file_path.relative_to(test_dir)
    rel_module = rel_path.with_suffix("").as_posix().replace(os.path.sep, ".")

    # First, discover test classes
    class_tests = _find_test_classes(module, rel_module, method_or_wildcard)

    # Then, discover standalone test functions
    function_tests = _find_standalone_test_functions(module, rel_module, method_or_wildcard, class_tests)

    # Combine class tests and function tests in correct order
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


def _split_components(path_component: str) -> tuple[str | None, str | None]:
    """Split a path component into file and method components.

    Args:
        path_component: Path component to split

    Returns:
        Tuple of (file, method)
    """
    # If it contains a dot, it could be file.method
    if "." in path_component:
        parts = path_component.split(".")
        # File name and method name
        if len(parts) == 2:  # noqa: PLR2004
            return parts[0], parts[1]
        # Multiple dots - treat as file with extension
        return path_component, None
    # No dot: a file without extension
    return path_component, None


def _parse_test_specifier(specifier: str) -> tuple[str | None, str | None, str | None]:
    """Parse a test specifier into directory, file, and method components.

    Args:
        specifier: The test specifier string

    Returns:
        A tuple of (directory, file, method) components
    """
    # Start with empty components
    directory = file = method = None

    # Split the specifier by path separators
    path_components = specifier.split("/")
    component_count = len(path_components)

    # Single component: method, file, or directory
    if component_count == 1:
        if "." in path_components[0]:
            file, method = _split_components(path_components[0])
        else:
            directory = path_components[0]

    # Two components: directory/file or directory/file.method
    elif component_count == 2:  # noqa: PLR2004
        directory = path_components[0]
        file, method = _split_components(path_components[1])

    # Three or more components: directory/[subdirs]/file or directory/[subdirs]/file.method
    else:
        # Convert to Path and join all components except the last one
        directory = str(Path(*path_components[:-1]))
        file, method = _split_components(path_components[-1])

    # Handle wildcards
    if file and "*" in file:
        # If a wildcard is in the filename, set directory to include the file part
        directory = str(Path(directory) / file) if directory else file
        file = None

    return directory, file, method


def _find_test_dir(test_dir: str | None, cwd: Path) -> Path:
    """Find the test directory.

    Args:
        test_dir: Optional test directory specified
        cwd: Current working directory

    Returns:
        Path to the test directory
    """
    if test_dir:
        return Path(test_dir)
    # Default to current directory if not specified
    return cwd


def _add_test_directory(
    directory_path: Path, package_dirs: list[Path], test_dirs: list[Path], search_dirs: list[Path]
) -> None:
    """Add a directory to the search directories if it exists.

    Args:
        directory_path: Path to the directory
        package_dirs: List of package directories to update
        test_dirs: List of test directories to update
        search_dirs: List of search directories to update
    """
    if directory_path.exists() and directory_path.is_dir():
        if (directory_path / "__init__.py").exists():
            package_dirs.append(directory_path)
        test_dirs.append(directory_path)
        search_dirs.append(directory_path)


def _find_matching_directories(
    base_dir: Path, pattern: str, package_dirs: list[Path], test_dirs: list[Path], search_dirs: list[Path]
) -> None:
    """Find directories matching a pattern and add them to the search directories.

    Args:
        base_dir: Base directory to search from
        pattern: Pattern to match
        package_dirs: List of package directories to update
        test_dirs: List of test directories to update
        search_dirs: List of search directories to update
    """
    if "*" in pattern:
        for found_dir in base_dir.glob(pattern):
            if found_dir.is_dir():
                _add_test_directory(found_dir, package_dirs, test_dirs, search_dirs)


def _handle_package_directory(
    test_dir: Path, directory: str | None, package_dirs: list[Path], test_dirs: list[Path], search_dirs: list[Path]
) -> None:
    """Handle directory search in a package.

    Args:
        test_dir: Base test directory
        directory: Directory to search in (or None for root)
        package_dirs: List of package directories to update
        test_dirs: List of test directories to update
        search_dirs: List of search directories to update
    """
    # We are in a package, add it as a package directory
    package_dirs.append(test_dir)

    # If a directory is specified, use it as a subdirectory within the package
    if directory:
        subdir = test_dir / directory
        _add_test_directory(subdir, package_dirs, test_dirs, search_dirs)

        # If not found, try using glob to match directories
        if not (subdir.exists() and subdir.is_dir()):
            _find_matching_directories(test_dir, directory, package_dirs, test_dirs, search_dirs)
            logger.debug(f"Directory {directory} not found or not a directory")
    else:
        # No directory specified, use the package root
        test_dirs.append(test_dir)
        search_dirs.append(test_dir)


def _handle_non_package_directory(
    test_dir: Path, directory: str | None, test_dirs: list[Path], search_dirs: list[Path]
) -> None:
    """Handle directory search in a non-package.

    Args:
        test_dir: Base test directory
        directory: Directory to search in (or None for root)
        test_dirs: List of test directories to update
        search_dirs: List of search directories to update
    """
    if directory:
        subdir = test_dir / directory
        if subdir.exists() and subdir.is_dir():
            test_dirs.append(subdir)
            search_dirs.append(subdir)
        else:
            # If not found, try using glob to match directories
            if "*" in directory:
                for found_dir in test_dir.glob(directory):
                    if found_dir.is_dir():
                        test_dirs.append(found_dir)
                        search_dirs.append(found_dir)
            logger.debug(f"Directory {directory} not found or not a directory")
    else:
        # No directory specified, use test_dir
        test_dirs.append(test_dir)
        search_dirs.append(test_dir)


def _find_test_packages(directory: str | None, test_dir: Path) -> tuple[list[Path], list[Path], list[Path]]:
    """Find test packages in the specified directory.

    Args:
        directory: Directory to search in (or None for root)
        test_dir: Base test directory

    Returns:
        Tuple of (package_dirs, test_dirs, search_dirs)
    """
    # Find all directories containing __init__.py files (packages)
    package_dirs = []
    test_dirs = []
    search_dirs = []

    # Check if we're in a Python package (has __init__.py)
    if (test_dir / "__init__.py").exists():
        _handle_package_directory(test_dir, directory, package_dirs, test_dirs, search_dirs)
    else:
        # Not in a package, treat as a regular directory
        _handle_non_package_directory(test_dir, directory, test_dirs, search_dirs)

    return package_dirs, test_dirs, search_dirs


def _find_test_files(file: str | None, search_dirs: list[Path]) -> list[tuple[Path, str]]:
    """Find test files in the search directories.

    Args:
        file: File pattern to search for (or None for all)
        search_dirs: Directories to search in

    Returns:
        List of tuples (test_dir, test_file)
    """
    test_file_paths = []

    # For each test directory, find matching test files
    for test_dir in search_dirs:
        if file:
            # A file pattern was specified
            if "*" in file:
                # Handle wildcards in the file pattern
                for matched_file in test_dir.glob(file):
                    if matched_file.is_file() and matched_file.suffix == ".py":
                        rel_path = matched_file.relative_to(test_dir)
                        test_file_paths.append((test_dir, str(rel_path)))
            else:
                # Specific file (with or without .py extension)
                file_with_ext = file if file.endswith(".py") else f"{file}.py"
                file_path = test_dir / file_with_ext
                if file_path.exists() and file_path.is_file():
                    test_file_paths.append((test_dir, file_with_ext))
                else:
                    logger.debug(f"File {file_path} not found")
        else:
            # No file specified, find all Python files that match naming patterns
            for py_file in test_dir.glob("*.py"):
                if py_file.name.startswith("test_") or py_file.name.endswith("_test.py"):
                    rel_path = py_file.relative_to(test_dir)
                    test_file_paths.append((test_dir, str(rel_path)))

    if not test_file_paths:
        # No test files found
        file_desc = f" matching '{file}'" if file else ""
        logger.info(f"No test files{file_desc} found in {[str(d) for d in search_dirs]}")

    return test_file_paths


def _find_closest_package_dir(test_dir: Path, package_dirs: list[Path]) -> Path | None:
    """Find the closest package directory that contains the test directory.

    Args:
        test_dir: The test directory
        package_dirs: List of package directories

    Returns:
        The closest package directory or None
    """
    closest_package = None
    for pkg_dir in package_dirs:
        # Find the package directory that is a parent of this test file
        if test_dir.is_relative_to(pkg_dir) and (
            closest_package is None
            or len(test_dir.relative_to(pkg_dir).parts) < len(test_dir.relative_to(closest_package).parts)
        ):
            closest_package = pkg_dir
    return closest_package


def _create_import_name(test_dir: Path, rel_path: Path, closest_package: Path | None) -> tuple[str, Path | None]:
    """Create an import name for a test file.

    Args:
        test_dir: The test directory
        rel_path: Relative path of the test file
        closest_package: The closest package directory

    Returns:
        Tuple of (import_name, package_dir)
    """
    if closest_package:
        # Create the import path based on the package structure
        rel_to_pkg = test_dir.relative_to(closest_package)
        pkg_parts = []

        # Add the package name (directory containing closest __init__.py)
        if closest_package.name:
            pkg_parts.append(closest_package.name)

        # Add subdirectory components
        if rel_to_pkg.parts:
            pkg_parts.extend(rel_to_pkg.parts)

        # Add the module name (file without .py)
        module_name = rel_path.with_suffix("").as_posix()
        pkg_parts.append(module_name)

        import_name = ".".join(pkg_parts)
        logger.debug(f"Using package import: {import_name}")
        return import_name, closest_package

    # Not in a package, use direct file import
    import_name = rel_path.with_suffix("").as_posix().replace(os.path.sep, ".")
    logger.debug(f"Using file import (no package): {import_name}")
    return import_name, None


def _process_test_files(
    test_file_paths: list[tuple[Path, str]], package_dirs: list[Path], method: str | None
) -> list[tuple[str, TestItem]]:
    """Process test files to find tests.

    Args:
        test_file_paths: List of (test_dir, test_file) tuples
        package_dirs: List of package directories
        method: Method name or wildcard

    Returns:
        List of discovered tests
    """
    discovered_tests = []

    for test_dir, test_file in test_file_paths:
        rel_path = Path(test_file)

        # Determine import name
        if package_dirs:
            # Find the closest package directory
            closest_package = _find_closest_package_dir(test_dir, package_dirs)
            import_name, package_dir = _create_import_name(test_dir, rel_path, closest_package)
        else:
            # Not in a package, use direct file import
            import_name = rel_path.with_suffix("").as_posix().replace(os.path.sep, ".")
            logger.debug(f"Using file import (no package): {import_name}")
            package_dir = None

        # Find tests in this module
        try:
            tests = _find_tests_in_module(package_dir, import_name, test_dir, test_file, method)
            discovered_tests.extend(tests)
        except Exception:
            logger.exception(f"Error discovering tests in {test_file}")

    return discovered_tests


def discover_tests_from_specifier(specifier: str | None, test_dir: str | None = None) -> list[tuple[str, TestItem]]:
    """Discover tests from a test specifier.

    Args:
        specifier: Test specifier string in the format [path/]file[.method]
        test_dir: Base directory for tests

    Returns:
        List of (test_name, test_item) tuples
    """
    cwd = Path.cwd()

    # Parse the specifier to determine directory, file, and method components
    directory = file = method = None

    if specifier:
        directory, file, method = _parse_test_specifier(specifier)

    # Find the test directory
    test_dir_path = _find_test_dir(test_dir, cwd)
    logger.debug(f"Test directory: {test_dir_path}")
    logger.debug(f"Looking for tests with: directory='{directory}', file='{file}', method='{method}'")

    # Find package directories and test directories
    package_dirs, test_dirs, search_dirs = _find_test_packages(directory, test_dir_path)

    if not search_dirs:
        logger.warning(f"No valid test directories found for '{directory or '.'}'")
        raise NoTestFilesFoundError(f"No valid test directories found for '{directory or '.'}'")

    # Find test files
    test_file_paths = _find_test_files(file, search_dirs)

    if not test_file_paths:
        raise NoTestFilesFoundError(f"No test files matching '{file or '*'}' found in {search_dirs}")

    # Process test files and discover tests
    discovered_tests = _process_test_files(test_file_paths, package_dirs, method)

    # Sort by module name for consistent order
    discovered_tests.sort(key=lambda x: x[0])
    return discovered_tests
