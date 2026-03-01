"""pytest configuration — adds test-simulator root to sys.path."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
