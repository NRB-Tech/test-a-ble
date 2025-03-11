"""Tests for the TestRunner class."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from test_a_ble.ble_manager import BLEManager
from test_a_ble.test_context import TestContext, TestStatus
from test_a_ble.test_runner import TestRunner

TEST_PACKAGE_DIR = os.path.join(os.path.dirname(__file__), "test_discovery_test_package")


@pytest.fixture
def mock_ble_manager():
    """Create a mock BLEManager for testing."""
    mock_manager = MagicMock(spec=BLEManager)
    mock_manager.connect_to_device = AsyncMock(return_value=True)
    mock_manager.disconnect = AsyncMock()
    return mock_manager


@pytest.fixture
def test_runner(mock_ble_manager):
    """Create a TestRunner instance for testing."""
    return TestRunner(mock_ble_manager)


def test_init(test_runner, mock_ble_manager):
    """Test initialization of TestRunner."""
    assert test_runner.ble_manager == mock_ble_manager
    assert isinstance(test_runner.test_context, TestContext)


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
    assert test_runner._is_package(str(package_dir)) is True
    assert test_runner._is_package(str(not_package_dir)) is False


@patch("importlib.util.spec_from_file_location")
@patch("importlib.util.module_from_spec")
@patch("os.path.exists")
def test_import_package(mock_exists, mock_module_from_spec, mock_spec_from_file, test_runner, tmp_path):
    """Test the _import_package method."""
    # Setup
    mock_exists.return_value = True

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

    # Test with base package
    with patch.dict("sys.modules", {}, clear=True):
        result = test_runner._import_package(str(package_dir), "base.package")
        assert result == "base.package.my_test_package"
        mock_exists.assert_called_with(str(package_dir / "__init__.py"))
        mock_spec_from_file.assert_called_with("base.package.my_test_package", str(package_dir / "__init__.py"))

    # Test without base package
    mock_exists.reset_mock()
    mock_spec_from_file.reset_mock()

    with patch.dict("sys.modules", {}, clear=True):
        result = test_runner._import_package(str(package_dir))
        assert result == "my_test_package"
        mock_exists.assert_called_with(str(package_dir / "__init__.py"))
        mock_spec_from_file.assert_called_with("my_test_package", str(package_dir / "__init__.py"))


@patch("os.path.isdir")
@patch("os.path.exists")
def test_find_and_import_nearest_package(mock_exists, mock_isdir, test_runner, tmp_path):
    """Test the _find_and_import_nearest_package method."""
    # Setup
    mock_isdir.return_value = True

    # Create a package directory structure
    package_dir = tmp_path / "path" / "to" / "test" / "package"
    package_dir.mkdir(parents=True)

    # Test when a package is found
    def exists_side_effect(path):
        return "__init__.py" in path

    mock_exists.side_effect = exists_side_effect

    with patch.object(test_runner, "_import_package") as mock_import:
        mock_import.return_value = "package"  # Just the package name, not the full import path
        result = test_runner._find_and_import_nearest_package(str(package_dir))
        assert result == ("package", str(package_dir))

    # Test when no package is found
    mock_exists.side_effect = lambda path: False
    result = test_runner._find_and_import_nearest_package(str(tmp_path / "path" / "to" / "nowhere"))
    assert result is None


@pytest.mark.asyncio
@patch("inspect.getmembers")
async def test_run_test_function(mock_getmembers, test_runner):
    """Test running a test function."""
    # Setup
    test_name = "test_function"
    test_description = "Test description"

    # Create a mock test function
    mock_test_func = AsyncMock()
    mock_test_func._is_ble_test = True
    mock_test_func._test_description = test_description

    # Mock the test context
    test_runner.test_context.start_test = MagicMock()
    test_runner.test_context.end_test = MagicMock()
    test_runner.test_context.unsubscribe_all = AsyncMock()

    # Run the test
    await test_runner.run_test(test_name, mock_test_func)

    # Assert
    test_runner.test_context.start_test.assert_called_once_with(test_description)
    mock_test_func.assert_called_once_with(test_runner.ble_manager, test_runner.test_context)
    test_runner.test_context.end_test.assert_called_once_with(TestStatus.PASS)
    test_runner.test_context.unsubscribe_all.assert_called_once()


@pytest.mark.asyncio
@patch("inspect.getmembers")
async def test_run_test_class(mock_getmembers, test_runner):
    """Test running a test class."""
    # Setup
    test_name = "TestClass.test_method"
    test_description = "Test class description"

    # Create a mock test class and method
    mock_test_method = AsyncMock()
    mock_test_method._test_description = test_description

    # Create a mock class instance that will be returned by the class constructor
    mock_instance = MagicMock()
    mock_instance.setUp = AsyncMock()
    mock_instance.tearDown = AsyncMock()

    # Create a mock class that returns the mock instance when called
    mock_test_class = MagicMock()
    mock_test_class._is_test_class = True
    mock_test_class._test_description = test_description
    mock_test_class.return_value = mock_instance
    mock_test_class.test_method = mock_test_method

    # Setup the test item as a tuple (class_name, class_obj, method)
    test_item = ("TestClass", mock_test_class, mock_test_method)

    # Mock the test context
    test_runner.test_context.start_test = MagicMock()
    test_runner.test_context.end_test = MagicMock()
    test_runner.test_context.unsubscribe_all = AsyncMock()

    # Run the test
    await test_runner.run_test(test_name, test_item)

    # Assert
    test_runner.test_context.start_test.assert_called_once_with(test_description)
    mock_instance.setUp.assert_called_once_with(test_runner.ble_manager, test_runner.test_context)
    mock_test_method.assert_called_once_with(mock_instance, test_runner.ble_manager, test_runner.test_context)
    mock_instance.tearDown.assert_called_once_with(test_runner.ble_manager, test_runner.test_context)
    test_runner.test_context.end_test.assert_called_once_with(TestStatus.PASS)
    test_runner.test_context.unsubscribe_all.assert_called_once()


@pytest.mark.asyncio
async def test_run_tests(test_runner):
    """Test running multiple tests."""
    # Setup
    mock_func1 = AsyncMock()
    mock_func1._is_ble_test = True
    mock_func2 = AsyncMock()
    mock_func2._is_ble_test = True

    tests = [("test_1", mock_func1), ("test_2", mock_func2)]

    # Mock the run_test method
    test_runner.run_test = AsyncMock()

    # Mock the test context
    test_runner.test_context.get_test_summary = MagicMock(return_value={"results": {}})
    test_runner.test_context.cleanup_tasks = AsyncMock()

    # Run the tests
    result = await test_runner.run_tests(tests)

    # Assert
    assert test_runner.run_test.call_count == 2
    test_runner.run_test.assert_any_call("test_1", mock_func1)
    test_runner.run_test.assert_any_call("test_2", mock_func2)
    test_runner.test_context.get_test_summary.assert_called_once()
    test_runner.test_context.cleanup_tasks.assert_called_once()
    assert result == {"results": {}}
