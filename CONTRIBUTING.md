# Contributing to SIMKL Scrobbler

Thank you for considering contributing to SIMKL Scrobbler! This document provides guidelines and instructions for contributing.

## Code of Conduct

Please be respectful and considerate when interacting with other contributors.

## How to Contribute

### Reporting Bugs

1. Check if the bug has already been reported in the Issues section
2. Use the bug report template when creating a new issue
3. Include detailed steps to reproduce the bug
4. Include information about your environment (OS, Python version, media player)
5. Add screenshots if relevant

### Suggesting Features

1. Check if the feature has already been suggested in the Issues section
2. Use the feature request template when creating a new issue
3. Explain why the feature would be useful to most users
4. Describe how the feature should work

### Contributing Code

1. Fork the repository
2. Create a new branch for your feature (`git checkout -b feature/amazing-feature`)
3. Follow the existing code style
4. Add tests for your changes
5. Ensure all tests pass: `python master_test.py`
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to your branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

## Development Setup

1. Fork and clone the repository
2. Install development dependencies:
   ```bash
   pip install -r requirements.txt
   pip install pytest pytest-cov
   ```
3. Create a .env file with your Simkl API credentials:
   ```
   SIMKL_CLIENT_ID=your_client_id
   SIMKL_ACCESS_TOKEN=your_access_token
   ```
4. Run tests to make sure everything works:
   ```bash
   python master_test.py
   ```

## Testing

All new features and bug fixes should include tests. We use:

- `master_test.py` for comprehensive testing
- Tests should cover all major aspects of your changes
- When testing the tracker with media players, use the `-t` flag to run in test mode

## Pull Request Process

1. Update the README.md with details of changes if they affect the API or user experience
2. Update the version numbers in setup.py and any other relevant files
3. The PR will be merged once it's been reviewed and approved

## Style Guide

- Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/) for Python code
- Use meaningful variable and function names
- Write docstrings for all functions, classes, and methods
- Keep functions small and focused on a single task
- Comment complex code sections

## License

By contributing, you agree that your contributions will be licensed under the project's MIT License.