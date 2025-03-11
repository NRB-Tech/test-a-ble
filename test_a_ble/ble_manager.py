"""
BLE Manager.

Manages BLE device discovery, connection, and communication.
"""

import asyncio
import logging
import sys
import uuid
from typing import Any, Callable, Dict, List, Optional, Union

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

logger = logging.getLogger(__name__)


def retrieveConnectedPeripheralsWithServices(
    scanner: BleakScanner, services: Union[List[str], List[uuid.UUID]]
) -> list[BLEDevice]:
    """Retrieve connected peripherals with specified services."""
    devices = []
    if sys.platform == "darwin":
        from CoreBluetooth import CBUUID
        from Foundation import NSArray

        for p in scanner._backend._manager.central_manager.retrieveConnectedPeripheralsWithServices_(
            NSArray.alloc().initWithArray_(list(map(CBUUID.UUIDWithString_, services)))
        ):
            if scanner._backend._use_bdaddr:
                # HACK: retrieveAddressForPeripheral_ is undocumented but seems to do the
                # trick
                address_bytes: bytes = scanner._backend._manager.central_manager.retrieveAddressForPeripheral_(p)
                address = address_bytes.hex(":").upper()
            else:
                address = p.identifier().UUIDString()

            device = scanner._backend.create_or_update_device(
                address,
                p.name(),
                (p, scanner._backend._manager.central_manager.delegate()),
                AdvertisementData(
                    local_name=p.name(),
                    manufacturer_data=None,
                    service_data=None,
                    service_uuids=None,
                    tx_power=None,
                    rssi=None,
                    platform_data=None,
                ),
            )
            devices.append(device)
        logger.debug(f"Found {len(devices)} connected devices with services {services}")
    return devices


