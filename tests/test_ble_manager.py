"""Basic tests for the test-a-ble package."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from test_a_ble import __version__


def test_version():
    """Test that the version is a string."""
    assert isinstance(__version__, str)


@pytest.mark.asyncio
@patch("test_a_ble.ble_manager.BleakScanner")
@patch("test_a_ble.ble_manager.asyncio")
async def test_device_discovery_mock(mock_asyncio, mock_scanner):
    """Test device discovery with mocked BleakScanner."""
    from test_a_ble.ble_manager import BLEManager

    # Setup mock device
    mock_device = MagicMock()
    mock_device.name = "Test Device"
    mock_device.address = "00:11:22:33:44:55"

    # Create manager instance with mocked discover_devices method
    with patch.object(BLEManager, "discover_devices", new_callable=AsyncMock) as mock_discover:
        # Setup the mock to return our device
        mock_discover.return_value = [mock_device]

        # Create manager instance
        manager = BLEManager()

        # Now we can properly await the mocked method
        devices = await manager.discover_devices()

        # Assert
        assert len(devices) == 1
        assert devices[0].name == "Test Device"
        assert devices[0].address == "00:11:22:33:44:55"


@pytest.mark.asyncio
async def test_connect_to_device():
    """Test connecting to a device."""
    from test_a_ble.ble_manager import BLEManager

    # Create mock device
    mock_device = MagicMock()
    mock_device.name = "Test Device"
    mock_device.address = "00:11:22:33:44:55"

    # Create manager instance
    manager = BLEManager()
    manager.discovered_devices = [mock_device]

    # Mock BleakClient
    with patch("test_a_ble.ble_manager.BleakClient") as mock_client_class:
        # Setup the mock client
        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client_class.return_value = mock_client

        # Call connect_to_device with the device address
        result = await manager.connect_to_device("00:11:22:33:44:55")

        # Assert
        assert result is True
        assert manager.device == mock_device
        assert manager.client == mock_client
        assert manager.connected is True
        mock_client.connect.assert_called_once()


@pytest.mark.asyncio
async def test_connect_to_device_not_found():
    """Test connecting to a device that's not in discovered devices."""
    from test_a_ble.ble_manager import BLEManager

    # Create manager instance
    manager = BLEManager()
    manager.discovered_devices = []

    # Mock discover_devices to return no devices
    with patch.object(manager, "discover_devices", new_callable=AsyncMock) as mock_discover:
        mock_discover.return_value = []

        # Call connect_to_device with a non-existent address
        result = await manager.connect_to_device("00:11:22:33:44:55")

        # Assert
        assert result is False
        assert manager.device is None
        assert manager.connected is False


@pytest.mark.asyncio
async def test_disconnect():
    """Test disconnecting from a device."""
    from test_a_ble.ble_manager import BLEManager

    # Create manager instance
    manager = BLEManager()

    # Mock client
    mock_client = MagicMock()
    mock_client.is_connected = True
    mock_client.disconnect = AsyncMock()
    manager.client = mock_client

    # Mock device
    mock_device = MagicMock()
    mock_device.address = "00:11:22:33:44:55"
    manager.device = mock_device

    # Set connected state
    manager.connected = True

    # Call disconnect
    await manager.disconnect()

    # Assert
    assert manager.connected is False
    assert manager.client is None
    mock_client.disconnect.assert_called_once()


