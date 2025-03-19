"""Test test discovery."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest  # type: ignore

from test_a_ble.ble_manager import BLEManager
from test_a_ble.test_discovery import (
    NoTestFilesFoundError,
    _import_package,
    _is_package,
    discover_tests_from_specifier,
    find_and_import_nearest_package,
)
from test_a_ble.test_runner import TestRunner

# Get the absolute path to the test_discovery_test_package
TEST_PACKAGE_DIR = Path(__file__).parent / "test_discovery_test_package"
TIMESTAMP_FILE = TEST_PACKAGE_DIR / "import_timestamp.txt"


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
    if TIMESTAMP_FILE.exists():
        TIMESTAMP_FILE.unlink()

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
    return TIMESTAMP_FILE.exists()


def test_discover_specific_function(test_runner: TestRunner):
    """Test discovering a specific function."""
    # Change to the test package directory
    with patch("pathlib.Path.cwd", return_value=TEST_PACKAGE_DIR):
        # Discover tests with the specifier "test_function"
        tests = discover_tests_from_specifier("test_function")

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


def test_discover_specific_class(test_runner: TestRunner):
    """Test discovering a specific class."""
    # Change to the test package directory
    with patch("pathlib.Path.cwd", return_value=TEST_PACKAGE_DIR):
        # Discover tests with the specifier "test_class"
        tests = discover_tests_from_specifier("test_class")

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


def test_discover_all_tests_from_cwd(test_runner: TestRunner):
    """Test discovering all tests from the current working directory."""
    # Change to the test package directory
    with patch("pathlib.Path.cwd", return_value=TEST_PACKAGE_DIR):
        # Discover tests with no specifier
        tests = discover_tests_from_specifier("all")

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


def test_discover_with_relative_path(test_runner: TestRunner):
    """Test discovering tests with a relative path."""
    # Get the relative path from the current directory to the test package
    current_dir = Path.cwd()
    relative_path = TEST_PACKAGE_DIR.relative_to(current_dir)

    # Discover tests with the relative path
    tests = discover_tests_from_specifier(str(relative_path))

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


def test_discover_with_absolute_path(test_runner: TestRunner):
    """Test discovering tests with an absolute path."""
    # Discover tests with the absolute path
    tests = discover_tests_from_specifier(str(TEST_PACKAGE_DIR))

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


def test_discover_with_file_wildcard(test_runner: TestRunner):
    """Test discovering tests with a wildcard for test files."""
    # Change to the test package directory
    with patch("pathlib.Path.cwd", return_value=TEST_PACKAGE_DIR):
        # Discover tests with the wildcard specifier "test_c*"
        tests = discover_tests_from_specifier("test_c*")

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


def test_discover_with_function_wildcard(test_runner: TestRunner):
    """Test discovering tests with a wildcard for test functions."""
    # Change to the test package directory
    with patch("pathlib.Path.cwd", return_value=TEST_PACKAGE_DIR):
        # Discover tests with the wildcard specifier "*_1"
        tests = discover_tests_from_specifier("*_1")

    # Verify the discovered tests
    assert len(tests) == 2  # Two modules

    # Sort the tests by module name for consistent checking
    tests.sort(key=lambda x: x[0])

    # Check the test items - TestNameItem is a tuple of (name, test_item)
    all_test_names = []
    for _module_name, test_items in tests:
        all_test_names.extend([item[0] for item in test_items])

    # We should have exactly 2 tests with names ending in _1
    assert len(all_test_names) == 2
    assert "test_function.test_function_1" in all_test_names
    assert "test_class.TestClass.test_method_1" in all_test_names

    # Check that the package was imported
    assert was_package_imported(), "Package was not imported during test discovery"


def test_is_package(test_runner, tmp_path):
    """Test the _is_package method."""
    # Create a directory that is a package
    package_dir = tmp_path / "package"
    package_dir.mkdir()
    init_file = package_dir / "__init__.py"
    init_file.write_text("")

    # Create a directory that is not a package
    not_package_dir = tmp_path / "not_package"
    not_package_dir.mkdir()

    # Test
    assert _is_package(package_dir) is True
    assert _is_package(not_package_dir) is False


@patch("importlib.util.spec_from_file_location")
@patch("importlib.util.module_from_spec")
def test_import_package_with_base_package(
    mock_module_from_spec,
    mock_spec_from_file,
    test_runner,
    tmp_path,
):
    """Test the _import_package method with a base package."""
    # Setup

    # Create a mock spec and module
    mock_spec = MagicMock()
    mock_spec.loader = MagicMock()
    mock_spec_from_file.return_value = mock_spec

    mock_module = MagicMock()
    mock_module_from_spec.return_value = mock_module

    # Create a package directory structure
    package_dir = tmp_path / "base_package" / "my_test_package"
    package_dir.mkdir(parents=True)
    init_file = package_dir / "__init__.py"
    init_file.write_text("")

    # Pre-construct the expected path string
    expected_init_path = package_dir / "__init__.py"

    # Test with base package
    with patch.dict("sys.modules", {}, clear=True):
        result = _import_package(package_dir, "base.package")
        assert result == "base.package.my_test_package"
        mock_spec_from_file.assert_called_with("base.package.my_test_package", expected_init_path)


@patch("importlib.util.spec_from_file_location")
@patch("importlib.util.module_from_spec")
def test_import_package_without_base_package(
    mock_module_from_spec,
    mock_spec_from_file,
    test_runner,
    tmp_path,
):
    """Test the _import_package method without a base package."""
    # Setup

    # Create a mock spec and module
    mock_spec = MagicMock()
    mock_spec.loader = MagicMock()
    mock_spec_from_file.return_value = mock_spec

    mock_module = MagicMock()
    mock_module_from_spec.return_value = mock_module

    # Create a package directory structure
    package_dir = tmp_path / "base_package" / "my_test_package"
    package_dir.mkdir(parents=True)
    init_file = package_dir / "__init__.py"
    init_file.write_text("")

    # Pre-construct the expected path string
    expected_init_path = package_dir / "__init__.py"

    # Test without base package
    with patch.dict("sys.modules", {}, clear=True):
        result = _import_package(package_dir)
        assert result == "my_test_package"
        mock_spec_from_file.assert_called_with("my_test_package", expected_init_path)


@patch("pathlib.Path")
def test_find_and_import_nearest_package_when_package_found(mock_path, test_runner, tmp_path):
    """Test the _find_and_import_nearest_package method when a package is found."""
    # Setup
    mock_path_instance = MagicMock()
    mock_path.return_value = mock_path_instance
    mock_path_instance.is_dir.return_value = True
    mock_path_instance.name = "package"  # Set the name property
    mock_path_instance.parent = mock_path_instance  # Set parent to self to prevent infinite loop

    # Configure mock to indicate a package is found
    def exists_side_effect(path):
        return "__init__.py" in str(path)

    mock_path_instance.exists.side_effect = exists_side_effect

    # Test when a package is found
    with patch("test_a_ble.test_discovery._import_package") as mock_import:
        mock_import.return_value = "package"  # Just the package name, not the full import path
        result = find_and_import_nearest_package(mock_path_instance)
        assert result == ("package", mock_path_instance)


@patch("test_a_ble.test_discovery._is_package")
def test_find_and_import_nearest_package_when_no_package_found(mock_is_package, test_runner, tmp_path):
    """Test the _find_and_import_nearest_package method when no package is found."""
    # Configure mock to indicate no package is found
    mock_is_package.return_value = False

    # Create a path to test
    path = tmp_path / "path" / "to" / "nowhere"

    # Test when no package is found
    result = find_and_import_nearest_package(path)
    assert result is None


def test_import_package_no_init_file(test_runner, tmp_path):
    """Test that _import_package raises an ImportError when no __init__.py file exists."""
    # Create a directory without an __init__.py file
    package_dir = tmp_path / "fake_package"
    package_dir.mkdir()

    # Test that it raises an ImportError
    with pytest.raises(ImportError, match="No __init__.py found"):
        _import_package(package_dir)


def test_find_and_import_nearest_package_with_import_error(test_runner, tmp_path):
    """Test that find_and_import_nearest_package raises when _import_package fails."""
    # Create a package directory structure
    package_dir = tmp_path / "error_package"
    package_dir.mkdir()

    # Create an __init__.py file that will exist but will fail during import
    init_file = package_dir / "__init__.py"
    init_file.write_text("raise ImportError('Testing import error')")

    # Test that it raises the ImportError
    with pytest.raises(ImportError):
        find_and_import_nearest_package(package_dir)


def test_import_already_imported_package(test_runner, tmp_path):
    """Test that _import_package returns the package name if it's already imported."""
    # Create a package directory
    package_dir = tmp_path / "already_imported"
    package_dir.mkdir()
    init_file = package_dir / "__init__.py"
    init_file.write_text("")

    package_name = "already_imported"

    # Mock sys.modules to simulate the package being already imported
    with patch.dict(sys.modules, {package_name: MagicMock()}):
        result = _import_package(package_dir)
        assert result == package_name


