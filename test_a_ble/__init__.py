"""
BLE IoT Device Testing Framework.

A modular, extensible framework for testing Bluetooth Low Energy IoT devices.
"""

import logging
import sys
from typing import Optional

__version__ = "0.1.0"


def setup_logging(verbose: bool = False, log_file: Optional[str] = None):
    """
    Configure logging for the BLE test framework.

    Args:
        verbose: If True, set log level to DEBUG, otherwise WARNING to hide
                 INFO logs during test
        log_file: Optional path to a log file to write logs to
    """
    # Set up logger with the desired log level
    root_logger = logging.getLogger()
    # Always maintain DEBUG level on the root logger to allow file logging
    root_logger.setLevel(logging.DEBUG)

    # Configure console handler with a format
    console_handler = logging.StreamHandler(sys.stdout)
    # Only show INFO+ logs during tests if verbose is enabled, otherwise
    # WARNING+
    console_handler.setLevel(logging.DEBUG if verbose else logging.WARNING)

    # Create a formatter that includes the timestamp, level, and message
    # Using a more concise format for better readability during tests
    formatter = logging.Formatter(
        ("%(levelname)-8s %(message)s" if not verbose else "%(asctime)s %(levelname)-8s %(message)s"),
        datefmt="%H:%M:%S",
    )
    console_handler.setFormatter(formatter)

    # Remove any existing handlers to avoid duplicate logs
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add the console handler to the root logger
    root_logger.addHandler(console_handler)

    # Add file handler if log_file is specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)  # Always log DEBUG to file
        file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(message)s", datefmt="%H:%M:%S"))
        root_logger.addHandler(file_handler)

    # Configure specific package loggers
    if not verbose:
        # Set higher log levels for noisy libraries and framework components
        # to reduce output
        logging.getLogger("bleak").setLevel(logging.WARNING)
        logging.getLogger("asyncio").setLevel(logging.WARNING)
        logging.getLogger("test_a_ble.ble_manager").setLevel(logging.WARNING)

    # Log the configuration
    logging.debug(f"Logging configured (verbose: {verbose}, log_file: {log_file})")
