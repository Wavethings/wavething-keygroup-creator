#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Writes assets/icon.png, assets/icon.ico and (on macOS) assets/icon.icns from the icon drawn
in build_app.py. Run from the project root before building the desktop app:
    python3 scripts/make_desktop_icons.py
"""
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import build_app  # noqa: E402


def main():
    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)
    (assets / "icon.png").write_bytes(build_app.png(512))
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [build_app.png(s) for s in sizes]
    head = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, data = b"", b""
    for s, img in zip(sizes, images):
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(img), offset + len(data))
        data += img
    (assets / "icon.ico").write_bytes(head + entries + data)
    print("assets/icon.png, assets/icon.ico")
    if sys.platform == "darwin":
        if build_app.make_icon(assets / "icon.icns"):
            print("assets/icon.icns")
        else:
            sys.exit("iconutil failed")


if __name__ == "__main__":
    main()