def test_check_if_file_exists():
    """Test _check_if_file_exists function."""
    # Import the function since it's not exported
    from test_a_ble.test_discovery import _check_if_file_exists

    # Create a simple test with mock Path objects
    test_dir = MagicMock()
    test_dir.is_dir.return_value = True

    # For the first test, configure Path.__truediv__ to return a path that exists
    path_mock = MagicMock()
    path_mock.exists.return_value = True
    test_dir.__truediv__.return_value = path_mock

    # Test when file exists
    result = _check_if_file_exists(test_dir, "test_file.py")
    assert result == (test_dir, "test_file.py")

    # Create a new mock for the second test with a different configuration
    test_dir2 = MagicMock()
    test_dir2.is_dir.return_value = True

    path_mock2 = MagicMock()
    path_mock2.exists.return_value = False
    test_dir2.__truediv__.return_value = path_mock2

    # Mock for the "tests" subdirectory check that also doesn't exist
    tests_dir_mock = MagicMock()
    tests_dir_mock.exists.return_value = False
    test_dir2.__truediv__.return_value.__truediv__.return_value = tests_dir_mock

    # Test when file doesn't exist
    result = _check_if_file_exists(test_dir2, "nonexistent_file.py")
    assert result is None


def test_find_tests_with_max_parent_directories(test_runner, tmp_path):
    """Test that find_and_import_nearest_package stops after MAX_IMPORT_PARENT_DIRECTORIES."""
    # Create a deep directory structure without any packages
    deep_dir = tmp_path
    for i in range(5):  # More than MAX_IMPORT_PARENT_DIRECTORIES
        deep_dir = deep_dir / f"level_{i}"
        deep_dir.mkdir()

    # Test that it returns None after checking the max number of parent directories
    result = find_and_import_nearest_package(deep_dir)
    assert result is None


