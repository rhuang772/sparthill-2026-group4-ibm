"""
tests/conftest.py

Adds app/providers to sys.path so that tests/test_airhub_sim.py can use
    from airhub_sim import ...
without any modification to the original test file.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app" / "providers"))
