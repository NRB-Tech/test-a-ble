"""Setup script for the test-a-ble package."""

import os

from setuptools import find_packages, setup

# Read the contents of the README file
with open(os.path.join(os.path.dirname(__file__), "README.md"), encoding="utf-8") as f:
    long_description = f.read()

extras_require = {
    "test": [
        "pytest>=8.3.5",
        "pytest-cov>=6.0.0",
        "pytest-asyncio>=0.22.0",
        "tox>=4.24.2",
    ],
    "lint": [
        "black>=25.1.0",
        "isort>=6.0.1",
        "flake8>=7.1.2",
        "flake8-docstrings>=1.7.0",
        "flake8-pyproject>=1.2.3",
        "mypy>=1.15.0",
    ],
    "security": [
        "bandit>=1.8.3",
        "safety>=3.3.1",
    ],
    "docs": [
        "sphinx>=8.2.3",
        "sphinx-rtd-theme>=3.0.2",
        "myst-parser>=4.0.1",
    ],
    "build": [
        "twine>=6.1.0",
        "build>=1.2.2",
    ],
    "dev": [],
}
# make "dev" an alias for "test lint security docs build"
extras_require["dev"] = (
    extras_require["test"]
    + extras_require["lint"]
    + extras_require["security"]
    + extras_require["docs"]
    + extras_require["build"]
)
setup(
    name="test-a-ble",
    version="0.1.0",
    description="Framework for testing BLE IoT devices",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Nick Brook",
    author_email="nick@nrbtech.io",
    url="https://github.com/nrb-tech/test-a-ble",
    packages=find_packages(),
    install_requires=[
        "bleak>=0.22.3",
        "rich>=13.9.4",
        "packaging",
        "prompt_toolkit>=3.0.0",
    ],
    extras_require=extras_require,
    entry_points={
        "console_scripts": [
            "test-a-ble=test_a_ble.cli:main",
        ],
    },
    python_requires=">=3.12",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",  # Add appropriate license
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Topic :: Software Development :: Testing",
        "Topic :: System :: Hardware",
    ],
    keywords="bluetooth, ble, iot, testing, automation",
)
