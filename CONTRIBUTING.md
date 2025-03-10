# Contributing to Test-a-BLE

Thank you for considering contributing to Test-a-BLE! This document provides guidelines and instructions for contributing.

## Code of Conduct

Please be respectful and considerate of others when contributing to this project.

## How to Contribute

1. **Fork the repository**
2. **Clone your fork**
   ```bash
   git clone https://github.com/your-username/test-a-ble.git
   cd test-a-ble
   ```
3. **Set up the development environment**
   ```bash
   pip install -e ".[dev]"
   ```
4. **Create a branch for your changes**
   ```bash
   git checkout -b feature/your-feature-name
   ```
5. **Make your changes**
6. **Run tests**
   ```bash
   pytest
   ```
7. **Format your code**
   ```bash
   black test-a-ble
   isort test-a-ble
   ```
8. **Commit your changes**
   ```bash
   git commit -m "Add your meaningful commit message here"
   ```
9. **Push to your fork**
   ```bash
   git push origin feature/your-feature-name
   ```
10. **Create a pull request**

## Development Guidelines

- Follow PEP 8 style guidelines
- Write tests for new features
- Update documentation for any changes
- Keep pull requests focused on a single topic

## Running Tests

```bash
pytest
```

## Building Documentation

```bash
cd docs
make html
```

## Reporting Issues

If you find a bug or have a feature request, please create an issue on GitHub.

## Release Process

Releases are managed by the maintainers. The process is:

1. Update version in `setup.py`
2. Update CHANGELOG.md
3. Create a new tag with the version number
4. Push the tag to GitHub
5. GitHub Actions will automatically build and publish to PyPI

## Versioning

We use [SemVer](http://semver.org/) for versioning. For the versions available, see the [tags on this repository](https://github.com/nrb-tech/test-a-ble/tags).

- **MAJOR** version when you make incompatible API changes
- **MINOR** version when you add functionality in a backwards compatible manner
- **PATCH** version when you make backwards compatible bug fixes

Thank you for your contributions!
