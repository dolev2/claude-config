"""Make the board sync's modules importable by their own names in the tests.

sync_project.py imports its flat siblings (board, marker, ...) the way Python finds them
when the script runs: from its own folder (claude-config #57).
"""

import sys
from pathlib import Path

PROJECT_SYNC = Path(__file__).resolve().parents[1] / "actions" / "project-sync"
sys.path.insert(0, str(PROJECT_SYNC))
