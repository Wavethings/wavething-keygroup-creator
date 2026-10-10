#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Wavethings
"""
Wavethings Keygroup Creator - standalone desktop app.

The entry point PyInstaller packages into "Wavethings Keygroup Creator.app" (macOS) and
"Wavethings Keygroup Creator.exe" (Windows). It starts the same local server as
keygroup_creator_gui.py and shows it in its own native window (pywebview) instead of the browser.
The window only loads pages from 127.0.0.1; nothing goes to the internet.

Run from source (needs `pip install -r requirements-desktop.txt`):
    python3 desktop/app.py
The real .app / .exe are built by .github/workflows/build-apps.yml on GitHub's macOS and
Windows machines whenever a release is published.
"""
import sys
import threading
import traceback
from pathlib import Path

if getattr(sys, "frozen", False):           # inside the PyInstaller bundle
    sys.path.insert(0, str(Path(sys._MEIPASS)))
else:                                       # from source: modules live one folder up
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import webview  # noqa: E402  (pywebview, build-only dependency)

import keygroup_creator_gui as gui  # noqa: E402
import mpc_keygroup_creator as kc  # noqa: E402

WINDOW = None


def _dialog_kinds():
    fd = getattr(webview, "FileDialog", None)          # pywebview 5.3+
    if fd is not None:
        return fd.FOLDER, fd.OPEN
    return webview.FOLDER_DIALOG, webview.OPEN_DIALOG  # older pywebview


def native_pick(kind):
    """Folder / .xpm chooser of the window itself (replaces osascript / tkinter)."""
    folder, openf = _dialog_kinds()
    try:
        if kind == "folder":
            r = WINDOW.create_file_dialog(folder)
        else:
            r = WINDOW.create_file_dialog(openf, file_types=("MPC program (*.xpm)", "All files (*.*)"))
    except Exception:
        gui.log(traceback.format_exc())
        return None
    if not r:
        return ""
    return r[0] if isinstance(r, (list, tuple)) else str(r)


def main():
    global WINDOW
    try:
        server, url = gui.start_server()
    except Exception:
        gui.log(traceback.format_exc())
        raise
    threading.Thread(target=server.serve_forever, daemon=True).start()
    gui.PICKER = native_pick
    WINDOW = webview.create_window(f"Wavethings Keygroup Creator {kc.VERSION}", url,
                                   width=1240, height=900, min_size=(820, 600),
                                   background_color="#141518")
    webview.start()
    server.shutdown()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        gui.log("desktop app crashed:\n" + traceback.format_exc())
        raise
