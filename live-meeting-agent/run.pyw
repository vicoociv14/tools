"""Silent entry point for the Live Meeting Agent capture core.

Launched by Task Scheduler at logon via pythonw.exe (no console window).
Run for development with:  python -m lma.capture.tray
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lma.capture.tray import main  # noqa: E402  (after sys.path setup)

if __name__ == "__main__":
    sys.exit(main())
