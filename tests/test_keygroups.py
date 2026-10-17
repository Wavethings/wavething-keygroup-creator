import copy
import json
import math
import struct
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import mpc_keygroup_creator as kc  # noqa: E402
import ogg_preview as op  # noqa: E402


def make_wav(path, frames=1000, unity=None, loop=None):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(b"".join(struct.pack("<h", int(1000 * math.sin(i / 5))) for i in range(frames)))
    if unity is not None:
        smpl = struct.pack("<9I", 0, 0, 22675, unity, 0, 0, 0, 1 if loop else 0, 0)
        if loop:
            smpl += struct.pack("<6I", 0, 0, loop, frames - 1, 0, 0)
        data = path.read_bytes() + b"smpl" + struct.pack("<I", len(smpl)) + smpl
        data = data[:4] + struct.pack("<I", len(data) - 8) + data[8:]
        path.write_bytes(data)


def make_aiff(path, frames=1000, base=60, loop=(300, 800)):
    """AIFF laid out like Logic's Auto Sampler: COMM, MARK (Start/End/LoopStart/LoopEnd), INST, SSND."""
    def chunk(cid, body):
        return cid + struct.pack(">I", len(body)) + body + (b"\0" if len(body) % 2 else b"")
    comm = struct.pack(">hIh", 1, frames, 16) + bytes.fromhex("400EAC44000000000000")
    marks = [(1, 0, b"Start"), (2, frames, b"End"), (3, loop[0], b"LoopStart"), (4, loop[1], b"LoopEnd")]
    mark = struct.pack(">H", len(marks))
    for mid, pos, name in marks:
        ps = bytes([len(name)]) + name
        mark += struct.pack(">hI", mid, pos) + ps + (b"\0" if len(ps) % 2 else b"")
    inst = struct.pack(">bbbbbbhhhhhhh", base, 0, 0, 127, 0, 127, 0, 1, 3, 4, 0, 0, 0)
    ssnd = struct.pack(">II", 0, 0) + b"\0\0" * frames
    body = b"AIFF" + chunk(b"COMM", comm) + chunk(b"MARK", mark) + chunk(b"INST", inst) + chunk(b"SSND", ssnd)
    path.write_bytes(b"FORM" + struct.pack(">I", len(body)) + body)


class Names(unittest.TestCase):
    def test_mpc_autosampler(self):
        p = kc.parse_name("A Beautiful Dread Lead-F#2-V127-DKJN")
        self.assertEqual((p["note"], p["vel"]), (54, 127))

    def test_variants(self):
        self.assertEqual(kc.parse_name("Piano_C3_v64")["note"], 60)
        self.assertEqual(kc.parse_name("Piano Db2 vel 100")["vel"], 100)
        self.assertEqual(kc.parse_name("Piano Db2 vel 100")["note"], 49)
        self.assertEqual(kc.parse_name("Str_A-1_ff")["note"], 21)
        self.assertEqual(kc.parse_name("Str_A-1_ff")["vel"], 112)
        self.assertEqual(kc.parse_name("Bass C4", "c4")["note"], 60)
        self.assertIsNone(kc.parse_name("Pad Dread FDW9")["note"])
        self.assertIsNone(kc.parse_name("Juno 106 pad")["note"])
        self.assertEqual(kc.parse_name("Juno_060", numbers=True)["note"], 60)

    def test_note_roundtrip(self):
        for n in range(128):
            self.assertEqual(kc.parse_note(kc.note_name(n)), n)

    def test_guess_name(self):
        self.assertEqual(kc.guess_name([{"stem": "A Beautiful Dread Lead-C2-V127-FDW9"}]),
                         "A Beautiful Dread Lead")