@pytest.mark.asyncio
async def test_discover_services():
    """Test discovering services."""
    from test_a_ble.ble_manager import BLEManager

    # Create manager instance
    manager = BLEManager()

    # Mock device
    mock_device = MagicMock()
    mock_device.address = "00:11:22:33:44:55"
    manager.device = mock_device

    # Mock client
    mock_client = MagicMock()
    mock_client.is_connected = True

    # Create mock service
    mock_service = MagicMock()
    mock_service.uuid = "0000180d-0000-1000-8000-00805f9b34fb"  # Heart Rate Service

    # Create mock characteristic
    mock_char = MagicMock()
    mock_char.uuid = "00002a37-0000-1000-8000-00805f9b34fb"  # Heart Rate Measurement
    mock_char.properties = ["read", "notify"]
    mock_char.description = "Heart Rate Measurement"
    mock_char.handle = 42

    # Add characteristic to service
    mock_service.characteristics = [mock_char]

    # Add service to client
    mock_client.services = [mock_service]

    # Set client
    manager.client = mock_client

    # Call discover_services
    services = await manager.discover_services()

    # Assert
    assert len(services) == 1
    assert "0000180d-0000-1000-8000-00805f9b34fb" in services
    assert "00002a37-0000-1000-8000-00805f9b34fb" in services["0000180d-0000-1000-8000-00805f9b34fb"]["characteristics"]
    assert (
        "read"
        in services["0000180d-0000-1000-8000-00805f9b34fb"]["characteristics"]["00002a37-0000-1000-8000-00805f9b34fb"][
            "properties"
        ]
    )
    assert (
        "notify"
        in services["0000180d-0000-1000-8000-00805f9b34fb"]["characteristics"]["00002a37-0000-1000-8000-00805f9b34fb"][
            "properties"
        ]
    )


@pytest.mark.asyncio
async def test_read_characteristic():
    """Test reading a characteristic."""
    from test_a_ble.ble_manager import BLEManager

    # Create manager instance
    manager = BLEManager()

    # Mock client
    mock_client = MagicMock()
    mock_client.is_connected = True
    mock_client.read_gatt_char = AsyncMock()
    mock_client.read_gatt_char.return_value = bytearray([0x01, 0x02, 0x03])
    manager.client = mock_client

    # Call read_characteristic
    char_uuid = "00002a37-0000-1000-8000-00805f9b34fb"
    result = await manager.read_characteristic(char_uuid)

    # Assert
    assert result == bytearray([0x01, 0x02, 0x03])
    mock_client.read_gatt_char.assert_called_once_with(char_uuid)


@pytest.mark.asyncio
async def test_write_characteristic():
    """Test writing to a characteristic."""
    from test_a_ble.ble_manager import BLEManager

    # Create manager instance
    manager = BLEManager()

    # Mock client
    mock_client = MagicMock()
    mock_client.is_connected = True
    mock_client.write_gatt_char = AsyncMock()
    manager.client = mock_client

    # Mock discover_services
    with patch.object(manager, "discover_services", new_callable=AsyncMock) as mock_discover:
        # Setup mock services
        mock_services = {
            "00:11:22:33:44:55": {
                "0000180d-0000-1000-8000-00805f9b34fb": {
                    "uuid": "0000180d-0000-1000-8000-00805f9b34fb",
                    "characteristics": {
                        "00002a39-0000-1000-8000-00805f9b34fb": {
                            "uuid": "00002a39-0000-1000-8000-00805f9b34fb",
                            "properties": ["write"],
                            "description": "Heart Rate Control Point",
                            "handle": 43,
                        }
                    },
                }
            }
        }
        mock_discover.return_value = mock_services
        manager.services = mock_services

        # Mock device
        mock_device = MagicMock()
        mock_device.address = "00:11:22:33:44:55"
        manager.device = mock_device

        # Call write_characteristic
        char_uuid = "00002a39-0000-1000-8000-00805f9b34fb"
        data = bytearray([0x01])
        await manager.write_characteristic(char_uuid, data)

        # Assert
        mock_client.write_gatt_char.assert_called_once_with(char_uuid, data, True)


@pytest.mark.asyncio
async def test_subscribe_to_characteristic():
    """Test subscribing to a characteristic."""
    from test_a_ble.ble_manager import BLEManager

    # Create manager instance
    manager = BLEManager()

    # Mock client
    mock_client = MagicMock()
    mock_client.is_connected = True
    mock_client.start_notify = AsyncMock()
    manager.client = mock_client

    # Create a callback function
    callback = MagicMock()

    # Call subscribe_to_characteristic
    char_uuid = "00002a37-0000-1000-8000-00805f9b34fb"
    await manager.subscribe_to_characteristic(char_uuid, callback)

    # Assert
    assert char_uuid in manager.notification_callbacks
    assert callback in manager.notification_callbacks[char_uuid]
    assert char_uuid in manager.active_subscriptions
    mock_client.start_notify.assert_called_once()


