#!/usr/bin/env python3
"""Wavethings Keygroup Creator - browser interface.

Run:  python3 keygroup_creator_gui.py
A local server starts and the interface opens in your browser. Nothing leaves your computer.
"""
import json
import mimetypes
import os
import platform
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mpc_keygroup_creator as kc  # noqa: E402

APP_NAME = "Wavethings Keygroup Creator"


app_dir = kc.app_dir


SETTINGS = app_dir() / "settings.json"
LOG = app_dir() / "log.txt"
SCANNED = set()          # audio files the browser may play
STATE = {"last_ping": 0.0, "busy": False}


def log(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except OSError:
        pass


def load_settings():
    try:
        return json.loads(SETTINGS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(s):
    tmp = SETTINGS.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(SETTINGS)


# ----------------------------------------------------------------------------- native dialogs
PICKER = None   # the desktop app (desktop/app.py) puts its own native dialog here


def pick(kind, prompt=""):
    """Native folder / file chooser. Returns a path, "" if cancelled, None if unavailable."""
    if PICKER:
        return PICKER(kind)
    if sys.platform == "darwin":
        what = "choose folder" if kind == "folder" else "choose file"
        script = f'activate\nPOSIX path of ({what} with prompt "{prompt}")'
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else ""
    code = ("import tkinter as t,tkinter.filedialog as f;r=t.Tk();r.withdraw();"
            "r.attributes('-topmost',1);"
            + ("print(f.askdirectory())" if kind == "folder" else
               "print(f.askopenfilename(filetypes=[('MPC program','*.xpm'),('*','*')]))"))
    try:
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    return r.stdout.strip()


def reveal(path):
    p = Path(path)
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(p)])
        elif os.name == "nt":
            subprocess.Popen(["explorer", "/select,", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(p.parent)])
    except OSError:
        pass


