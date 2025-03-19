#!/usr/bin/env python3
"""Script to bump the version of the package.

Usage: python scripts/bump_version.py [major|minor|patch]
"""

import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def update_pyproject_toml(new_version):
    """Update the version in pyproject.toml."""
    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
    content = pyproject_path.read_text()

    # Replace the version in project section
    content = re.sub(
        r'version = "[0-9]+\.[0-9]+\.[0-9]+"',
        f'version = "{new_version}"',
        content,
    )

    pyproject_path.write_text(content)
    print(f"Updated version in pyproject.toml to {new_version}")


def update_init_py(new_version):
    """Update the version in __init__.py."""
    init_py_path = Path(__file__).parent.parent / "test_a_ble" / "__init__.py"
    content = init_py_path.read_text()

    # Replace the version
    content = re.sub(
        r'__version__ = "[0-9]+\.[0-9]+\.[0-9]+"',
        f'__version__ = "{new_version}"',
        content,
    )

    init_py_path.write_text(content)
    print(f"Updated version in __init__.py to {new_version}")


def update_docs_conf_py(new_version):
    """Update the version in docs/source/conf.py."""
    conf_py_path = Path(__file__).parent.parent / "docs" / "source" / "conf.py"
    content = conf_py_path.read_text()

    # Replace the version
    content = re.sub(r"release = '[0-9]+\.[0-9]+\.[0-9]+'", f"release = '{new_version}'", content)

    conf_py_path.write_text(content)
    print(f"Updated version in docs/source/conf.py to {new_version}")


def update_changelog(new_version):
    """Update the changelog with a new version section."""
    changelog_path = Path(__file__).parent.parent / "CHANGELOG.md"
    content = changelog_path.read_text()

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
-"""

    # Find the position after the header section
    header_end = content.find("## [")
    if header_end == -1:
        print("Could not find version section in CHANGELOG.md")
        return

    # Insert the new section after the header
    updated_content = content[:header_end] + new_section + "\n\n\n" + content[header_end:]

    changelog_path.write_text(updated_content)
    print(f"Updated CHANGELOG.md with new version {new_version}")


def get_current_version():
    """Get the current version from pyproject.toml."""
    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
    try:
        content = pyproject_path.read_text()
        match = re.search(r'^version = "([0-9]+\.[0-9]+\.[0-9]+)"', content, re.MULTILINE)
        if match:
            return match.group(1)
    except Exception as e:
        print(f"Error reading pyproject.toml: {e}")
        sys.exit(1)

    print("Could not find version in pyproject.toml")
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


def run_command(cmd, check=True):
    """Run a command safely."""
    try:
        return subprocess.run(cmd, check=check, shell=False, text=True, capture_output=True)  # noqa: S603  # nosec: B603
    except subprocess.CalledProcessError as e:
        print(f"Command failed: {e}")
        print(f"Command output:\n{e.stdout}\n{e.stderr}")
        sys.exit(1)


def run_build():
    """Run the build for the release."""
    print("Running build...")
    run_command(["make", "build"])
    print("Build passed.")


def run_checks():
    """Run the checks for the release."""
    print("Running checks...")
    run_command(["make", "check"])
    print("Checks passed.")


def run_git_command(cmd, check=True):
    """Run a git command safely."""
    return run_command(["git", *cmd], check=check)


def check_tag_exists(tag_name):
    """Check if a git tag already exists."""
    result = run_git_command(["tag", "-l", tag_name], check=False)
    return tag_name in result.stdout.splitlines()


def delete_tag(tag_name, remote=False):
    """Delete a git tag locally and optionally from remote."""
    run_git_command(["tag", "-d", tag_name])
    if remote:
        run_git_command(["push", "origin", f":refs/tags/{tag_name}"], check=False)


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

        update_pyproject_toml(new_version)
        update_init_py(new_version)
        update_docs_conf_py(new_version)
        update_changelog(new_version)
        run_checks()

        print(f"Version bumped to {new_version}")
        print("Now update the changelog: CHANGELOG.md")
        print("Don't forget to commit the changes and create a new tag:")
        print(f"git commit -am 'Bump version to {new_version}'")
    else:
        new_version = current_version
        print("Commands to run to create a new tag:")

    print(f"git tag -a v{new_version} -m 'Version {new_version}'")
    print("git push && git push --tags")
    print("\nDo you want to run the git commands now? (y/n)")
    response = input().strip().lower()

    if response in {"y", "yes"}:
        print("Running git commands...")
        if args.part:
            run_git_command(["commit", "-am", f"Bump version to {new_version}"])

        tag_name = f"v{new_version}"
        if check_tag_exists(tag_name):
            print(f"\nTag {tag_name} already exists!")
            print("Do you want to delete the existing tag and recreate it? (y/n)")
            retag_response = input().strip().lower()
            if retag_response in {"y", "yes"}:
                delete_tag(tag_name, remote=True)
            else:
                print("Aborting tag creation.")
                return

        run_git_command(["tag", "-a", tag_name, "-m", f"Version {new_version}"])

        print("Do you want to push the changes? (y/n)")
        push_response = input().strip().lower()
        if push_response in {"y", "yes"}:
            run_git_command(["push"])
            run_git_command(["push", "--tags"])
            print("Changes pushed successfully.")
        else:
            print("Changes committed and tagged locally. Run 'git push && git push --tags' when ready.")
    else:
        print("Commands not executed. Run them manually when ready.")


if __name__ == "__main__":
    main()
