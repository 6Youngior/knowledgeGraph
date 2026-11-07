"""Compatibility entry point for the complete classroom presentation journey."""
from pathlib import Path
import runpy

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).with_name("check_presentation_flow.py")), run_name="__main__")
