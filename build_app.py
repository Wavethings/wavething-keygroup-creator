#!/usr/bin/env python3
"""Build "Wavethings Keygroup Creator.app" (macOS) next to this script.

Run once:  python3 build_app.py
Double-click the app: it opens the interface in your browser and quits when you close the tab.
Run it again after updating the scripts.
"""
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE / "Wavethings Keygroup Creator.app"
FILES = ["mpc_keygroup_creator.py", "keygroup_creator_gui.py", "ogg_preview.py"]
ES = any(v.lower().startswith("es") for v in [__import__("os").environ.get("LANG", "")])

PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>Wavethings Keygroup Creator</string>
<key>CFBundleDisplayName</key><string>Wavethings Keygroup Creator</string>
<key>CFBundleIdentifier</key><string>com.wavethings.keygroupcreator</string>
<key>CFBundleVersion</key><string>1.3.0</string>
<key>CFBundleShortVersionString</key><string>1.3.0</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleExecutable</key><string>KeygroupCreator</string>
<key>CFBundleIconFile</key><string>icon</string>
<key>LSMinimumSystemVersion</key><string>10.13</string>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
"""

LAUNCHER = """#!/bin/bash
DIR="$(cd "$(dirname "$0")/../Resources" && pwd)"
PY="$(command -v python3)"
for p in /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
  [ -z "$PY" ] && [ -x "$p" ] && PY="$p"
done
if [ -z "$PY" ]; then
  osascript -e 'display alert "Keygroup Creator needs Python 3 / necesita Python 3" message "Open Terminal and run / Abre la Terminal y ejecuta: xcode-select --install"'
  exit 1
fi
exec "$PY" "$DIR/keygroup_creator_gui.py" --app
"""


# ---------- icon: piano keys under coloured velocity layers, PNG written by hand ----------
def png(size):
    s = size
    rows = []
    r = s * 0.2                        # corner radius
    keys_top, keys_bot = s * 0.58, s * 0.86
    m = s * 0.12
    cols = [(255, 90, 54), (255, 150, 50), (255, 200, 60)]
    for y in range(s):
        row = bytearray([0])
        for x in range(s):
            # rounded square background
            dx = max(r - x, 0, x - (s - 1 - r))
            dy = max(r - y, 0, y - (s - 1 - r))
            inside = (dx * dx + dy * dy) <= r * r
            if not inside:
                row += b"\0\0\0\0"
                continue
            c = (29, 31, 36)
            if m <= x < s - m:
                if s * 0.16 <= y < keys_top - s * 0.03:      # three layer bands
                    band = int((y - s * 0.16) / ((keys_top - s * 0.03 - s * 0.16) / 3))
                    c = cols[2 - min(band, 2)]
                    if int((x - m) / ((s - 2 * m) / 3)) % 2:
                        c = tuple(int(v * 0.82) for v in c)
                elif keys_top <= y < keys_bot:
                    kw = (s - 2 * m) / 7
                    k = (x - m) / kw
                    c = (40, 42, 47) if (k - int(k)) > 0.9 else (240, 240, 236)
                    if y < keys_top + (keys_bot - keys_top) * 0.6:
                        for b in (1, 2, 4, 5, 6):
                            if abs((x - m) - b * kw) < kw * 0.3:
                                c = (40, 42, 47)
            row += bytes(c) + b"\xff"
        rows.append(bytes(row))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", s, s, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))


def make_icon(dest):
    iconset = dest.parent / "icon.iconset"
    iconset.mkdir(exist_ok=True)
    cache = {}
    for name, size in [("16x16", 16), ("16x16@2x", 32), ("32x32", 32), ("32x32@2x", 64),
                       ("128x128", 128), ("128x128@2x", 256), ("256x256", 256), ("256x256@2x", 512),
                       ("512x512", 512), ("512x512@2x", 1024)]:
        cache.setdefault(size, png(size))
        (iconset / f"icon_{name}.png").write_bytes(cache[size])
    try:
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(dest)], check=True,
                       capture_output=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False
    finally:
        shutil.rmtree(iconset, ignore_errors=True)


def main():
    missing = [f for f in FILES if not (HERE / f).is_file()]
    if missing:
        sys.exit(("Faltan archivos: " if ES else "Missing files: ") + ", ".join(missing))
    if APP.exists():
        shutil.rmtree(APP)
    macos, res = APP / "Contents" / "MacOS", APP / "Contents" / "Resources"
    macos.mkdir(parents=True)
    res.mkdir(parents=True)
    for f in FILES:
        shutil.copy2(HERE / f, res / f)
    (APP / "Contents" / "Info.plist").write_text(PLIST)
    launcher = macos / "KeygroupCreator"
    launcher.write_text(LAUNCHER)
    launcher.chmod(0o755)
    print("Creando icono…" if ES else "Making icon…")
    if not make_icon(res / "icon.icns"):
        print("  (sin icono: la app funciona igual)" if ES else "  (no icon: the app works anyway)")
    print(f"\n{'Listo' if ES else 'Done'}: {APP}")


if __name__ == "__main__":
    main()
