"""Launcher used by `python run.py` and as the PyInstaller entry point."""
import sys

from marquee.app import main

if __name__ == "__main__":
    sys.exit(main())