# ----------------------------------------------------------------------------- API
def api(path, body):
    if path == "/api/init":
        s = load_settings()
        tpl = s.get("template") or None
        try:
            _, doc = kc.load_template(tpl)
        except Exception:
            tpl, (_, doc) = None, kc.load_template(None)
        return {"settings": s, "defaults": kc.template_sound(doc), "template_ok": True,
                "presets": kc.load_presets(), "builtin_presets": kc.BUILTIN_PRESETS,
                "filters": kc.FILTER_TYPES, "version": kc.VERSION,
                "home": str(Path.home()), "platform": platform.system()}
    if path == "/api/save":
        save_settings(body)
        return {"ok": True}
    if path == "/api/ping":
        STATE["last_ping"] = time.time()
        return {"ok": True}
    if path == "/api/pick":
        p = pick(body.get("kind", "folder"), body.get("prompt", ""))
        return {"path": p, "unsupported": p is None}
    if path == "/api/scan":
        samples = kc.scan_folder(body["folder"], body.get("recursive", False),
                                 body.get("octave", "c3"), body.get("numbers", False))
        SCANNED.update(s["path"] for s in samples)
        presets = body.get("presets") or kc.load_presets()
        if body.get("split", True):
            groups = kc.group_samples(samples, Path(body["folder"]).name)
        else:
            groups = [(kc.guess_name(samples, body["folder"]), samples)] if samples else []
        return {"groups": [{"name": n, "samples": g, "preset": kc.guess_preset(n, presets)}
                           for n, g in groups]}
    if path == "/api/presets":
        kc.save_presets(body["presets"])
        return {"ok": True}
    if path == "/api/map":
        kgs, warnings, errors = kc.build_map(body["samples"], body.get("zones", "center"),
                                             body.get("extend", True), body.get("vel", "auto"))
        return {"keygroups": [{"low": k["low"], "high": k["high"], "root": k["root"],
                               "layers": [{"path": l["sample"]["path"], "vstart": l["vstart"],
                                           "vend": l["vend"], "root": l["root"]}
                                          for l in k["layers"]]} for k in kgs],
                "warnings": warnings, "errors": errors}
    if path == "/api/template":
        p = body.get("path") or None
        _, doc = kc.load_template(p)
        return {"defaults": kc.template_sound(doc)}
    if path == "/api/generate":
        STATE["busy"] = True
        results = []
        try:
            progs = body["programs"]
            for prog, name in zip(progs, kc.unique_names([p["name"] for p in progs])):
                try:
                    xpm, kgs, warnings = kc.generate(
                        prog["samples"], name, body["output"], body.get("zones", "center"),
                        body.get("extend", True), body.get("vel", "auto"), prog.get("sound"),
                        body.get("template") or None, body.get("hardlink", False), log=log,
                        loops=body.get("loops", True), preview=body.get("preview", True),
                        preview_seconds=float(body.get("previewSeconds") or 6))
                    nfiles = len({l["sample"]["path"] for k in kgs for l in k["layers"]})
                    results.append({"name": name, "xpm": str(xpm), "keygroups": len(kgs),
                                    "samples": nfiles, "warnings": warnings})
                except kc.KeygroupError as e:
                    results.append({"name": name, "error": str(e)})
        finally:
            STATE["busy"] = False
        return {"results": results}
    if path == "/api/reveal":
        reveal(body["path"])
        return {"ok": True}
    raise KeyError(path)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, data, ctype="application/json; charset=utf-8"):
        if not isinstance(data, bytes):
            data = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path in ("/", "/index.html"):
            return self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        if u.path == "/audio":
            p = urllib.parse.parse_qs(u.query).get("p", [""])[0]
            if p not in SCANNED or not Path(p).is_file():
                return self._send(404, {"error": "not found"})
            ctype = mimetypes.guess_type(p)[0] or "audio/wav"
            return self._send(200, Path(p).read_bytes(), ctype)
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.headers.get("Origin") not in (None, f"http://{self.headers.get('Host')}"):
            return self._send(403, {"error": "forbidden"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            self._send(200, api(urllib.parse.urlparse(self.path).path, body))
        except kc.KeygroupError as e:
            self._send(400, {"error": str(e)})
        except KeyError as e:
            self._send(404, {"error": f"unknown: {e}"})
        except Exception as e:  # noqa: BLE001
            log(traceback.format_exc())
            self._send(500, {"error": f"{type(e).__name__}: {e}"})


def watchdog(server, grace=8.0):
    """App mode: quit a few seconds after the browser tab is closed."""
    while True:
        time.sleep(1)
        last = STATE["last_ping"]
        if last and not STATE["busy"] and time.time() - last > grace:
            log("browser closed, exiting")
            server.shutdown()
            return


def start_server(port=0):
    """Start the local server on 127.0.0.1 (port 0 = any free one). Returns (server, url).
    Used by main() below and by the desktop app, which shows `url` in its own window."""
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    log(f"start {kc.VERSION} {url}")
    return server, url


def main():
    app_mode = "--app" in sys.argv
    port = 0
    for a in sys.argv[1:]:
        if a.startswith("--port="):
            port = int(a.split("=", 1)[1])
    server, url = start_server(port)
    print(f"{APP_NAME} {kc.VERSION}: {url}  (Ctrl+C to quit)")
    if app_mode:
        threading.Thread(target=watchdog, args=(server,), daemon=True).start()
    if "--no-browser" not in sys.argv:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Keygroup Creator</title>
<style>
:root{--bg:#141518;--panel:#1d1f24;--panel2:#25282e;--line:#33373f;--text:#e8e9ec;--dim:#9aa0aa;
--acc:#ff5a36;--acc2:#ffb03a;--ok:#4cc38a;--warn:#ffb03a;--err:#ff5d5d;--key:#f4f4f2;--bkey:#2a2c31}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
header{display:flex;align-items:center;gap:12px;padding:14px 22px;border-bottom:1px solid var(--line);background:#101114;position:sticky;top:0;z-index:5}
header h1{font-size:16px;margin:0;font-weight:650;letter-spacing:.2px}
header h1 b{color:var(--acc)}
header .ver{color:var(--dim);font-size:12px}
header .sp{flex:1}
main{max-width:1180px;margin:0 auto;padding:18px 22px 60px;display:grid;gap:16px}
section{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px 18px}
section h2{margin:0 0 12px;font-size:13px;text-transform:uppercase;letter-spacing:1.2px;color:var(--dim);font-weight:650;display:flex;gap:10px;align-items:center}
section h2 .n{background:var(--acc);color:#fff;border-radius:50%;width:20px;height:20px;display:inline-grid;place-items:center;font-size:11px;letter-spacing:0}
.row{display:flex;flex-wrap:wrap;gap:10px 16px;align-items:center;margin-bottom:10px}
.row:last-child{margin-bottom:0}
label{color:var(--dim);font-size:13px}
input[type=text],input[type=number],select{background:var(--panel2);border:1px solid var(--line);color:var(--text);border-radius:6px;padding:6px 8px;font:inherit}
input[type=text]:focus,input[type=number]:focus,select:focus{outline:2px solid var(--acc);outline-offset:-1px}
input.path{flex:1;min-width:240px}
button{background:var(--panel2);color:var(--text);border:1px solid var(--line);border-radius:6px;padding:6px 12px;font:inherit;cursor:pointer}
button:hover{border-color:#555b66}
button.primary{background:var(--acc);border-color:var(--acc);color:#fff;font-weight:600;padding:9px 20px}
button.primary:hover{filter:brightness(1.08)}
button:disabled{opacity:.5;cursor:default}
.chk{display:inline-flex;gap:6px;align-items:center;color:var(--text);font-size:13px;cursor:pointer}
.hint{color:var(--dim);font-size:12.5px;margin:6px 0 0}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:6px;overflow:hidden}
.seg button{border:0;border-radius:0;padding:5px 10px;background:var(--panel2)}
.seg button.on{background:var(--acc);color:#fff}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;color:var(--dim);font-weight:500;padding:6px 8px;border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--panel)}
td{padding:4px 8px;border-bottom:1px solid #26292f}
tr.off td{opacity:.4}
tr.bad td.nm{color:var(--err)}
td.nm{word-break:break-all}
td input[type=text]{width:66px;padding:3px 6px}
td input.vel{width:58px}
.tablewrap{max-height:340px;overflow:auto;border:1px solid var(--line);border-radius:8px}
.play{width:26px;height:26px;padding:0;border-radius:50%;font-size:11px}
.src{font-size:11px;color:var(--dim)}
.badge{display:inline-block;padding:2px 8px;border-radius:10px;background:var(--panel2);font-size:12px;color:var(--dim)}
.badge.ok{color:var(--ok)}
.msgs{margin-top:10px;display:grid;gap:4px;font-size:13px}
.msgs .w{color:var(--warn)} .msgs .e{color:var(--err)} .msgs .o{color:var(--ok)}
#mapwrap{overflow-x:auto}
#map{width:100%;min-width:760px;display:block}
#map .zone rect{cursor:pointer}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:900px){.grid2{grid-template-columns:1fr}}
.card{background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:12px 14px}
.card h3{margin:0 0 8px;font-size:13px;font-weight:600}
.sl{display:grid;grid-template-columns:110px 1fr 78px;gap:8px;align-items:center;margin:5px 0}
.sl label{font-size:12.5px}
.sl input[type=range]{width:100%;accent-color:var(--acc)}
.sl input[type=number]{width:62px;padding:3px 5px}
#velSensN{width:78px;text-align:right}
.sl input.val{width:78px;padding:3px 6px;text-align:right;font-variant-numeric:tabular-nums}
svg.env{width:100%;height:90px;display:block;background:#17191d;border-radius:6px;margin-bottom:6px}
.out{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
#status{font-size:13px}
.empty{color:var(--dim);padding:22px;text-align:center}
.lang button{padding:3px 8px;font-size:12px}
.insts{display:grid;gap:6px;margin:4px 0 14px}
.inst{display:grid;grid-template-columns:22px minmax(160px,1fr) 90px 150px minmax(150px,auto);gap:10px;align-items:center;
 background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:6px 10px;cursor:pointer}
.inst.cur{border-color:var(--acc);box-shadow:0 0 0 1px var(--acc) inset}
.inst.off{opacity:.5}
.inst input[type=text]{width:100%;padding:4px 7px}
.inst .cnt{color:var(--dim);font-size:12.5px}
.inst .st{font-size:12px;color:var(--dim);text-align:right}
.inst .st.ok{color:var(--ok)} .inst .st.e{color:var(--err)}
@media(max-width:760px){.inst{grid-template-columns:22px 1fr 1fr}.inst .cnt,.inst .st{text-align:left}}
.sub{font-size:12.5px;color:var(--dim);margin:0 0 8px}
.sub b{color:var(--text)}
.presetbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:14px;padding:10px 12px;background:var(--panel2);border:1px solid var(--line);border-radius:8px}
.presetbar .mod{color:var(--warn);font-size:12px}
.sp{flex:1}
.dlg{position:fixed;inset:0;background:rgba(0,0,0,.55);display:grid;place-items:center;z-index:50}
.dlg[hidden]{display:none}
.dlg .box{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:18px;width:min(460px,calc(100vw - 32px));box-shadow:0 10px 40px rgba(0,0,0,.5)}
.dlg p{margin:0 0 12px;white-space:pre-wrap}
.dlg input{width:100%;margin-bottom:14px}
.dlg .btns{display:flex;justify-content:flex-end;gap:8px}
</style></head><body>
<header><h1><b>Wavethings</b> Keygroup Creator</h1><span class="ver" id="ver"></span><span class="sp"></span>
<span class="seg lang"><button data-lang="es">ES</button><button data-lang="en">EN</button></span></header>
<main>

<section>
<h2><span class="n">1</span><span data-t="sec_samples"></span></h2>
<div class="row"><label data-t="lbl_folder"></label><input type="text" class="path" id="folder" spellcheck="false">
<button id="pickFolder" data-t="btn_choose"></button><button id="scan" data-t="btn_scan"></button></div>
<div class="row">
<label class="chk"><input type="checkbox" id="recursive"><span data-t="chk_recursive"></span></label>
<label data-t="lbl_octave"></label><select id="octave"><option value="c3" data-t="oct_c3"></option><option value="c4" data-t="oct_c4"></option></select>
<label class="chk"><input type="checkbox" id="numbers"><span data-t="chk_numbers"></span></label>
<label class="chk"><input type="checkbox" id="split"><span data-t="chk_split"></span></label>
<span class="sp"></span><span class="badge" id="count"></span>
</div>
<div class="insts" id="insts"></div>
<p class="sub" id="curSamples"></p>
<div class="tablewrap"><table><thead><tr><th></th><th data-t="th_file"></th><th data-t="th_note"></th><th data-t="th_vel"></th><th data-t="th_src"></th><th data-t="th_loop"></th><th data-t="th_use"></th></tr></thead>
<tbody id="rows"><tr><td colspan="7" class="empty" data-t="no_samples"></td></tr></tbody></table></div>
<p class="hint" data-t="hint_names"></p>
</section>

<section>
<h2><span class="n">2</span><span data-t="sec_map"></span></h2>
<div class="row">
<label data-t="lbl_zones"></label><span class="seg" id="zones"><button data-v="center" data-t="z_center"></button><button data-v="up" data-t="z_up"></button><button data-v="down" data-t="z_down"></button></span>
<label class="chk"><input type="checkbox" id="extend"><span data-t="chk_extend"></span></label>
<label data-t="lbl_vel"></label><select id="velmode"><option value="auto" data-t="v_auto"></option><option value="upper" data-t="v_upper"></option><option value="center" data-t="v_center"></option><option value="even" data-t="v_even"></option></select>
<span class="sp"></span><span class="badge" id="summary"></span>
</div>
<div id="mapwrap"><svg id="map" viewBox="0 0 1280 250"></svg></div>
<div class="msgs" id="mapmsgs"></div>
<p class="hint" data-t="hint_map"></p>
</section>

<section>
<h2><span class="n">3</span><span data-t="sec_sound"></span></h2>
<p class="sub" id="curSound"></p>
<div class="presetbar"><label data-t="lbl_preset"></label><select id="presetSel"></select><span class="mod" id="presetMod"></span>
<span class="sp"></span><button id="savePreset" data-t="btn_save_preset"></button><button id="renPreset" data-t="btn_ren_preset"></button><button id="delPreset" data-t="btn_del_preset"></button>
<button id="applyAll" data-t="btn_apply_all"></button><button id="resetSound" data-t="btn_reset"></button><button id="restorePresets" data-t="btn_restore"></button></div>
<div class="grid2">
<div class="card"><h3 data-t="amp_env"></h3><svg class="env" id="ampSvg" viewBox="0 0 400 90" preserveAspectRatio="none"></svg><div id="ampSl"></div>
<div class="sl"><label data-t="velsens"></label><input type="range" min="0" max="100" step="1" id="velSensR"><input type="number" min="0" max="100" step="0.1" id="velSensN"></div></div>
<div class="card"><h3 data-t="filter"></h3>
<div class="sl"><label data-t="f_type"></label><select id="ftype" style="grid-column:span 2"></select></div>
<div class="sl" id="fcustomRow" style="display:none"><label data-t="f_index"></label><input type="number" id="fcustom" min="0" max="60" style="grid-column:span 2;width:80px"></div>
<div id="filtSl"></div>
<div id="blendSl"></div>
<div class="sl"><span></span><label class="chk" style="grid-column:span 2"><input type="checkbox" id="serial"><span data-t="f_serial"></span></label></div>
<p class="hint" data-t="hint_blend"></p></div>
<div class="card"><h3 data-t="flt_env"></h3><svg class="env" id="fenvSvg" viewBox="0 0 400 90" preserveAspectRatio="none"></svg><div id="fenvSl"></div></div>
<div class="card"><h3 data-t="about_vals"></h3><p class="hint" style="margin:0" data-t="hint_vals"></p></div>
</div>
</section>

<section>
<h2><span class="n">4</span><span data-t="sec_out"></span></h2>
<div class="row"><label data-t="lbl_output"></label><input type="text" class="path" id="output" spellcheck="false"><button id="pickOut" data-t="btn_choose"></button></div>
<div class="row">
<label class="chk"><input type="checkbox" id="hardlink"><span data-t="chk_hardlink"></span></label>
<label class="chk"><input type="checkbox" id="loops"><span data-t="chk_loops"></span></label></div>
<div class="row"><label class="chk"><input type="checkbox" id="preview"><span data-t="chk_preview"></span></label>
<label data-t="lbl_pvsec"></label><input type="number" id="previewSeconds" min="1" max="30" step="0.5" style="width:70px"></div>
<div class="row"><label data-t="lbl_template"></label><span class="badge" id="tplname"></span><button id="pickTpl" data-t="btn_tpl"></button><button id="builtinTpl" data-t="btn_builtin"></button></div>
<p class="hint" data-t="hint_out"></p>
<div class="out" style="margin-top:14px"><button class="primary" id="go" data-t="btn_go"></button><span id="status"></span><button id="reveal" style="display:none" data-t="btn_reveal"></button></div>
<div class="msgs" id="genmsgs"></div>
</section>
</main>
<audio id="player"></audio>
<div class="dlg" id="dlg" hidden><div class="box"><p id="dlgMsg"></p><input type="text" id="dlgIn" spellcheck="false">
<div class="btns"><button id="dlgNo" data-t="btn_cancel"></button><button id="dlgOk" class="primary" data-t="btn_ok"></button></div></div></div>
<script>
const I18N={en:{
chk_split:"One program per instrument",hint_time:"Type a time: 250 ms, 1.5 s (a plain number is ms)",hint_sus:"0–127, as on the MPC",btn_ok:"OK",btn_cancel:"Cancel",chk_preview:"Create a preview for the MPC browser ([Previews]/Name.xpm.ogg)",lbl_pvsec:"Seconds",
w_preview_failed:"Preview not created ({0})",cur_samples:"Samples of <b>{0}</b> — click an instrument above to see its samples, map and sound.",
cur_sound:"Sound of <b>{0}</b>",no_preset:"— Template values —",lbl_preset:"Preset",modified:"● modified",btn_save_preset:"Save preset…",btn_ren_preset:"Rename…",btn_del_preset:"Delete",
btn_apply_all:"Apply to all instruments",btn_restore:"Restore built-in presets",ask_preset:"Preset name (an existing name is overwritten):",ask_rename:"New name for “{0}”:",
confirm_del:"Delete the preset “{0}”?",confirm_restore:"Put back the built-in presets (Pad, Lead, Pluck, Keys, Bass, Strings) with their original values? Your other presets are kept.",
applied_all:"Sound copied to {0} instrument(s)",inst_count:"{0} samples",st_ok:"{0} kg · {1} layer(s)",st_err:"⚠ check",n_inst:"{0} instruments",
btn_go_n:"Create {0} programs",results:"{0} program(s) created in {1}",
sec_samples:"Samples",lbl_folder:"Folder",btn_choose:"Choose…",btn_scan:"Scan",chk_recursive:"Include subfolders",
lbl_octave:"Note names",oct_c3:"C3 = 60 (MPC)",oct_c4:"C4 = 60",chk_numbers:"Accept MIDI numbers (_060_)",
th_file:"File",th_note:"Root note",th_vel:"Velocity",th_src:"Read from",th_loop:"Loop",no_loop:"—",chk_loops:"Use the loops stored in the samples",loop_tip:"Loop {0}–{1} s (of {2} s). The sample will end at the loop end, as when the MPC loads it.",th_use:"Use",no_samples:"Choose a folder and press Scan.",
src_name:"name",src_file:"file data",src_none:"— not found",src_edit:"edited",count:"{0} samples",
hint_names:"The root note is read from the name (C2, F#3, Db4…), and if missing, from the note stored inside the WAV/AIFF. Velocity layers come from V127 / vel64 / v1 v2 v3 or pp p mp mf f ff. You can type over any value; leave velocity empty for a single layer.",
sec_map:"Keygroups",lbl_zones:"Root note in its zone",z_center:"Centered",z_up:"At the bottom",z_down:"At the top",chk_extend:"Stretch to the whole keyboard",
lbl_vel:"Velocity values",v_auto:"Automatic",v_upper:"Top of the range",v_center:"Center of the range",v_even:"Equal parts",
summary:"{0} keygroups · {1} layer(s)",hint_map:"Each column is a keygroup, each block a velocity layer (soft at the bottom, hard at the top). Click a block to hear its sample. The MPC allows up to 8 layers per keygroup.",
sec_sound:"Envelopes and filter",btn_reset:"Template values",amp_env:"Amp envelope",flt_env:"Filter envelope",filter:"Filter",
Attack:"Attack",Hold:"Hold",Decay:"Decay",Sustain:"Sustain",Release:"Release",velsens:"Velocity → volume",blend:"Filter 1 ↔ 2 mix",f_serial:"Filters in series (default: parallel)",
hint_blend:"Mix 0 = only filter 1 is heard; 100 = only filter 2 (the MPC default is 50, both at once). In series the sound goes through filter 1 and then filter 2.",
f_type:"Type",f_index:"Type index",f_other:"Other (type the index)…",cutoff:"Cutoff",resonance:"Resonance",envAmount:"Env amount",keytrack:"Key track",velocity:"Velocity → filter",
about_vals:"About the values",hint_vals:"Envelope times are the ones the MPC shows (measured on the MPC: 0 ms to 30 s on an exponential curve); you can type them. Sustain goes 0–127 as on the MPC; the filter knobs 0–100. Everything applies to all keygroups of the selected instrument. Presets are starting points: pick one, adjust it and save it with your own name. The drawing shows the shape, not the real proportions. Use “Template values” to go back to the template's settings.",
sec_out:"Program",lbl_name:"Name",lbl_output:"Save in",chk_hardlink:"Link samples instead of copying (saves space)",
lbl_template:"Template",btn_tpl:"Use another .xpm…",btn_builtin:"Built-in",tpl_builtin:"Built-in (MPC 3.9)",
hint_out:"Same layout the MPC uses: “Name.xpm” goes in the folder you choose, its samples in “Name_[ProgramData]” next to it and the preview in “[Previews]”. Copy them together to your MPC. The preview plays the sample closest to C3 (loudest layer). The names are the ones in the instrument list.",
btn_go:"Create keygroup",btn_reveal:"Show in folder",generating:"Creating…",done:"✔ {0} — {1} keygroups, {2} samples",
need_samples:"Scan a folder with samples first",need_out:"Choose where to save it",need_name:"Type a name",
w_no_note:"No root note, left out: {0}",w_no_vel:"No velocity in the name, used as 127: {0}",w_duplicate:"Same note and velocity as another sample, left out: {0}",
e_no_samples:"No usable samples (each one needs a root note).",e_too_many_layers:"{0} different velocities: the MPC allows 8 layers at most.",e_too_many_keygroups:"{0} different notes: the MPC allows 128 keygroups at most.",
ask_path:"Full path:",scanning:"Scanning…",err:"Error: {0}",tpl_bad:"That file is not an MPC 3.x keygroup program"},
es:{
chk_split:"Un programa por instrumento",hint_time:"Escribe un tiempo: 250 ms, 1,5 s (un número solo son ms)",hint_sus:"0–127, como en la MPC",btn_ok:"Aceptar",btn_cancel:"Cancelar",chk_preview:"Crear preescucha para el navegador de la MPC ([Previews]/Nombre.xpm.ogg)",lbl_pvsec:"Segundos",
w_preview_failed:"No se pudo crear la preescucha ({0})",cur_samples:"Samples de <b>{0}</b> — haz clic en un instrumento de la lista para ver sus samples, su mapa y su sonido.",
cur_sound:"Sonido de <b>{0}</b>",no_preset:"— Valores de la plantilla —",lbl_preset:"Preset",modified:"● modificado",btn_save_preset:"Guardar preset…",btn_ren_preset:"Renombrar…",btn_del_preset:"Borrar",
btn_apply_all:"Aplicar a todos los instrumentos",btn_restore:"Restaurar presets integrados",ask_preset:"Nombre del preset (si ya existe, se sobrescribe):",ask_rename:"Nuevo nombre para «{0}»:",
confirm_del:"¿Borrar el preset «{0}»?",confirm_restore:"¿Recuperar los presets integrados (Pad, Lead, Pluck, Keys, Bass, Strings) con sus valores originales? Tus otros presets se conservan.",
applied_all:"Sonido copiado a {0} instrumento(s)",inst_count:"{0} samples",st_ok:"{0} kg · {1} capa(s)",st_err:"⚠ revisar",n_inst:"{0} instrumentos",
btn_go_n:"Crear {0} programas",results:"{0} programa(s) creado(s) en {1}",
sec_samples:"Samples",lbl_folder:"Carpeta",btn_choose:"Elegir…",btn_scan:"Escanear",chk_recursive:"Incluir subcarpetas",
lbl_octave:"Nombres de nota",oct_c3:"C3 = 60 (MPC)",oct_c4:"C4 = 60",chk_numbers:"Aceptar números MIDI (_060_)",
th_file:"Archivo",th_note:"Nota raíz",th_vel:"Velocidad",th_src:"Leída de",th_loop:"Loop",no_loop:"—",chk_loops:"Usar los loops guardados en los samples",loop_tip:"Loop {0}–{1} s (de {2} s). El sample terminará al final del loop, como cuando lo carga la MPC.",th_use:"Usar",no_samples:"Elige una carpeta y pulsa Escanear.",
src_name:"nombre",src_file:"datos del archivo",src_none:"— no encontrada",src_edit:"editada",count:"{0} samples",
hint_names:"La nota raíz se lee del nombre (C2, F#3, Db4…) y, si no aparece, de la nota guardada dentro del WAV/AIFF. Las capas de velocidad salen de V127 / vel64 / v1 v2 v3 o pp p mp mf f ff. Puedes escribir encima de cualquier valor; deja la velocidad vacía para una sola capa.",
sec_map:"Keygroups",lbl_zones:"Nota raíz en su zona",z_center:"Centrada",z_up:"Abajo",z_down:"Arriba",chk_extend:"Estirar a todo el teclado",
lbl_vel:"Valores de velocidad",v_auto:"Automático",v_upper:"Límite superior",v_center:"Centro del rango",v_even:"Partes iguales",
summary:"{0} keygroups · {1} capa(s)",hint_map:"Cada columna es un keygroup y cada bloque una capa de velocidad (suave abajo, fuerte arriba). Haz clic en un bloque para oír su sample. La MPC admite hasta 8 capas por keygroup.",
sec_sound:"Envolventes y filtro",btn_reset:"Valores de la plantilla",amp_env:"Envolvente de amplitud",flt_env:"Envolvente del filtro",filter:"Filtro",
Attack:"Ataque",Hold:"Hold",Decay:"Decay",Sustain:"Sustain",Release:"Release",velsens:"Velocidad → volumen",blend:"Mezcla filtro 1 ↔ 2",f_serial:"Filtros en serie (por defecto: en paralelo)",
hint_blend:"Mezcla 0 = solo suena el filtro 1; 100 = solo el filtro 2 (la MPC trae 50, los dos a la vez). En serie el sonido pasa por el filtro 1 y luego por el 2.",
f_type:"Tipo",f_index:"Índice del tipo",f_other:"Otro (escribe el índice)…",cutoff:"Corte",resonance:"Resonancia",envAmount:"Cantidad de env.",keytrack:"Seguimiento de tecla",velocity:"Velocidad → filtro",
about_vals:"Sobre los valores",hint_vals:"Los tiempos de las envolventes son los que muestra la MPC (medidos en la MPC: de 0 ms a 30 s con una curva exponencial) y puedes escribirlos. El Sustain va de 0 a 127 como en la MPC; los controles del filtro, de 0 a 100. Todo se aplica a todos los keygroups del instrumento seleccionado. Los presets son puntos de partida: elige uno, ajústalo y guárdalo con tu propio nombre. El dibujo muestra la forma, no las proporciones reales. «Valores de la plantilla» vuelve a los ajustes de la plantilla.",
sec_out:"Programa",lbl_name:"Nombre",lbl_output:"Guardar en",chk_hardlink:"Enlazar samples en vez de copiar (ahorra espacio)",
lbl_template:"Plantilla",btn_tpl:"Usar otro .xpm…",btn_builtin:"Integrada",tpl_builtin:"Integrada (MPC 3.9)",
hint_out:"Igual que la MPC: «Nombre.xpm» va en la carpeta que elijas, sus samples en «Nombre_[ProgramData]», a su lado, y la preescucha en «[Previews]». Cópialos juntos a la MPC. La preescucha suena con el sample más cercano a C3 (la capa más fuerte). Los nombres son los de la lista de instrumentos.",
btn_go:"Crear keygroup",btn_reveal:"Mostrar en la carpeta",generating:"Creando…",done:"✔ {0} — {1} keygroups, {2} samples",
need_samples:"Primero escanea una carpeta con samples",need_out:"Elige dónde guardarlo",need_name:"Escribe un nombre",
w_no_note:"Sin nota raíz, se queda fuera: {0}",w_no_vel:"Sin velocidad en el nombre, se usa 127: {0}",w_duplicate:"Misma nota y velocidad que otro sample, se queda fuera: {0}",
e_no_samples:"No hay samples utilizables (cada uno necesita una nota raíz).",e_too_many_layers:"{0} velocidades distintas: la MPC admite 8 capas como máximo.",e_too_many_keygroups:"{0} notas distintas: la MPC admite 128 keygroups como máximo.",
ask_path:"Ruta completa:",scanning:"Escaneando…",err:"Error: {0}",tpl_bad:"Ese archivo no es un programa keygroup de MPC 3.x"}};
let LANG=(navigator.language||"en").toLowerCase().startsWith("es")?"es":"en";
const t=(k,...a)=>{let s=(I18N[LANG]&&I18N[LANG][k])??I18N.en[k]??k;a.forEach((v,i)=>s=s.replaceAll("{"+i+"}",v));return s};
const $=id=>document.getElementById(id);
const NAMES=["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"];
const OFF={c3:2,c4:1};
const ENV=["Attack","Hold","Decay","Sustain","Release"];
const FILT=["cutoff","resonance","envAmount","keytrack","velocity"];
let S={folder:"",recursive:false,octave:"c3",numbers:false,split:true,zones:"center",extend:true,vel:"auto",
 output:"",hardlink:false,loops:true,preview:true,previewSeconds:6,template:"",sound:null,lang:null};
let DEFAULTS=null,FILTERS=[],SAMPLES=[],MAP=null,LASTXPM="",PRESETS={},BUILTIN={};
let INSTR=[],CUR=-1,SND=null;   /* instruments of the scan; SND = sound being edited */
const clone=o=>JSON.parse(JSON.stringify(o));
function merge(base,over){const r=clone(base);for(const k in over||{}){
 if(over[k]&&typeof over[k]==="object"&&!Array.isArray(over[k]))r[k]=Object.assign(r[k]||{},clone(over[k]));else r[k]=over[k]}return r}
const presetSound=name=>merge(DEFAULTS,name&&PRESETS[name]?PRESETS[name]:{});
const eq=(a,b)=>JSON.stringify(a)===JSON.stringify(b);

const noteName=n=>n==null?"":NAMES[n%12]+(Math.floor(n/12)-OFF[S.octave]);
function parseNote(txt){txt=String(txt).trim();if(txt==="")return null;
 if(/^\d{1,3}$/.test(txt)){const n=+txt;return n<=127?n:undefined}
 const m=txt.match(/^([A-Ga-g])(#|b|s|♯|♭)?(-?\d)$/);if(!m)return undefined;
 let pc={C:0,D:2,E:4,F:5,G:7,A:9,B:11}[m[1].toUpperCase()];
 if(["#","s","♯"].includes(m[2]))pc++;else if(["b","♭"].includes(m[2]))pc--;
 const n=(+m[3]+OFF[S.octave])*12+pc;return n>=0&&n<=127?n:undefined}

async function call(path,body){const r=await fetch(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body||{})});
 const j=await r.json();if(!r.ok)throw new Error(j.error||r.status);return j}
let saveT=null;function save(){clearTimeout(saveT);saveT=setTimeout(()=>call("/api/save",S).catch(()=>{}),400)}

function applyLang(){document.documentElement.lang=LANG;
 document.querySelectorAll("[data-t]").forEach(e=>e.textContent=t(e.dataset.t));
 document.querySelectorAll(".lang button").forEach(b=>b.classList.toggle("on",b.dataset.lang===LANG));
 buildSliders();fillFilterTypes();renderRows();renderMap();tplLabel();renderInst();renderPresetBar()}

/* ---------- sliders ---------- */
/* MPC envelope curve (measured): time = 30000^(value/100) ms; sustain shown 0-127 */
const LN30K=Math.log(30000);
const msOf=v=>v<=0?0:Math.exp(Math.min(v,100)/100*LN30K);
const posOf=ms=>ms<1?0:Math.min(100,100*Math.log(ms)/LN30K);
const dec=(x,d)=>x.toFixed(d).replace(".",LANG==="es"?",":".");
function fmtTime(v){const ms=msOf(v);if(v<=0)return"0 ms";if(ms<1000)return dec(ms,1)+" ms";return dec(ms/1000,ms<10000?2:1)+" s"}
function parseTime(txt){const m=String(txt).trim().toLowerCase().replace(",",".").match(/^(\d*\.?\d+)\s*(ms|s)?$/);
 if(!m)return null;return posOf(m[2]==="s"?+m[1]*1000:+m[1])}
const FMT={plain:{show:v=>String(Math.round(v*10)/10),parse:x=>{const n=parseFloat(String(x).replace(",","."));return isNaN(n)?null:n}},
 time:{show:fmtTime,parse:parseTime},
 sus:{show:v=>String(Math.round(v*1.27)),parse:x=>{const n=parseFloat(String(x).replace(",","."));return isNaN(n)?null:n/1.27}}};
function slider(parent,id,label,get,set,fmt){fmt=fmt||FMT.plain;
 const d=document.createElement("div");d.className="sl";
 d.innerHTML=`<label>${label}</label><input type="range" min="0" max="100" step="0.1"><input type="text" class="val" spellcheck="false">`;
 const [r,n]=d.querySelectorAll("input");r.value=get();n.value=fmt.show(get());
 if(fmt===FMT.time)n.title=t("hint_time");if(fmt===FMT.sus)n.title=t("hint_sus");
 const upd=v=>{v=Math.max(0,Math.min(100,+v||0));v=Math.round(v*100)/100;set(v);r.value=v;n.value=fmt.show(v);drawEnvs();soundChanged()};
 r.oninput=()=>upd(r.value);n.onchange=()=>{const v=fmt.parse(n.value);if(v===null){n.value=fmt.show(get());return}upd(v)};
 n.onkeydown=e=>{if(e.key==="Enter")n.blur()};parent.appendChild(d)}
function buildSliders(){if(!SND)return;
 for(const [env,box] of [["amp","ampSl"],["fenv","fenvSl"]]){const p=$(box);p.innerHTML="";
  ENV.forEach(k=>slider(p,env+k,t(k),()=>SND[env][k],v=>SND[env][k]=v,k==="Sustain"?FMT.sus:FMT.time))}
 const f=$("filtSl");f.innerHTML="";FILT.forEach(k=>slider(f,"f"+k,t(k),()=>SND.filter[k],v=>SND.filter[k]=v));
 const bl=$("blendSl");bl.innerHTML="";slider(bl,"blend",t("blend"),()=>SND.blend,v=>SND.blend=v);
 $("serial").checked=!!SND.serial;
 $("velSensR").value=$("velSensN").value=SND.velSens;drawEnvs();soundChanged()}
function velSens(v){v=Math.max(0,Math.min(100,+v||0));SND.velSens=v;$("velSensR").value=$("velSensN").value=v;soundChanged()}
$("velSensR").oninput=e=>velSens(e.target.value);$("velSensN").onchange=e=>velSens(e.target.value);
function fillFilterTypes(){const s=$("ftype");if(!SND)return;s.innerHTML="";
 FILTERS.forEach(([i,en,es])=>{const o=document.createElement("option");o.value=i;o.textContent=(LANG==="es"?es:en);s.appendChild(o)});
 const o=document.createElement("option");o.value="other";o.textContent=t("f_other");s.appendChild(o);
 const known=FILTERS.some(f=>f[0]===SND.filter.type);s.value=known?SND.filter.type:"other";
 $("fcustomRow").style.display=known?"none":"";$("fcustom").value=SND.filter.type}
$("ftype").onchange=e=>{if(e.target.value==="other"){$("fcustomRow").style.display="";$("fcustom").focus()}
 else{$("fcustomRow").style.display="none";SND.filter.type=+e.target.value;soundChanged()}};
$("fcustom").onchange=e=>{SND.filter.type=Math.max(0,parseInt(e.target.value)||0);soundChanged()};
function drawEnv(svg,e){const W=400,H=90,pad=6,seg=W/5-6;
 const x1=pad+e.Attack/100*seg,x2=x1+e.Hold/100*seg,x3=x2+e.Decay/100*seg+2,x4=x3+seg*.9,x5=x4+e.Release/100*seg+2;
 const top=pad,bot=H-pad,sy=bot-(bot-top)*e.Sustain/100;
 const d=`M${pad},${bot} L${x1},${top} L${x2},${top} L${x3},${sy} L${x4},${sy} L${x5},${bot}`;
 svg.innerHTML=`<path d="${d} Z" fill="rgba(255,90,54,.18)"/><path d="${d}" fill="none" stroke="#ff5a36" stroke-width="2" vector-effect="non-scaling-stroke"/>`}
function drawEnvs(){if(!SND)return;drawEnv($("ampSvg"),SND.amp);drawEnv($("fenvSvg"),SND.fenv)}
$("serial").onchange=e=>{SND.serial=e.target.checked;soundChanged()};
function setSound(o){/* replace the sound being edited, keeping the same object */
 for(const k of Object.keys(SND))delete SND[k];Object.assign(SND,clone(o));buildSliders();fillFilterTypes()}
$("resetSound").onclick=()=>{const i=INSTR[CUR];if(i)i.preset=null;setSound(DEFAULTS);renderInst();renderPresetBar()};

/* ---------- presets ---------- */
function soundChanged(){if(INSTR.length<=1){S.sound=SND;S.preset=INSTR[CUR]?INSTR[CUR].preset:S.preset}save();renderPresetBar();if(INSTR[CUR])renderInst()}
function presetOptions(sel,value){sel.innerHTML="";const o=document.createElement("option");o.value="";o.textContent=t("no_preset");sel.appendChild(o);
 Object.keys(PRESETS).sort((a,b)=>a.localeCompare(b)).forEach(n=>{const o=document.createElement("option");o.value=n;o.textContent=n;sel.appendChild(o)});sel.value=value||""}
function renderPresetBar(){const i=INSTR[CUR];const name=i?i.preset:S.preset;presetOptions($("presetSel"),name);
 const base=presetSound(name);$("presetMod").textContent=SND&&!eq(merge(DEFAULTS,SND),base)?t("modified"):"";
 const has=!!(name&&PRESETS[name]);$("delPreset").disabled=!has;$("renPreset").disabled=!has;
 $("applyAll").disabled=INSTR.length<2;
 $("curSound").innerHTML=i?t("cur_sound",esc(i.name)):""}
function usePreset(name){const i=INSTR[CUR];if(i)i.preset=name||null;else S.preset=name||null;setSound(presetSound(name));renderInst();renderPresetBar();save()}
$("presetSel").onchange=e=>usePreset(e.target.value);
function savePresets(){call("/api/presets",{presets:PRESETS}).catch(e=>tell(t("err",e.message)))}
$("savePreset").onclick=async()=>{const i=INSTR[CUR];const cur=i?i.preset:S.preset;let n=await askText(t("ask_preset"),cur||"");
 if(!n||!(n=n.trim()))return;PRESETS[n]=clone(SND);savePresets();if(i)i.preset=n;else S.preset=n;renderInst();renderPresetBar();save()};
$("renPreset").onclick=async()=>{const i=INSTR[CUR];const old=i?i.preset:S.preset;if(!old||!PRESETS[old])return;
 let n=await askText(t("ask_rename",old),old);if(!n||!(n=n.trim())||n===old)return;PRESETS[n]=PRESETS[old];delete PRESETS[old];
 INSTR.forEach(x=>{if(x.preset===old)x.preset=n});if(S.preset===old)S.preset=n;savePresets();renderInst();renderPresetBar();save()};
$("delPreset").onclick=async()=>{const i=INSTR[CUR];const old=i?i.preset:S.preset;if(!old||!PRESETS[old]||!(await askYes(t("confirm_del",old))))return;
 delete PRESETS[old];INSTR.forEach(x=>{if(x.preset===old)x.preset=null});if(S.preset===old)S.preset=null;savePresets();renderInst();renderPresetBar();save()};
$("restorePresets").onclick=async()=>{if(!(await askYes(t("confirm_restore"))))return;Object.assign(PRESETS,clone(BUILTIN));savePresets();renderInst();renderPresetBar()};
$("applyAll").onclick=()=>{const i=INSTR[CUR];if(!i)return;let n=0;INSTR.forEach(x=>{if(x!==i){x.sound=clone(SND);x.preset=i.preset;n++}});
 renderInst();renderPresetBar();$("status").textContent=t("applied_all",n)};
/* in-page dialogs: the desktop window (WKWebView / WebView2) has no prompt() or confirm() */
function dialog(msg,value,input){return new Promise(res=>{const d=$("dlg"),i=$("dlgIn");$("dlgMsg").textContent=msg;
 i.style.display=input?"":"none";i.value=value||"";$("dlgNo").style.display=input===null?"none":"";d.hidden=false;(input?i:$("dlgOk")).focus();
 const done=v=>{d.hidden=true;$("dlgOk").onclick=$("dlgNo").onclick=i.onkeydown=null;res(v)};
 $("dlgOk").onclick=()=>done(input?i.value:true);$("dlgNo").onclick=()=>done(input?null:false);
 i.onkeydown=e=>{if(e.key==="Enter")done(i.value);if(e.key==="Escape")done(null)}})}
const askText=(m,v)=>dialog(m,v,true),askYes=m=>dialog(m,"",false),tell=m=>dialog(m,"",null);
const esc=x=>String(x).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

/* ---------- samples ---------- */
function bindOpt(id,key,ev="change",after){const e=$(id);const v=S[key];
 if(e.type==="checkbox")e.checked=!!v;else e.value=v??"";
 e.addEventListener(ev,()=>{S[key]=e.type==="checkbox"?e.checked:e.value;save();after&&after()})}
async function choose(kind,target,after){try{const r=await call("/api/pick",{kind,prompt:""});
 let p=r.path;if(r.unsupported)p=await askText(t("ask_path"),S[target]||"");
 if(p){if(p.length>1)p=p.replace(/[\\/]$/,"");S[target]=p;$(target).value=p;save();after&&after(p)}}
 catch(e){tell(t("err",e.message))}}
async function scan(){if(!S.folder)return;$("count").textContent=t("scanning");
 try{const r=await call("/api/scan",{folder:S.folder,recursive:S.recursive,octave:S.octave,numbers:S.numbers,split:S.split,presets:PRESETS});
  INSTR=r.groups.map(g=>({name:g.name,on:true,samples:g.samples,preset:g.preset,sound:presetSound(g.preset),status:null}));
  if(INSTR.length===1&&!INSTR[0].preset&&S.sound){INSTR[0].sound=merge(DEFAULTS,S.sound);INSTR[0].preset=S.preset||null}
  await Promise.all(INSTR.map(statusOf));selectInst(INSTR.length?0:-1)}
 catch(e){INSTR=[];selectInst(-1);$("count").textContent=t("err",e.message)}}
async function statusOf(i){try{const m=await call("/api/map",{samples:i.samples,zones:S.zones,extend:S.extend,vel:S.vel});i.status=m}catch(e){i.status={keygroups:[],errors:[["err",e.message]],warnings:[]}}}
function selectInst(k){CUR=k;const i=INSTR[k];SAMPLES=i?i.samples:[];SND=i?i.sound:(S.sound=merge(DEFAULTS,S.sound||{}));
 buildSliders();fillFilterTypes();renderRows();renderInst();renderPresetBar();MAP=i?i.status:null;renderMap();refreshMap()}
function renderInst(){const box=$("insts");box.innerHTML="";const n=INSTR.length;
 $("count").textContent=n?(n>1?t("n_inst",n)+" · ":"")+t("count",INSTR.reduce((a,i)=>a+i.samples.length,0)):"";
 $("curSamples").innerHTML=INSTR[CUR]&&n>1?t("cur_samples",esc(INSTR[CUR].name)):"";
 INSTR.forEach((i,k)=>{const d=document.createElement("div");d.className="inst"+(k===CUR?" cur":"")+(i.on?"":" off");
  const st=i.status;let stx="",cls="";if(st){if(st.errors.length){stx=t("st_err");cls="e"}else{const nl=Math.max(...st.keygroups.map(x=>x.layers.length));stx=t("st_ok",st.keygroups.length,nl);cls="ok"}}
  d.innerHTML=`<input type="checkbox" ${i.on?"checked":""}><input type="text" spellcheck="false"><span class="cnt">${t("inst_count",i.samples.length)}</span><select></select><span class="st ${cls}">${stx}</span>`;
  const [cb,nm]=d.querySelectorAll("input");const sel=d.querySelector("select");nm.value=i.name;
  presetOptions(sel,i.preset);const mod=!eq(merge(DEFAULTS,i.sound),presetSound(i.preset));if(mod)sel.options[sel.selectedIndex].textContent+=" ●";
  cb.onclick=e=>e.stopPropagation();cb.onchange=()=>{i.on=cb.checked;d.classList.toggle("off",!i.on);goLabel()};
  nm.onclick=e=>e.stopPropagation();nm.oninput=()=>{i.name=nm.value;if(k===CUR){renderPresetBar();$("curSamples").innerHTML=n>1?t("cur_samples",esc(i.name)):""}};
  sel.onclick=e=>e.stopPropagation();sel.onchange=()=>{i.preset=sel.value||null;i.sound=presetSound(i.preset);if(k===CUR){SND=i.sound;buildSliders();fillFilterTypes();renderPresetBar()}renderInst()};
  d.onclick=()=>{if(k!==CUR)selectInst(k)};box.appendChild(d)});
 box.style.display=n?"":"none";goLabel()}
function goLabel(){const n=INSTR.filter(i=>i.on).length;$("go").textContent=n>1?t("btn_go_n",n):t("btn_go")}
function renderRows(){const tb=$("rows");
 if(!SAMPLES.length){tb.innerHTML=`<tr><td colspan="7" class="empty">${t("no_samples")}</td></tr>`;return}
 tb.innerHTML="";
 SAMPLES.forEach((s,i)=>{const tr=document.createElement("tr");
  tr.className=(s.on?"":"off")+(s.note==null?" bad":"");
  const src=s.source==="name"?t("src_name"):s.source==="file"?t("src_file"):s.source==="edit"?t("src_edit"):t("src_none");
  tr.innerHTML=`<td><button class="play" title="▶">▶</button></td><td class="nm"></td>
  <td><input type="text" class="note" value="${noteName(s.note)}"></td>
  <td><input type="text" class="vel" value="${s.vel??""}" placeholder="—"></td><td class="src">${src}</td><td class="src lp"></td>
  <td><input type="checkbox" ${s.on?"checked":""}></td>`;
  tr.querySelector(".nm").textContent=s.file;
  const lp=tr.querySelector(".lp");
  if(s.loop_start!=null&&s.rate){const f=x=>(x/s.rate).toFixed(2);lp.textContent="↻ "+f(s.loop_start)+"–"+f(s.loop_end||s.frames)+" s";
   lp.title=t("loop_tip",f(s.loop_start),f(s.loop_end||s.frames),f(s.frames));lp.style.color="var(--ok)"}else lp.textContent=t("no_loop");
  tr.querySelector(".play").onclick=()=>play(s.path);
  const ni=tr.querySelector(".note");ni.onchange=()=>{const n=parseNote(ni.value);
   if(n===undefined){ni.value=noteName(s.note);return}s.note=n;s.source="edit";renderRows();refreshMap()};
  const vi=tr.querySelector(".vel");vi.onchange=()=>{const v=vi.value.trim();
   if(v===""){s.vel=null}else if(/^\d{1,3}$/.test(v)&&+v<=127){s.vel=+v}else{vi.value=s.vel??"";return}refreshMap()};
  tr.querySelector("input[type=checkbox]").onchange=e=>{s.on=e.target.checked;tr.classList.toggle("off",!s.on);refreshMap()};
  tb.appendChild(tr)})}
function play(p){const a=$("player");a.src="/audio?p="+encodeURIComponent(p);a.play().catch(()=>{})}

/* ---------- map ---------- */
let mapT=null;function refreshMap(all){clearTimeout(mapT);mapT=setTimeout(async()=>{
 if(all)await Promise.all(INSTR.map(statusOf));
 const i=INSTR[CUR];if(!i){MAP=null;renderMap();return}
 await statusOf(i);MAP=i.status;renderMap();renderInst()},120)}
function isBlack(n){return [1,3,6,8,10].includes(n%12)}
function renderMap(){const svg=$("map");const W=1280,KW=W/128,TOP=8,MH=170,KY=TOP+MH+10,KH=50;
 let h="";
 // keyboard
 for(let n=0;n<128;n++)if(!isBlack(n))h+=`<rect x="${n*KW}" y="${KY}" width="${KW}" height="${KH}" fill="#e9e9e6" stroke="#9a9a96" stroke-width=".5"/>`;
 for(let n=0;n<128;n++)if(isBlack(n))h+=`<rect x="${n*KW}" y="${KY}" width="${KW}" height="${KH*.62}" fill="#2a2c31"/>`;
 for(let n=0;n<128;n+=12)h+=`<text x="${n*KW+1}" y="${KY+KH-4}" font-size="9" fill="#555">${noteName(n)}</text>`;
 h+=`<rect x="0" y="${TOP}" width="${W}" height="${MH}" fill="#17191d" rx="4"/>`;
 const kgs=MAP?MAP.keygroups:[];const hues=[14,32,48,160,190,210,265,320];
 kgs.forEach((k,ki)=>{const x=k.low*KW,w=(k.high-k.low+1)*KW;
  k.layers.forEach((l,li)=>{const y0=TOP+MH-(l.vend+1)/128*MH,y1=TOP+MH-l.vstart/128*MH;
   const hue=hues[li%hues.length],light=ki%2?46:54;const name=l.path.split(/[\\/]/).pop();
   h+=`<g class="zone" data-p="${encodeURIComponent(l.path)}"><rect x="${x+.6}" y="${y0+.6}" width="${w-1.2}" height="${y1-y0-1.2}" rx="2" fill="hsl(${hue} 85% ${light}%)" fill-opacity="${l.root===k.root?.9:.5}"><title>${noteName(k.low)}–${noteName(k.high)} · ${t("th_note")}: ${noteName(l.root)} · vel ${l.vstart}–${l.vend}\n${name}</title></rect></g>`});
  h+=`<rect x="${k.root*KW}" y="${KY}" width="${KW}" height="5" fill="#ff5a36"/>`;
  if(w>=26)h+=`<text x="${x+w/2}" y="${TOP+MH-5}" font-size="10" fill="#111" text-anchor="middle" pointer-events="none" font-weight="600">${noteName(k.root)}</text>`});
 if(!kgs.length)h+=`<text x="${W/2}" y="${TOP+MH/2}" fill="#777" text-anchor="middle" font-size="14">${t("no_samples")}</text>`;
 svg.innerHTML=h;svg.querySelectorAll(".zone").forEach(g=>g.onclick=()=>play(decodeURIComponent(g.dataset.p)));
 const nl=kgs.length?Math.max(...kgs.map(k=>k.layers.length)):0;
 $("summary").textContent=kgs.length?t("summary",kgs.length,nl):"";$("summary").classList.toggle("ok",kgs.length>0);
 const m=$("mapmsgs");m.innerHTML="";if(!MAP)return;
 MAP.errors.forEach(([k,a])=>{const d=document.createElement("div");d.className="e";d.textContent=I18N.en["e_"+k]?t("e_"+k,a):t("err",a);m.appendChild(d)});
 MAP.warnings.forEach(([k,a])=>{const d=document.createElement("div");d.className="w";d.textContent="⚠ "+t("w_"+k,a);m.appendChild(d)})}
function seg(id,key){const b=$(id).querySelectorAll("button");const upd=()=>b.forEach(x=>x.classList.toggle("on",x.dataset.v===S[key]));
 b.forEach(x=>x.onclick=()=>{S[key]=x.dataset.v;upd();save();refreshMap(true)});upd()}

/* ---------- output ---------- */
function tplLabel(){$("tplname").textContent=S.template?S.template.split(/[\\/]/).pop():t("tpl_builtin")}
async function setTemplate(p){try{const r=await call("/api/template",{path:p||""});S.template=p||"";DEFAULTS=r.defaults;
 INSTR.forEach(i=>i.sound=presetSound(i.preset));if(INSTR[CUR])SND=INSTR[CUR].sound;else{S.sound=presetSound(S.preset);SND=S.sound}
 buildSliders();fillFilterTypes();renderInst();renderPresetBar();tplLabel();save()}catch(e){tell(t("tpl_bad")+"\n"+e.message)}}
$("pickTpl").onclick=async()=>{const r=await call("/api/pick",{kind:"file"});let p=r.path;if(r.unsupported)p=await askText(t("ask_path"),"");if(p)setTemplate(p)};
$("builtinTpl").onclick=()=>setTemplate("");
$("go").onclick=async()=>{const st=$("status"),gm=$("genmsgs");gm.innerHTML="";$("reveal").style.display="none";
 const progs=INSTR.filter(i=>i.on).map(i=>({name:i.name.trim(),samples:i.samples,sound:i.sound}));
 if(!progs.length){st.textContent=t("need_samples");return}if(progs.some(p=>!p.name)){st.textContent=t("need_name");return}
 if(!S.output){st.textContent=t("need_out");return}
 $("go").disabled=true;st.textContent=t("generating");
 try{const r=await call("/api/generate",{programs:progs,output:S.output,zones:S.zones,extend:S.extend,vel:S.vel,
  template:S.template,hardlink:S.hardlink,loops:S.loops,preview:S.preview,previewSeconds:+S.previewSeconds||6});
  const ok=r.results.filter(x=>x.xpm);LASTXPM=ok.length?ok[0].xpm:"";st.innerHTML="";
  const d=document.createElement("span");d.style.color=ok.length?"var(--ok)":"var(--err)";
  d.textContent=ok.length===1&&r.results.length===1?t("done",ok[0].xpm,ok[0].keygroups,ok[0].samples):"✔ "+t("results",ok.length,S.output);st.appendChild(d);
  if(ok.length)$("reveal").style.display="";
  r.results.forEach(x=>{const multi=r.results.length>1;
   if(x.error){const e=document.createElement("div");e.className="e";e.textContent=(multi?x.name+": ":"")+t("err",x.error);gm.appendChild(e);return}
   if(multi){const o=document.createElement("div");o.className="o";o.textContent=t("done",x.name+".xpm",x.keygroups,x.samples);gm.appendChild(o)}
   x.warnings.forEach(([k,a])=>{const w=document.createElement("div");w.className="w";w.textContent="⚠ "+(multi?x.name+": ":"")+t("w_"+k,a);gm.appendChild(w)})})}
 catch(e){st.textContent=t("err",e.message)}finally{$("go").disabled=false;save()}};
$("reveal").onclick=()=>LASTXPM&&call("/api/reveal",{path:LASTXPM});

/* ---------- start ---------- */
(async()=>{const r=await call("/api/init");$("ver").textContent="v"+r.version;FILTERS=r.filters;DEFAULTS=r.defaults;
 PRESETS=r.presets||{};BUILTIN=r.builtin_presets||{};
 S=Object.assign(S,r.settings||{});if(S.lang)LANG=S.lang;delete S.name;
 S.sound=merge(DEFAULTS,S.sound&&S.sound.amp?S.sound:{});SND=S.sound;
 bindOpt("folder","folder","change",scan);bindOpt("recursive","recursive","change",scan);
 bindOpt("octave","octave","change",scan);bindOpt("numbers","numbers","change",scan);bindOpt("split","split","change",scan);
 bindOpt("extend","extend","change",()=>refreshMap(true));bindOpt("velmode","vel","change",()=>refreshMap(true));
 bindOpt("output","output","change");bindOpt("hardlink","hardlink");bindOpt("loops","loops");bindOpt("preview","preview");bindOpt("previewSeconds","previewSeconds");
 seg("zones","zones");
 $("pickFolder").onclick=()=>choose("folder","folder",scan);$("scan").onclick=scan;
 $("pickOut").onclick=()=>choose("folder","output");
 document.querySelectorAll(".lang button").forEach(b=>b.onclick=()=>{LANG=b.dataset.lang;S.lang=LANG;save();applyLang()});
 applyLang();selectInst(-1);if(S.folder)scan();
 setInterval(()=>call("/api/ping").catch(()=>{}),2000);call("/api/ping").catch(()=>{})})();
</script></body></html>"""

if __name__ == "__main__":
    main()
