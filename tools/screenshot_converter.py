# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
"""Screenshot driver for the CASU converter (runs under Xvfb)."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
os.environ.setdefault("XDG_CONFIG_HOME", tempfile.mkdtemp(prefix="casu-conv-shot-"))

import casu_converter  # noqa: E402

app = casu_converter.CASUConverter()
media = root / "test_media"
app._set_sources([media / "demo_clip.mp4"])
app.output.set(str(Path(tempfile.mkdtemp(prefix="casu-out-"))))
app.direction.set("to-casu")
app._sync_direction()
app.status.set("Step 3 — press Convert to pack segmented CASU (source stays untouched).")
app.toast("Sources inspected · ready to convert")
app.after(20000, app.destroy)
app.mainloop()