class BLEManager:
    """Manages BLE device discovery, connection, and communication."""

    # Class variable to store services that the framework should look for when finding connected devices
    _expected_service_uuids = set()

    @classmethod
    def register_expected_services(cls, service_uuids):
        """
        Register service UUIDs that should be used when looking for connected devices.

        Args:
            service_uuids: List or set of service UUID strings in standard format
        """
        if not service_uuids:
            return

        # Convert to set for deduplication
        if isinstance(service_uuids, (list, tuple, set)):
            cls._expected_service_uuids.update(service_uuids)
        else:
            # If a single UUID is provided
            cls._expected_service_uuids.add(service_uuids)

        logger.debug(f"Registered expected service UUIDs: {cls._expected_service_uuids}")

    def __init__(self):
        """Initialize the BLEManager."""
        self.device: Optional[BLEDevice] = None
        self.client: Optional[BleakClient] = None
        self.discovered_devices: List[BLEDevice] = []
        self.services: Dict[str, Any] = {}
        self.characteristics: Dict[str, Any] = {}
        self.notification_callbacks: Dict[str, List[Callable]] = {}
        self.connected = False
        self.advertisement_data_map: Dict[str, AdvertisementData] = {}  # Map device addresses to advertisement data
        self.active_subscriptions: Dict[str, Callable] = {}  # Added for active subscriptions

    async def discover_devices(
        self,
        timeout: float = 5.0,
        name_filter: Optional[str] = None,
        address_filter: Optional[str] = None,
    ) -> List[BLEDevice]:
        """
        Scan for BLE devices and return filtered results.

        Args:
            timeout: Scan duration in seconds
            name_filter: Optional filter for device name (substring match)
            address_filter: Optional filter for device address

        Returns:
            List of discovered BLE devices matching filters
        """
        logger.debug(f"Scanning for BLE devices (timeout: {timeout}s)")

        self.discovered_devices = []
        self.advertisement_data_map = {}  # Reset the map

        def _device_found(device: BLEDevice, adv_data: AdvertisementData):
            # Skip devices we've already found
            if any(d.address == device.address for d in self.discovered_devices):
                return

            # Apply filters
            if name_filter and name_filter.lower() not in (device.name or "").lower():
                return

            if address_filter and address_filter != device.address:
                return

            # Store advertisement data in our map
            self.advertisement_data_map[device.address] = adv_data
            self.discovered_devices.append(device)
            logger.debug(f"Found device: {device.name or 'Unknown'} ({device.address})")

        # Perform scan
        scanner = BleakScanner(detection_callback=_device_found)

        devices = retrieveConnectedPeripheralsWithServices(scanner, self._expected_service_uuids)
        self.discovered_devices.extend(devices)

        if devices:
            logger.debug(
                f"Found {len(devices)} connected devices with services "
                f"{self._expected_service_uuids}, not scanning for more devices"
            )
        else:
            await scanner.start()
            await asyncio.sleep(timeout)
            await scanner.stop()

        # Sort by signal strength (RSSI)
        def get_rssi(device):
            # Get advertisement data for device or use default RSSI
            adv_data = self.advertisement_data_map.get(device.address)
            return adv_data.rssi if adv_data else -100

        self.discovered_devices.sort(key=get_rssi, reverse=True)

        logger.debug(f"Discovered {len(self.discovered_devices)} devices")
        return self.discovered_devices

    async def connect_to_device(
        self,
        device_or_address: Union[BLEDevice, str],
        retry_count: int = 3,
        retry_delay: float = 1.0,
    ) -> bool:
        """
        Connect to a BLE device.

        Args:
            device_or_address: BLEDevice or device address to connect to
            retry_count: Number of connection attempts before failing
            retry_delay: Delay between retries in seconds

        Returns:
            True if connection successful, False otherwise
        """
        # Check if device_or_address is a string or a BLEDevice
        if isinstance(device_or_address, str):
            # Look up device by address in discovered devices
            device_address = device_or_address
            for device in self.discovered_devices:
                if device.address == device_address:
                    self.device = device
                    break

            # If not found in discovered devices, handle special cases
            if not self.device:
                logger.debug(f"Device with address {device_or_address} not in discovered devices")

                # on macos, we have to scan for the device first
                if sys.platform == "darwin":
                    devices = await self.discover_devices(timeout=5.0, address_filter=device_or_address)
                    if devices:
                        self.device = devices[0]
                        logger.debug(f"Found device: {self.device.name or 'Unknown'} ({self.device.address})")
                    else:
                        logger.error(f"Could not find device with address {device_or_address}")
                        return False
                else:
                    try:
                        # For modern Bleak (0.19.0+), create a device with required parameters
                        self.device = BLEDevice(address=device_or_address, name=None, details={}, rssi=0)
                    except Exception as e:
                        logger.error(f"Failed to create BLEDevice: {str(e)}")
                        logger.debug("Attempting to discover the device first...")

                        # Try to discover the device first
                        devices = await self.discover_devices(timeout=5.0, address_filter=device_or_address)

                        if devices:
                            self.device = devices[0]
                            logger.debug(f"Found device: {self.device.name or 'Unknown'} ({self.device.address})")
                        else:
                            logger.error(f"Could not find device with address {device_or_address}")
                            self.device = None
                            return False
        else:
            self.device = device_or_address

        logger.info(f"Connecting to {self.device.name or 'Unknown'} ({self.device.address})")

        # Attempt connection with retries
        for attempt in range(retry_count):
            try:
                logger.debug(f"Connection attempt {attempt + 1}/{retry_count}")

                # Create client with the device identifier
                self.client = BleakClient(self.device)

                # Connect to the device
                await self.client.connect()

                self.connected = True
                logger.info(f"Connected to {self.device.name or 'Unknown'} ({self.device.address})")
                return True

            except Exception as e:
                logger.warning(f"Connection attempt {attempt + 1} failed: {str(e)}")
                if attempt < retry_count - 1:
                    await asyncio.sleep(retry_delay)

        logger.error(f"Failed to connect to device after {retry_count} attempts")
        self.device = None
        return False

    async def disconnect(self):
        """Disconnect from the connected device and clean up resources."""
        logger.debug("Starting BLE disconnect process")

        if not self.client:
            logger.debug("No client to disconnect")
            return

        # First, clean up all active subscriptions
        subscription_uuids = list(self.active_subscriptions.keys())
        if subscription_uuids:
            logger.debug(f"Cleaning up {len(subscription_uuids)} active subscriptions")
            for sub_uuid in subscription_uuids:
                try:
                    logger.debug(f"Unsubscribing from {sub_uuid}")
                    await self.unsubscribe_from_characteristic(sub_uuid)
                except Exception as e:
                    logger.debug(f"Error cleaning up subscription to {uuid}: {e}")

        # Now attempt to disconnect from the device
        try:
            if self.client.is_connected:
                logger.info(f"Disconnecting from {self.device.address if self.device else 'unknown device'}")
                await self.client.disconnect()
                logger.debug("Disconnected successfully")
            else:
                logger.debug("Client already disconnected")
        except Exception as e:
            logger.error(f"Error during disconnect: {e}")
        finally:
            # Ensure these are cleaned up regardless of disconnect success
            self.connected = False
            self.active_subscriptions.clear()
            self.notification_callbacks.clear()
            self.services.clear()
            self.characteristics.clear()

            # Clear the client reference
            self.client = None

            logger.debug("Disconnect cleanup completed")

    async def discover_services(self, cache: bool = True) -> Dict[str, Any]:
        """
        Discover services and characteristics of the connected device.

        Args:
            cache: Whether to cache results for future use

        Returns:
            Dictionary of services and their characteristics
        """
        if not self.client or not self.client.is_connected:
            logger.error("Not connected to any device")
            return {}

        logger.debug("Discovering services and characteristics")

        # Return cached services if available
        if self.device.address in self.services and cache:
            return self.services[self.device.address]

        # Discover services
        services = {}
        for service in self.client.services:
            characteristics = {}
            for char in service.characteristics:
                properties = []
                if "read" in char.properties:
                    properties.append("read")
                if "write" in char.properties:
                    properties.append("write")
                if "notify" in char.properties:
                    properties.append("notify")

                characteristics[str(char.uuid)] = {
                    "uuid": str(char.uuid),
                    "properties": properties,
                    "description": char.description or "",
                    "handle": char.handle,
                }

            services[str(service.uuid)] = {
                "uuid": str(service.uuid),
                "characteristics": characteristics,
            }

        if cache:
            self.services[self.device.address] = services

        logger.debug(f"Discovered {len(services)} services")
        return services

    async def read_characteristic(self, characteristic_uuid: str) -> bytearray:
        """
        Read value from a characteristic.

        Args:
            characteristic_uuid: UUID of the characteristic to read

        Returns:
            Bytes read from the characteristic
        """
        if not self.client or not self.client.is_connected:
            raise RuntimeError("Not connected to any device")

        logger.debug(f"Reading characteristic: {characteristic_uuid}")
        value = await self.client.read_gatt_char(characteristic_uuid)
        logger.debug(f"Read value: {value.hex()}")
        return value

    async def write_characteristic(
        self,
        characteristic_uuid: str,
        data: Union[bytes, bytearray, memoryview],
        response: bool = True,
    ) -> None:
        """
        Write value to a characteristic.

        Args:
            characteristic_uuid: UUID of the characteristic to write to
            data: Data to write
            response: Whether to wait for response
        """
        if not self.client or not self.client.is_connected:
            raise RuntimeError("Not connected to any device")

        logger.debug(f"Writing to characteristic {characteristic_uuid}: {data.hex()}")

        # Check if the characteristic is readable before trying to read it
        is_readable = False
        try:
            # Get the services if not already cached
            if not self.services:
                await self.discover_services()

            # Look for the characteristic in all services
            for service_uuid, service_info in self.services.get(self.device.address, {}).items():
                characteristics = service_info.get("characteristics", {})
                if characteristic_uuid in characteristics:
                    properties = characteristics[characteristic_uuid].get("properties", [])
                    is_readable = "read" in properties
                    break

            logger.debug(f"Characteristic {characteristic_uuid} is readable: {is_readable}")
        except Exception as e:
            logger.debug(f"Error checking if characteristic is readable: {str(e)}")
            is_readable = False

        try:
            # Try to get current value before writing (if characteristic supports reading)
            if is_readable:
                try:
                    current_value = await self.client.read_gatt_char(characteristic_uuid)
                    logger.debug(f"Current value before write: {current_value.hex()}")
                except Exception as e:
                    logger.debug(f"Could not read characteristic before write despite being readable: {str(e)}")
            else:
                logger.debug("Skipping pre-write read - characteristic not readable")

            # Write the new value
            await self.client.write_gatt_char(characteristic_uuid, data, response)
            logger.debug(f"Write command sent for {characteristic_uuid}")

            # Verify the write was successful if response is True and characteristic is readable
            if response and is_readable:
                try:
                    # Small delay to allow the device to process the write
                    await asyncio.sleep(0.1)

                    # Read back the value to verify
                    new_value = await self.client.read_gatt_char(characteristic_uuid)

                    # Check if the value matches what we wrote
                    if new_value == data:
                        logger.debug(f"Write verified: {new_value.hex()}")
                    else:
                        logger.warning(f"Write verification failed. Expected: {data.hex()}, Got: {new_value.hex()}")
                except Exception as e:
                    logger.debug(f"Could not verify write: {str(e)}")
            elif not is_readable:
                logger.debug("Skipping write verification - characteristic not readable")

            logger.debug("Write operation completed")
        except Exception as e:
            logger.error(f"Error writing to characteristic {characteristic_uuid}: {str(e)}")
            raise

    def _notification_handler(self, characteristic_uuid: str):
        """Create a notification handler for a specific characteristic."""

        def _handle_notification(sender, data: bytearray):
            """
            Handle BLE notifications in latest Bleak versions.

            The sender parameter can be of different types in different Bleak versions.
            """
            # Check if we received actual data - sometimes error strings may be passed
            if isinstance(data, bytearray) or isinstance(data, bytes):
                logger.debug(f"Notification from {characteristic_uuid}: {data.hex()}")
                # Call all registered callbacks for this characteristic
                if characteristic_uuid in self.notification_callbacks:
                    for callback in self.notification_callbacks[characteristic_uuid]:
                        try:
                            callback(data)
                        except Exception as e:
                            logger.error(f"Error in notification callback: {str(e)}")
            # If we get a non-data value (like an error string), log it but don't invoke callbacks
            elif data is not None:
                # Log but at debug level to avoid cluttering logs
                logger.debug(f"Received non-data notification from {characteristic_uuid}: {data}")

        return _handle_notification

    async def subscribe_to_characteristic(
        self, characteristic_uuid: str, callback: Callable[[bytearray], None]
    ) -> None:
        """
        Subscribe to notifications from a characteristic.

        Args:
            characteristic_uuid: UUID of the characteristic to subscribe to
            callback: Function to call when notification is received
        """
        if not self.client or not self.client.is_connected:
            raise RuntimeError("Not connected to any device")

        # Register callback
        if characteristic_uuid not in self.notification_callbacks:
            self.notification_callbacks[characteristic_uuid] = []
            # Start listening for notifications
            try:
                await self.client.start_notify(characteristic_uuid, self._notification_handler(characteristic_uuid))
                # Track the active subscription
                self.active_subscriptions[characteristic_uuid] = True
                logger.debug(f"Subscribed to notifications from {characteristic_uuid}")
            except Exception as e:
                logger.error(f"Failed to subscribe to {characteristic_uuid}: {e}")
                raise

        self.notification_callbacks[characteristic_uuid].append(callback)
        logger.debug(
            f"Added callback for {characteristic_uuid}, total callbacks: "
            f"{len(self.notification_callbacks[characteristic_uuid])}"
        )

    async def unsubscribe_from_characteristic(self, characteristic_uuid: str) -> None:
        """
        Unsubscribe from notifications from a characteristic.

        Args:
            characteristic_uuid: UUID of the characteristic to unsubscribe from
        """
        # Handle case where we're not connected anymore
        if not self.client or not self.client.is_connected:
            logger.debug(f"Not connected when unsubscribing from {characteristic_uuid}")
            # Clean up local tracking
            if characteristic_uuid in self.notification_callbacks:
                logger.debug(f"Clearing callbacks for {characteristic_uuid} (not connected)")
                del self.notification_callbacks[characteristic_uuid]
            if characteristic_uuid in self.active_subscriptions:
                logger.debug(f"Removing from active subscriptions: {characteristic_uuid} (not connected)")
                del self.active_subscriptions[characteristic_uuid]
            return

        # Otherwise handle normally with the connected client
        try:
            # Stop notifications from the device if we're subscribed
            if characteristic_uuid in self.active_subscriptions:
                try:
                    await self.client.stop_notify(characteristic_uuid)
                    logger.info(f"Unsubscribed from notifications from {characteristic_uuid}")
                except Exception as e:
                    logger.error(f"Error stopping notifications for {characteristic_uuid}: {e}")
                finally:
                    # Remove from active subscriptions even if there was an error
                    del self.active_subscriptions[characteristic_uuid]
            else:
                logger.debug(f"No active subscription for {characteristic_uuid}")

            # Clear any registered callbacks
            if characteristic_uuid in self.notification_callbacks:
                logger.debug(
                    f"Clearing {len(self.notification_callbacks[characteristic_uuid])} callbacks for "
                    f"{characteristic_uuid}"
                )
                del self.notification_callbacks[characteristic_uuid]

        except Exception as e:
            logger.error(f"Error during unsubscribe from {characteristic_uuid}: {e}")
            # Still clean up local state even if there was an error
            if characteristic_uuid in self.active_subscriptions:
                del self.active_subscriptions[characteristic_uuid]
            if characteristic_uuid in self.notification_callbacks:
                del self.notification_callbacks[characteristic_uuid]

    def get_discovered_device_info(self) -> List[Dict[str, Any]]:
        """Return information about discovered devices in a structured format."""
        result = []
        for device in self.discovered_devices:
            # Get RSSI from our advertisement data map
            adv_data = self.advertisement_data_map.get(device.address)
            rssi = adv_data.rssi if adv_data else None

            result.append(
                {
                    "name": device.name or "Unknown",
                    "address": device.address,
                    "rssi": rssi,
                }
            )
        return result