class Instruments(unittest.TestCase):
    def test_instrument_name(self):
        self.assertEqual(kc.name_parts("Analog_Pad-C3-V127-E36P"), ("Analog_Pad", "E36P"))
        self.assertEqual(kc.instrument_name("Synth C2 Bender"), "Synth Bender")
        self.assertEqual(kc.instrument_name("C3 Piano v64"), "Piano")
        self.assertIsNone(kc.instrument_name("Noise"))

    def test_group(self):
        smp = [{"stem": n} for n in ("Pad-C3-V127-AAAA", "Pad-C4-V127-BBBB", "Lead_C3_v1",
                                     "Lead_C4_v2", "Pad noise", "Other")]
        g = dict(kc.group_samples(smp))
        self.assertEqual(sorted(g), ["Lead", "Other", "Pad"])
        self.assertEqual(len(g["Pad"]), 3)

    def test_group_name_after_note(self):
        # a folder exported with the instrument name on both sides of the note
        notes = ["C2", "F#2", "C3", "F#3", "C4", "F#4"]
        stems = [f"Chord {n} Prophetic" for n in notes] + [f"Perc {n} Prophetic" for n in notes]
        for inst in ("Bender", "Blazer", "Draw"):
            stems += [f"Synth {n} {inst}" for n in notes]
        stems += [f"Synth {n} Modul" for n in ("C4", "F#4")]
        g = dict(kc.group_samples([{"stem": x} for x in stems]))
        self.assertEqual(sorted(g), ["Chord Prophetic", "Perc Prophetic", "Synth Bender",
                                     "Synth Blazer", "Synth Draw", "Synth Modul"])
        self.assertEqual(len(g["Synth Draw"]), 6)
        self.assertEqual(len(g["Synth Modul"]), 2)

    def test_group_random_take_ids(self):
        # Logic's Auto Sampler: a different random id after the velocity in every file
        ids = ["FDW9", "DKJN", "DA7T", "UNOY"]
        stems = [f"Dread Lead-{n}-V127-{i}" for n, i in zip(["C2", "F#2", "C3", "F#3"], ids)]
        self.assertEqual([n for n, _ in kc.group_samples([{"stem": x} for x in stems])], ["Dread Lead"])
        self.assertEqual([n for n, _ in kc.group_samples([{"stem": "Analog_Pad-C3-V127-E36P"}])],
                         ["Analog_Pad"])

    def test_unique_names(self):
        self.assertEqual(kc.unique_names(["Pad", "pad", "A/B"]), ["Pad", "pad (2)", "A_B"])

    def test_presets(self):
        self.assertEqual(kc.guess_preset("A Beautiful Dread Lead"), "Lead")
        self.assertEqual(kc.guess_preset("WarmPad"), "Pad")
        self.assertEqual(kc.guess_preset("Grand Piano"), "Keys")
        self.assertIsNone(kc.guess_preset("Thing"))
        self.assertEqual(kc.guess_preset("My Vox", {"Vox": {}}), "Vox")
        h, doc = kc.load_template()
        for name, snd in kc.BUILTIN_PRESETS.items():
            ss = copy.deepcopy(doc["data"]["drum"]["instruments"][0]["synthSection"])
            kc.apply_sound(ss, snd)
            self.assertAlmostEqual(ss["ampEnvelope"]["Attack"]["value0"], snd["amp"]["Attack"] / 100)
            self.assertEqual(ss["filterBlend"], 0.0)


def ogg_pages(data):
    """Parse Ogg pages, checking capture pattern and CRC. Returns [(flags, granule, body)]."""
    pages, pos = [], 0
    while pos < len(data):
        assert data[pos:pos + 4] == b"OggS"
        flags, gran = data[pos + 5], struct.unpack_from("<q", data, pos + 6)[0]
        nseg = data[pos + 26]
        lacing = data[pos + 27:pos + 27 + nseg]
        size = 27 + nseg + sum(lacing)
        page = bytearray(data[pos:pos + size])
        crc = struct.unpack_from("<I", page, 22)[0]
        page[22:26] = b"\0\0\0\0"
        assert op._crc(page) == crc, "bad CRC"
        pages.append((flags, gran, bytes(page[27 + nseg:])))
        pos += size
    return pages


