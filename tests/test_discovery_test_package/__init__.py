"""Test discovery test package."""

import os
import time

# Create a timestamp file to track when the package was imported
TIMESTAMP_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "import_timestamp.txt")

# Write the current timestamp to the file
with open(TIMESTAMP_FILE, "w") as f:
    f.write(str(time.time()))
