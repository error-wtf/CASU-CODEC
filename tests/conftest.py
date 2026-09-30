# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
"""Pytest bootstrap: make the repo root importable without pyproject help.

pyproject `pythonpath = ["."]` covers plain `pytest` runs from the root; this
conftest additionally covers running single test files by path or from a
subdirectory (casu.* and mpcasu_qt.* must resolve to THIS checkout).
Parity with the Casu-Player repo's tests/conftest.py.
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if _ROOT.is_dir() and str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
