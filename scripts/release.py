#!/usr/bin/env python3
"""Script to bump the version of the package.

Usage: python scripts/bump_version.py [major|minor|patch]
"""

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime


def update_setup_py(new_version):
    """Update the version in setup.py."""
    setup_py_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "setup.py")
    with open(setup_py_path) as f:
        content = f.read()

    # Replace the version
    content = re.sub(r'version="[0-9]+\.[0-9]+\.[0-9]+"', f'version="{new_version}"', content)

    with open(setup_py_path, "w") as f:
        f.write(content)

    print(f"Updated version in setup.py to {new_version}")


def update_init_py(new_version):
    """Update the version in __init__.py."""
    init_py_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "test-a-ble", "__init__.py")
    with open(init_py_path) as f:
        content = f.read()

    # Replace the version
    content = re.sub(
        r'__version__ = "[0-9]+\.[0-9]+\.[0-9]+"',
        f'__version__ = "{new_version}"',
        content,
    )

    with open(init_py_path, "w") as f:
        f.write(content)

    print(f"Updated version in __init__.py to {new_version}")


def update_docs_conf_py(new_version):
    """Update the version in docs/source/conf.py."""
    conf_py_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "source", "conf.py")
    with open(conf_py_path) as f:
        content = f.read()

    # Replace the version
    content = re.sub(r"release = '[0-9]+\.[0-9]+\.[0-9]+'", f"release = '{new_version}'", content)

    with open(conf_py_path, "w") as f:
        f.write(content)

    print(f"Updated version in docs/source/conf.py to {new_version}")


def update_changelog(new_version):
    """Update the changelog with a new version section."""
    changelog_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "CHANGELOG.md")
    with open(changelog_path) as f:
        content = f.read()

    # Check if the new version already exists in the changelog
    if f"## [{new_version}]" in content:
        print(f"Version {new_version} already exists in CHANGELOG.md")
        return

    # Get the current date
    today = datetime.now().strftime("%Y-%m-%d")

    # Create a new version section
    new_section = f"""## [{new_version}] - {today}

### Added
-

### Changed
-

### Fixed
-

"""

    # Insert the new section after the header
    content = re.sub(
        r"(## \[)",
        f"{new_section}\n\n\1",
        content,
        flags=re.DOTALL,
    )

    with open(changelog_path, "w") as f:
        f.write(content)

    print(f"Updated CHANGELOG.md with new version {new_version}")


def get_current_version():
    """Get the current version from setup.py."""
    setup_py_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "setup.py")
    with open(setup_py_path) as f:
        content = f.read()

    # Extract the version
    match = re.search(r'version="([0-9]+\.[0-9]+\.[0-9]+)"', content)
    if match:
        return match.group(1)
    print("Could not find version in setup.py")
    sys.exit(1)


def bump_version(current_version, part):
    """Bump the version according to the specified part."""
    major, minor, patch = map(int, current_version.split("."))

    if part == "major":
        major += 1
        minor = 0
        patch = 0
    elif part == "minor":
        minor += 1
        patch = 0
    elif part == "patch":
        patch += 1
    else:
        print(f"Invalid part: {part}")
        sys.exit(1)

    return f"{major}.{minor}.{patch}"


def main():
    """Execute the main function."""
    parser = argparse.ArgumentParser(description="Bump the version of the package.")
    parser.add_argument(
        "part",
        nargs="?",
        choices=["major", "minor", "patch"],
        help="The part of the version to bump (optional)",
    )
    args = parser.parse_args()

    current_version = get_current_version()
    if args.part:
        new_version = bump_version(current_version, args.part)
        print(f"Bumping version from {current_version} to {new_version}")

        update_setup_py(new_version)
        update_init_py(new_version)
        update_docs_conf_py(new_version)
        update_changelog(new_version)

        print(f"Version bumped to {new_version}")
        print("Don't forget to commit the changes and create a new tag:")
        print(f"git commit -am 'Bump version to {new_version}'")
    else:
        new_version = current_version
        print("Commands to run to create a new tag:")

    print(f"git tag -a v{new_version} -m 'Version {new_version}'")
    print("git push && git push --tags")
    print("\nDo you want to run the git commands now? (y/n)")
    response = input().strip().lower()

    if response == "y" or response == "yes":
        print("Running git commands...")
        if args.part:
            subprocess.run(["git", "commit", "-am", f"Bump version to {new_version}"], check=True, shell=False)  # nosec B603
        subprocess.run(["git", "tag", "-a", f"v{new_version}", "-m", f"Version {new_version}"], check=True, shell=False)  # nosec B603

        print("Do you want to push the changes? (y/n)")
        push_response = input().strip().lower()
        if push_response == "y" or push_response == "yes":
            subprocess.run(["git", "push"], check=True, shell=False)  # nosec B603
            subprocess.run(["git", "push", "--tags"], check=True, shell=False)  # nosec B603
            print("Changes pushed successfully.")
        else:
            print("Changes committed and tagged locally. Run 'git push && git push --tags' when ready.")
    else:
        print("Commands not executed. Run them manually when ready.")


if __name__ == "__main__":
    main()