class Previews(unittest.TestCase):
    def test_pick_sample(self):
        kg = lambda r, lays: {"root": r, "layers": [{"root": r, "vend": v, "sample": {"path": f"{r}-{v}"}}
                                                    for v in lays]}
        self.assertEqual(kc.preview_sample([kg(48, [127]), kg(62, [63, 127]), kg(72, [127])])["path"], "62-127")
        self.assertEqual(kc.preview_sample([kg(57, [127]), kg(63, [127])])["path"], "57-127")

    def test_read_formats(self):
        with tempfile.TemporaryDirectory() as d:
            w = Path(d) / "a.wav"
            make_wav(w, 300)
            rate, ch = op.read_audio(w)
            self.assertEqual((rate, len(ch), len(ch[0])), (44100, 1, 300))
            a = Path(d) / "a.aif"
            make_aiff(a, 200)
            rate, ch = op.read_audio(a)
            self.assertEqual((rate, len(ch), len(ch[0])), (44100, 1, 200))

    def test_ogg_stream(self):
        rate = 22050
        x = [0.3 * math.sin(2 * math.pi * 330 * i / rate) for i in range(rate)]
        data = op.encode_ogg([x, x], rate)
        pages = ogg_pages(data)
        self.assertEqual(pages[0][0] & 2, 2)                  # BOS
        self.assertTrue(pages[0][2].startswith(b"\x01vorbis"))
        self.assertEqual(pages[-1][0] & 4, 4)                 # EOS
        self.assertEqual(pages[-1][1], rate)                  # exact length
        self.assertEqual(pages[0][2][11], 2)                  # channels

    def test_generate_writes_preview(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "src"
            src.mkdir()
            for n in ("C2", "C3", "C4"):
                make_wav(src / f"Keys-{n}-V127.wav", 3000)
            xpm, _, w = kc.generate(kc.scan_folder(src), "Keys", Path(d) / "out", log=lambda m: None)
            pv = Path(d) / "out" / "[Previews]" / "Keys.xpm.ogg"
            self.assertTrue(pv.is_file(), w)
            self.assertTrue(pv.read_bytes().startswith(b"OggS"))
            xpm, _, w = kc.generate(kc.scan_folder(src), "Keys2", Path(d) / "out", preview=False,
                                    log=lambda m: None)
            self.assertFalse((Path(d) / "out" / "[Previews]" / "Keys2.xpm.ogg").exists())


class Mapping(unittest.TestCase):
    def test_mpc_zones(self):
        roots = [48, 54, 60, 66, 72, 78, 84, 90, 95]
        z = kc.zone_bounds(roots, "center", extend=False)
        self.assertEqual(z[0], (48, 50))
        self.assertEqual(z[1], (51, 56))
        self.assertEqual(z[-1], (93, 95))
        self.assertEqual(kc.zone_bounds(roots)[0][0], 0)
        self.assertEqual(kc.zone_bounds(roots)[-1][1], 127)
        self.assertEqual(kc.zone_bounds([48, 60], "up", False), [(48, 59), (60, 60)])
        self.assertEqual(kc.zone_bounds([48, 60], "down", False), [(48, 48), (49, 60)])

    def test_velocity(self):
        self.assertEqual(kc.velocity_ranges([40, 90, 127]), [(0, 40), (41, 90), (91, 127)])
        self.assertEqual(kc.velocity_ranges([1, 2, 3, 4]), [(0, 31), (32, 63), (64, 95), (96, 127)])
        self.assertEqual(kc.velocity_ranges([40, 100], "center"), [(0, 70), (71, 127)])
        self.assertEqual(kc.velocity_ranges([64]), [(0, 127)])

    def test_borrow_and_warnings(self):
        s = lambda p, n, v: {"path": p, "note": n, "vel": v, "on": True}
        kgs, w, e = kc.build_map([s("a", 60, 40), s("b", 60, 127), s("c", 72, 127),
                                  s("d", None, None), s("e", 72, 127)])
        self.assertFalse(e)
        self.assertEqual([x["sample"]["path"] for x in kgs[1]["layers"]], ["a", "c"])
        self.assertIn(("no_note", "d"), w)
        self.assertIn(("duplicate", "e"), w)

    def test_too_many_layers(self):
        smp = [{"path": str(i), "note": 60, "vel": i * 10, "on": True} for i in range(1, 10)]
        self.assertEqual(kc.build_map(smp)[2][0][0], "too_many_layers")


class Files(unittest.TestCase):
    def test_audio_info(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.wav"
            make_wav(p, 500, unity=62, loop=100)
            ai = kc.audio_info(p)
            self.assertEqual((ai["frames"], ai["rate"], ai["root"], ai["loop_start"], ai["loop_end"]),
                             (500, 44100, 62, 100, 500))
            a = Path(d) / "Pad-C3-V127-E36P.aif"
            make_aiff(a, 1000, 60, (300, 800))
            ai = kc.audio_info(a)
            self.assertEqual((ai["frames"], ai["rate"], ai["root"], ai["loop_start"], ai["loop_end"]),
                             (1000, 44100, 60, 300, 800))

    def test_loop_in_program(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "src"
            src.mkdir()
            make_aiff(src / "Pad-C3-V127-E36P.aif", 1000, 60, (300, 800))
            make_wav(src / "Pad-C4-V127-ABCD.wav", 900)
            samples = kc.scan_folder(src)
            for loops, expect in ((True, (800, 300, 1)), (False, (1000, 0, 0))):
                xpm, _, _ = kc.generate(samples, "Pad", Path(d) / str(loops), loops=loops, log=lambda m: None)
                ins = kc.read_xpm(xpm.read_bytes())[1]["data"]["drum"]["instruments"]
                si = ins[0]["layersv"][0]["sliceInfo"]
                self.assertEqual((si["End"], si["LoopStart"], si["LoopMode"]), expect)
                si = ins[1]["layersv"][0]["sliceInfo"]
                self.assertEqual((si["End"], si["LoopStart"], si["LoopMode"]), (900, 0, 0))

    def test_generate(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "src"
            src.mkdir()
            for n in ("C2", "C3"):
                for v in (50, 127):
                    make_wav(src / f"Keys-{n}-V{v}.wav", 800)
            make_wav(src / "Unnamed.wav", 800, unity=84)
            samples = kc.scan_folder(src)
            self.assertEqual(next(s for s in samples if s["stem"] == "Unnamed")["source"], "file")
            sound = {"amp": {"Attack": 10, "Release": 50}, "filter": {"type": 3, "cutoff": 40}}
            xpm, kgs, w = kc.generate(samples, "Keys", Path(d) / "out", sound=sound, log=lambda m: None)
            self.assertEqual(xpm, Path(d) / "out" / "Keys.xpm")
            self.assertTrue(xpm.is_file())
            pdata = Path(d) / "out" / "Keys_[ProgramData]"
            self.assertEqual(len(list(pdata.glob("*.wav"))), 5)
            self.assertEqual(list((Path(d) / "out").glob("*.wav")), [])
            raw = xpm.read_bytes()
            self.assertEqual(raw[:2], b"\x1f\x8b")
            header, doc = kc.read_xpm(raw)
            self.assertTrue(header.startswith(b"ACVS"))
            data = doc["data"]
            ins = data["drum"]["instruments"]
            self.assertEqual(data["keygroup"]["numKeygroups"], 3)
            self.assertEqual(len(ins), 3)
            self.assertEqual(len(ins[0]["layersv"]), 8)
            l0 = ins[0]["layersv"][0]
            self.assertEqual((l0["rootNote"], l0["velocityEnd"], l0["sliceInfo"]["End"]), (49, 50, 800))
            self.assertEqual(ins[0]["layersv"][1]["velocityStart"], 51)
            self.assertEqual(ins[0]["layersv"][2]["sampleName"], "")
            ss = ins[2]["synthSection"]
            self.assertAlmostEqual(ss["ampEnvelope"]["Attack"]["value0"], 0.1)
            self.assertAlmostEqual(ss["filterData"]["value0"]["filterCutoff"], 0.4)
            self.assertEqual(ss["filterData"]["value0"]["filterType"], 3)
            self.assertEqual(len(data["samples"]), 5)
            self.assertEqual(ss["filterBlend"], 0.0)
            self.assertFalse(ss["filterSerialRouting"])
            self.assertEqual(data["keygroup"]["synthSection"]["filterBlend"], 0.0)
            json.dumps(doc)

    def test_blend_serial(self):
        h, doc = kc.load_template()
        self.assertEqual(kc.template_sound(doc)["blend"], 0.0)
        ss = doc["data"]["drum"]["instruments"][0]["synthSection"]
        kc.apply_sound(ss, {"blend": 30, "serial": True})
        self.assertAlmostEqual(ss["filterBlend"], 0.3)
        self.assertTrue(ss["filterSerialRouting"])

    def test_template_roundtrip(self):
        h, doc = kc.load_template()
        h2, doc2 = kc.read_xpm(kc.write_xpm(h, doc))
        self.assertEqual((h, doc), (h2, doc2))


class EnvelopeCurve(unittest.TestCase):
    MPC = {0: 0, 10: 2.8, 20: 7.9, 40: 61.8, 60: 485.6, 80: 3820, 100: 30000}   # measured on the MPC

    def test_matches_mpc(self):
        for v, ms in self.MPC.items():
            self.assertAlmostEqual(kc.env_ms(v), ms, delta=max(0.06, ms * 0.002))

    def test_inverse(self):
        for ms in (5, 61.8, 250, 1500, 30000):   # 1 ms is value 0, shown as 0 by the MPC
            self.assertAlmostEqual(kc.env_ms(kc.env_value(ms)), ms, places=6)
        self.assertEqual(kc.env_value(0.5), 0)

    def test_cli_times(self):
        self.assertAlmostEqual(kc.parse_env("485.6ms", "Attack"), 60, delta=0.01)
        self.assertAlmostEqual(kc.parse_env("3,82s", "Release"), 80, delta=0.02)
        self.assertEqual(kc.parse_env("90", "Sustain"), 90)

    def test_presets_in_real_times(self):
        pad = kc.BUILTIN_PRESETS["Pad"]["amp"]
        self.assertAlmostEqual(kc.env_ms(pad["Attack"]), 600, delta=10)
        self.assertAlmostEqual(kc.env_ms(pad["Release"]), 1800, delta=30)

    def test_legacy_presets_upgraded(self):
        # use a temporary settings folder (works the same on macOS, Windows and Linux)
        from unittest import mock
        with tempfile.TemporaryDirectory() as d, mock.patch.object(kc, "app_dir", lambda: Path(d)):
            mine = copy.deepcopy(kc._LEGACY_BUILTIN["Lead"])
            mine["amp"]["Attack"] = 33
            kc.save_presets(dict(kc._LEGACY_BUILTIN, **{"Lead": mine, "Own": {"amp": {}}}))
            p = kc.load_presets()
            self.assertEqual(p["Pad"], kc.BUILTIN_PRESETS["Pad"])    # untouched -> new values
            self.assertEqual(p["Lead"]["amp"]["Attack"], 33)          # edited -> kept
            self.assertIn("Own", p)


class Desktop(unittest.TestCase):
    """pywebview and PyInstaller are not installed for the tests; check what can be checked."""
    ROOT = Path(__file__).resolve().parent.parent

    def test_sources_parse_for_python39(self):
        import ast
        for f in ("desktop/app.py", "desktop/keygroup_creator.spec", "scripts/make_desktop_icons.py",
                  "mpc_keygroup_creator.py", "keygroup_creator_gui.py", "ogg_preview.py", "build_app.py"):
            ast.parse((self.ROOT / f).read_text(encoding="utf-8"), feature_version=(3, 9))

    def test_versions_match(self):
        spec = (self.ROOT / "desktop" / "keygroup_creator.spec").read_text(encoding="utf-8")
        self.assertIn(f'VERSION = "{kc.VERSION}"', spec)
        self.assertIn(f"<string>{kc.VERSION}</string>", (self.ROOT / "build_app.py").read_text(encoding="utf-8"))

    def test_no_browser_dialogs_in_page(self):
        import keygroup_creator_gui as gui
        for bad in ("prompt(", "confirm(", "alert("):
            self.assertNotIn(bad, gui.PAGE.replace("no prompt() or confirm()", ""))


if __name__ == "__main__":
    unittest.main()
