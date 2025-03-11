"""Test test discovery."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

from test_a_ble.ble_manager import BLEManager
from test_a_ble.test_runner import TestRunner

# Get the absolute path to the test_discovery_test_package
TEST_PACKAGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_discovery_test_package")
TIMESTAMP_FILE = os.path.join(TEST_PACKAGE_DIR, "import_timestamp.txt")


@pytest.fixture
def mock_ble_manager():
    """Create a mock BLE manager."""
    return MagicMock(spec=BLEManager)


@pytest.fixture
def test_runner(mock_ble_manager):
    """Create a test runner with a mock BLE manager."""
    return TestRunner(mock_ble_manager)


def reset_now():
    """Reset the timestamp file and package import."""
    if os.path.exists(TIMESTAMP_FILE):
        os.remove(TIMESTAMP_FILE)

    if "test_discovery_test_package" in sys.modules:
        del sys.modules["test_discovery_test_package"]


@pytest.fixture(autouse=True)
def reset():
    """Reset the timestamp file and package import before and after each test."""
    reset_now()

    # Return the timestamp file path
    yield TIMESTAMP_FILE

    reset_now()


def was_package_imported():
    """Check if the package was imported by looking for the timestamp file."""
    return os.path.exists(TIMESTAMP_FILE)


def test_discover_specific_function(test_runner):
    """Test discovering a specific function."""
    # Change to the test package directory
    with patch("os.getcwd", return_value=TEST_PACKAGE_DIR):
        # Discover tests with the specifier "test_function"
        tests = test_runner.discover_tests(["test_function"])

    # Verify the discovered tests
    assert len(tests) == 1  # One module
    module_name, test_items = tests[0]
    assert module_name == "test_function"
    assert len(test_items) == 2  # Two test functions

    # Check test names - TestNameItem is a tuple of (name, test_item)
    test_names = [item[0] for item in test_items]
    assert "test_function.test_function_1" in test_names
    assert "test_function.test_function_2" in test_names

    # Check that the package was imported
    assert was_package_imported(), "Package was not imported during test discovery"


def test_discover_specific_class(test_runner):
    """Test discovering a specific class."""
    # Change to the test package directory
    with patch("os.getcwd", return_value=TEST_PACKAGE_DIR):
        # Discover tests with the specifier "test_class"
        tests = test_runner.discover_tests(["test_class"])

    # Verify the discovered tests
    assert len(tests) == 1  # One module
    module_name, test_items = tests[0]
    assert module_name == "test_class"
    assert len(test_items) == 2  # Two test methods

    # Check test names - TestNameItem is a tuple of (name, test_item)
    test_names = [item[0] for item in test_items]
    assert "test_class.TestClass.test_method_1" in test_names
    assert "test_class.TestClass.test_method_2" in test_names

    # Check that the package was imported
    assert was_package_imported(), "Package was not imported during test discovery"


def test_discover_all_tests_from_cwd(test_runner):
    """Test discovering all tests from the current working directory."""
    # Change to the test package directory
    with patch("os.getcwd", return_value=TEST_PACKAGE_DIR):
        # Discover tests with no specifier
        tests = test_runner.discover_tests(["all"])

    # Verify the discovered tests
    assert len(tests) == 2  # Two modules

    # Sort the tests by module name for consistent checking
    tests.sort(key=lambda x: x[0])

    # Check first module (test_class)
    module_name, test_items = tests[0]
    assert module_name == "test_class"
    assert len(test_items) == 2  # Two test methods

    # Check test names for test_class - TestNameItem is a tuple of (name, test_item)
    test_names = [item[0] for item in test_items]
    assert "test_class.TestClass.test_method_1" in test_names
    assert "test_class.TestClass.test_method_2" in test_names

    # Check second module (test_function)
    module_name, test_items = tests[1]
    assert module_name == "test_function"
    assert len(test_items) == 2  # Two test functions

    # Check test names for test_function - TestNameItem is a tuple of (name, test_item)
    test_names = [item[0] for item in test_items]
    assert "test_function.test_function_1" in test_names
    assert "test_function.test_function_2" in test_names

    # Check that the package was imported
    assert was_package_imported(), "Package was not imported during test discovery"


def test_discover_with_relative_path(test_runner):
    """Test discovering tests with a relative path."""
    # Get the relative path from the current directory to the test package
    current_dir = os.getcwd()
    relative_path = os.path.relpath(TEST_PACKAGE_DIR, current_dir)

    # Discover tests with the relative path
    tests = test_runner.discover_tests([relative_path])

    # Verify the discovered tests
    assert len(tests) == 2  # Two modules

    # Sort the tests by module name for consistent checking
    tests.sort(key=lambda x: x[0])

    # Check first module (test_class)
    module_name, test_items = tests[0]
    assert module_name == "test_class"
    assert len(test_items) == 2  # Two test methods

    # Check second module (test_function)
    module_name, test_items = tests[1]
    assert module_name == "test_function"
    assert len(test_items) == 2  # Two test functions

    # Check that the package was imported
    assert was_package_imported(), "Package was not imported during test discovery"


def test_discover_with_absolute_path(test_runner):
    """Test discovering tests with an absolute path."""
    # Discover tests with the absolute path
    tests = test_runner.discover_tests([TEST_PACKAGE_DIR])

    # Verify the discovered tests
    assert len(tests) == 2  # Two modules

    # Sort the tests by module name for consistent checking
    tests.sort(key=lambda x: x[0])

    # Check first module (test_class)
    module_name, test_items = tests[0]
    assert module_name == "test_class"
    assert len(test_items) == 2  # Two test methods

    # Check second module (test_function)
    module_name, test_items = tests[1]
    assert module_name == "test_function"
    assert len(test_items) == 2  # Two test functions

    # Check that the package was imported
    assert was_package_imported(), "Package was not imported during test discovery"


def test_discover_with_file_wildcard(test_runner):
    """Test discovering tests with a wildcard for test files."""
    # Change to the test package directory
    with patch("os.getcwd", return_value=TEST_PACKAGE_DIR):
        # Discover tests with the wildcard specifier "test_c*"
        tests = test_runner.discover_tests(["test_c*"])

    # Verify the discovered tests
    assert len(tests) == 1  # One module
    module_name, test_items = tests[0]
    assert module_name == "test_class"
    assert len(test_items) == 2  # Two test methods

    # Check test names - TestNameItem is a tuple of (name, test_item)
    test_names = [item[0] for item in test_items]
    assert "test_class.TestClass.test_method_1" in test_names
    assert "test_class.TestClass.test_method_2" in test_names

    # Check that the package was imported
    assert was_package_imported(), "Package was not imported during test discovery"


def test_discover_with_function_wildcard(test_runner):
    """Test discovering tests with a wildcard for test functions."""
    # Change to the test package directory
    with patch("os.getcwd", return_value=TEST_PACKAGE_DIR):
        # Discover tests with the wildcard specifier "*_1"
        tests = test_runner.discover_tests(["*_1"])

    # Verify the discovered tests
    assert len(tests) == 2  # Two modules

    # Sort the tests by module name for consistent checking
    tests.sort(key=lambda x: x[0])

    # Check the test items - TestNameItem is a tuple of (name, test_item)
    all_test_names = []
    for module_name, test_items in tests:
        all_test_names.extend([item[0] for item in test_items])

    # We should have exactly 2 tests with names ending in _1
    assert len(all_test_names) == 2
    assert "test_function.test_function_1" in all_test_names
    assert "test_class.TestClass.test_method_1" in all_test_names

    # Check that the package was imported
    assert was_package_imported(), "Package was not imported during test discovery"
