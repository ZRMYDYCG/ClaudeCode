"""Backward-compatible launcher: `python main.py` / `uv run python main.py`."""

from core.cli import main

if __name__ == "__main__":
    main()