@patch("pathlib.Path.is_dir")
@patch("test_a_ble.test_discovery._find_files_matching_wildcard")
def test_discover_tests_from_specifier_with_nonexistent_file(mock_find_files, mock_is_dir):
    """Test discover_tests_from_specifier with a file that doesn't exist."""
    # Setup mocks
    mock_is_dir.return_value = False
    # Configure _find_files_matching_wildcard to return empty list (no files found)
    mock_find_files.return_value = []

    # Test with a specific file pattern that is unlikely to exist
    # It should raise a specialized NoTestFilesFoundError
    with pytest.raises(NoTestFilesFoundError):
        discover_tests_from_specifier("nonexistent_file_xyz123.py")


@patch("pathlib.Path.is_dir")
@patch("test_a_ble.test_discovery._find_files_matching_wildcard")
def test_discover_tests_from_specifier_with_nonexistent_directory(mock_find_files, mock_is_dir):
    """Test discover_tests_from_specifier with a directory that doesn't exist."""
    # Configure mocks
    mock_is_dir.return_value = False
    # Configure _find_files_matching_wildcard to return empty list (no files found)
    mock_find_files.return_value = []

    # Test with a specific directory pattern
    # It should raise a specialized NoTestFilesFoundError
    with pytest.raises(NoTestFilesFoundError):
        discover_tests_from_specifier("nonexistent_dir_xyz123/")


def test_discover_tests_with_empty_directory(tmp_path):
    """Test discover_tests_from_specifier with an empty directory."""
    # Create an empty directory
    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()

    # Test that it raises a specialized NoTestFilesFoundError
    with pytest.raises(NoTestFilesFoundError):
        discover_tests_from_specifier(str(empty_dir))


@patch("importlib.util.spec_from_file_location")
def test_import_package_spec_failure(mock_spec_from_file, test_runner, tmp_path):
    """Test that _import_package raises an ImportError when spec_from_file_location returns None."""
    # Setup
    mock_spec_from_file.return_value = None

    # Create a package directory structure
    package_dir = tmp_path / "spec_fail_package"
    package_dir.mkdir()
    init_file = package_dir / "__init__.py"
    init_file.write_text("")

    # Test that it raises an ImportError with any message
    with pytest.raises(ImportError):
        _import_package(package_dir)


@patch("test_a_ble.test_discovery._find_tests_in_file")
def test_find_tests_in_file_with_wildcard(mock_find_tests_in_file):
    """Test _find_tests_in_file with a wildcard."""
    # Import the function since it's not exported
    from test_a_ble.test_discovery import _find_tests_in_file

    # Setup mock to return test data
    mock_find_tests_in_file.return_value = [("test1", lambda: None), ("test2", lambda: None)]

    # Test with wildcard
    result = _find_tests_in_file(None, Path("/test/dir"), "test_file.py", "*test*")

    # Should filter results based on wildcard
    assert result == mock_find_tests_in_file.return_value

    # Check function was called with correct arguments
    mock_find_tests_in_file.assert_called_once()


@patch("test_a_ble.test_discovery._find_files_matching_wildcard")
def test_discover_tests_from_specifier_with_wildcard(mock_find_files):
    """Test discover_tests_from_specifier with a wildcard."""
    # Setup mock to return a list of files
    mock_find_files.return_value = ["test_file1.py", "test_file2.py"]

    # Test with wildcard
    with patch("test_a_ble.test_discovery._find_tests_in_file") as mock_find_tests:
        # Configure the inner mock to return some test data
        mock_find_tests.return_value = [("test1", lambda: None)]

        # Call function with wildcard
        result = discover_tests_from_specifier("test_*")

        # Should return results from all matched files
        assert len(result) == 2  # Two module entries from the two files
        assert result[0][0] == "test_file1"  # First module name
        assert result[1][0] == "test_file2"  # Second module name


@patch("test_a_ble.test_discovery._find_files_matching_wildcard")
def test_discover_tests_from_specifier_handles_error_paths(mock_find_files):
    """Test error handling in discover_tests_from_specifier function."""
    # Mock to return no test files found - should cause NoTestFilesFoundError
    mock_find_files.return_value = []

    # Should raise a specialized NoTestFilesFoundError
    with pytest.raises(NoTestFilesFoundError):
        discover_tests_from_specifier("nonexistent_pattern")
