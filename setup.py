"""Setup script for the test-a-ble package."""

import os

from setuptools import find_packages, setup

# Read the contents of the README file
with open(os.path.join(os.path.dirname(__file__), "README.md"), encoding="utf-8") as f:
    long_description = f.read()

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
        "rich>=12.0.0",
        "packaging",
        "prompt_toolkit>=3.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "black>=22.0.0",
            "isort>=5.10.0",
            "flake8>=7.0.0",
            "flake8-docstrings>=1.7.0",
            "flake8-pyproject>=1.2.3",
            "mypy>=0.9.0",
            "sphinx>=4.0.0",
            "sphinx-rtd-theme>=1.0.0",
            "twine>=4.0.0",
            "build>=0.8.0",
            "myst-parser>=4.0.1",
        ],
    },
    entry_points={
        "console_scripts": [
            "test-a-ble=test_a_ble.cli:main",
        ],
    },
    python_requires=">=3.8",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",  # Add appropriate license
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Testing",
        "Topic :: System :: Hardware",
    ],
    keywords="bluetooth, ble, iot, testing, automation",
)
