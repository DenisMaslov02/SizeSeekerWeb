"""Entry point for the frozen (PyInstaller) build."""

import sys

from sizeseekerweb.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
