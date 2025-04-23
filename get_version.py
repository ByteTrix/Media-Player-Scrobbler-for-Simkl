#!/usr/bin/env python
"""
Extract version number from pyproject.toml for automated version management.
Used by build scripts to ensure version consistency across the project.
"""

import re
import sys

def get_version_from_pyproject():
    """Extract version from pyproject.toml file."""
    try:
        with open('pyproject.toml', 'r') as f:
            content = f.read()
        
        # Find the version using regex
        match = re.search(r'version\s*=\s*"([^"]+)"', content)
        if match:
            return match.group(1)
        else:
            print("Error: Could not find version in pyproject.toml", file=sys.stderr)
            return "0.0.0"  # Default fallback version
    except Exception as e:
        print(f"Error reading pyproject.toml: {e}", file=sys.stderr)
        return "0.0.0"  # Default fallback version

if __name__ == "__main__":
    # Print the version to stdout so it can be captured by build scripts
    print(get_version_from_pyproject())