@pytest.mark.asyncio
async def test_unsubscribe_from_characteristic():
    """Test unsubscribing from a characteristic."""
    from test_a_ble.ble_manager import BLEManager

    # Create manager instance
    manager = BLEManager()

    # Mock client
    mock_client = MagicMock()
    mock_client.is_connected = True
    mock_client.stop_notify = AsyncMock()
    manager.client = mock_client

    # Setup active subscription
    char_uuid = "00002a37-0000-1000-8000-00805f9b34fb"
    callback = MagicMock()
    manager.notification_callbacks[char_uuid] = [callback]
    manager.active_subscriptions[char_uuid] = True

    # Call unsubscribe_from_characteristic
    await manager.unsubscribe_from_characteristic(char_uuid)

    # Assert
    assert char_uuid not in manager.notification_callbacks
    assert char_uuid not in manager.active_subscriptions
    mock_client.stop_notify.assert_called_once_with(char_uuid)


@pytest.mark.asyncio
async def test_notification_handler():
    """Test the notification handler."""
    from test_a_ble.ble_manager import BLEManager

    # Create manager instance
    manager = BLEManager()

    # Create a callback function
    callback = MagicMock()

    # Setup notification callbacks
    char_uuid = "00002a37-0000-1000-8000-00805f9b34fb"
    manager.notification_callbacks[char_uuid] = [callback]

    # Get the notification handler
    handler = manager._notification_handler(char_uuid)

    # Call the handler with some data
    data = bytearray([0x01, 0x02, 0x03])
    handler(None, data)

    # Assert
    callback.assert_called_once_with(data)


@pytest.mark.asyncio
async def test_get_discovered_device_info():
    """Test getting discovered device info."""
    from test_a_ble.ble_manager import BLEManager

    # Create manager instance
    manager = BLEManager()

    # Create mock devices
    mock_device1 = MagicMock()
    mock_device1.name = "Device 1"
    mock_device1.address = "00:11:22:33:44:55"

    mock_device2 = MagicMock()
    mock_device2.name = None  # Test device with no name
    mock_device2.address = "66:77:88:99:AA:BB"

    # Add devices to discovered_devices
    manager.discovered_devices = [mock_device1, mock_device2]

    # Create mock advertisement data
    mock_adv_data1 = MagicMock()
    mock_adv_data1.rssi = -50

    # Add advertisement data to map
    manager.advertisement_data_map = {"00:11:22:33:44:55": mock_adv_data1}

    # Call get_discovered_device_info
    result = manager.get_discovered_device_info()

    # Assert
    assert len(result) == 2
    assert result[0]["name"] == "Device 1"
    assert result[0]["address"] == "00:11:22:33:44:55"
    assert result[0]["rssi"] == -50
    assert result[1]["name"] == "Unknown"  # Should default to "Unknown"
    assert result[1]["address"] == "66:77:88:99:AA:BB"
    assert result[1]["rssi"] is None  # No advertisement data for this device


@pytest.mark.asyncio
async def test_register_expected_services():
    """Test registering expected services."""
    from test_a_ble.ble_manager import BLEManager

    # Clear expected services before test
    BLEManager._expected_service_uuids = set()

    # Register a single service
    BLEManager.register_expected_services("0000180d-0000-1000-8000-00805f9b34fb")
    assert "0000180d-0000-1000-8000-00805f9b34fb" in BLEManager._expected_service_uuids

    # Register multiple services
    BLEManager.register_expected_services(
        ["0000180a-0000-1000-8000-00805f9b34fb", "00001810-0000-1000-8000-00805f9b34fb"]
    )
    assert "0000180a-0000-1000-8000-00805f9b34fb" in BLEManager._expected_service_uuids
    assert "00001810-0000-1000-8000-00805f9b34fb" in BLEManager._expected_service_uuids

    # Register a duplicate service (should not add duplicates)
    BLEManager.register_expected_services("0000180d-0000-1000-8000-00805f9b34fb")
    assert len(BLEManager._expected_service_uuids) == 3
