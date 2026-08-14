# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
"""Render the casu CLI session as a terminal-style screenshot."""
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "docs" / "screenshots" / "casu-codec-cli.png"

COMMANDS = [
    ["casu", "--version"],
    ["casu", "mp5-info", "test_media/demo.mp5"],
    ["casu", "native-info", "test_media/demo_casunat2.casu"],
    ["casu", "verify", "test_media/demo_clip.mp4.casu"],
]


def run(cmd):
    proc = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True, timeout=60)
    return (proc.stdout or proc.stderr).strip()


def main() -> int:
    lines = []
    for cmd in COMMANDS:
        lines.append("$ " + " ".join(cmd))
        output = run(cmd)
        lines.extend(output.splitlines())
        lines.append("")
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 15)
    except OSError:
        font = ImageFont.load_default()
    pad, line_h = 22, 22
    width = max(len(line) for line in lines) * 9 + pad * 2
    width = max(900, min(width, 1400))
    height = len(lines) * line_h + pad * 2 + 34
    image = Image.new("RGB", (width, height), "#07090b")
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, width, 34], fill="#101317")
    draw.ellipse([12, 11, 24, 23], fill="#ff1e2d")
    draw.ellipse([30, 11, 42, 23], fill="#e0a010")
    draw.ellipse([48, 11, 60, 23], fill="#25c065")
    draw.text((72, 9), "casu — Codec for All Segmented Units", fill="#b9bec5", font=font)
    y = pad + 34
    for line in lines:
        color = "#ff5d68" if line.startswith("$") else "#f4f5f7"
        if line.startswith("VALID") or line.startswith("{") or line.startswith("  "):
            color = "#9fe8b8" if line.startswith("VALID") else "#d7d9dc"
        draw.text((pad, y), line[:150], fill=color, font=font)
        y += line_h
    image.save(OUT)
    print(f"saved {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
