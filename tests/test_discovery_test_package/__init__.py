"""Test discovery test package."""

import time
from pathlib import Path

# Create a timestamp file to track when the package was imported
TIMESTAMP_FILE = Path(__file__).parent / "import_timestamp.txt"

# Write the current timestamp to the file
with TIMESTAMP_FILE.open("w") as f:
    f.write(str(time.time()))
