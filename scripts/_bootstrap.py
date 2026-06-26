"""Put the repo root on sys.path so ``import experiments`` works when scripts
are run directly (``python scripts/foo.py``)."""
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
