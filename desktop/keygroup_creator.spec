# -*- mode: python -*-
# SPDX-License-Identifier: MIT
# PyInstaller recipe for the standalone desktop app. Build with (from the project root):
#   python3 scripts/make_desktop_icons.py
#   pyinstaller desktop/keygroup_creator.spec --noconfirm
# Normally run by .github/workflows/build-apps.yml on GitHub's macOS and Windows machines.
import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
APP_NAME = "Wavethings Keygroup Creator"
VERSION = "1.4.1"

if sys.platform == "darwin":
    platform_mod, icon = "webview.platforms.cocoa", "icon.icns"
elif sys.platform == "win32":
    platform_mod, icon = "webview.platforms.edgechromium", "icon.ico"
else:
    platform_mod, icon = "webview.platforms.gtk", "icon.png"

a = Analysis(
    [str(ROOT / "desktop" / "app.py")],
    pathex=[str(ROOT)],
    hiddenimports=["webview", platform_mod, "keygroup_creator_gui", "mpc_keygroup_creator",
                   "ogg_preview"] + (["clr"] if sys.platform == "win32" else []),
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name=APP_NAME if sys.platform != "darwin" else "WavethingsKeygroupCreator",
    console=False,
    icon=str(ROOT / "assets" / icon),
)
coll = COLLECT(exe, a.binaries, a.datas, name=APP_NAME)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=str(ROOT / "assets" / "icon.icns"),
        bundle_identifier="com.wavethings.keygroupcreator",
        info_plist={
            "CFBundleName": APP_NAME,
            "CFBundleDisplayName": APP_NAME,
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHumanReadableCopyright": "Copyright (c) 2026 Wavethings - MIT License",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
        },
    )
