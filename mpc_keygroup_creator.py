#!/usr/bin/env python3
"""Wavethings Keygroup Creator - engine and command line.

Builds one MPC 3.x keygroup program (.xpm) from a folder of samples whose file names carry the
root note (C2, F#3, Db4...) and, optionally, the velocity layer (V127, vel64, pp/mf/ff...).
Only the Python 3.9+ standard library is used.
"""
import argparse
import base64
import copy
import gzip
import json
import math
import os
import random
import re
import shutil
import struct
import sys
from pathlib import Path

VERSION = "1.4.0"
AUDIO_EXT = {".wav", ".aif", ".aiff"}
MAX_LAYERS = 8          # layers per keygroup in MPC 3.x
MAX_KEYGROUPS = 128

# Program saved by the MPC 3.9 (one keygroup, one layer) used as built-in template.
TEMPLATE_B64 = """
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
XZ0Jb5bV+s62ugsDXe23bCJ7W2isUEN6ThtG6YZ1PreOrm5c9bVyyYTTssqbm5x6XWrDpft6UV/+pqQHCWShvfbrE73K9utFJkbX
Cf/SLMRdEy1LRsmHqryYUs5Z2i3wBSHsmFvSYCRxlTYXI/9WsD/+1MzddXpTTpnfcaxzv9dbN7So60VWt+N5PUpdPnGaJXHRu+BQ
ziYmjGz4Ti9XNySSvW4DNLxDDpl/MObbyPyXY76DzD8c8/vZNGWGztmUPiSiyrtNfhONXYvmFvlu13WVOJRdBZOrVlWwfMhSFpe1
d/47zWWQLtJlsseFLrhbZg8A27lJ+AcUc23R/gnS5k0ofCOLzH1bNwgct4trLJsLULqUY5X1GnTeqSrlTdMb6QGychHj/A8XnP3v
7lXCm2Leckc0t81aM5GXtHbQxa+VjI+SoqFrcSykz8PFLSvzZDJheQfNOGfstuJczszrsei851XncRiovJWOxTV7aByr7okliX6n
D2ws8gxeDmrKW6ocsC4drmnmF0DvBiMtWqUz7T/iKE+AMVspm8jQfD1u2cn+WzP5spCO/09p0pWcqRPD7F7USaKmwp3LrNfarfPU
k1xUsx0uW6XUzmImihZ+WLzKfpkXbAltVN7tnPHRLeUTxS3i+1H95wWD0PU9L9wqsujH/SoM3K51LULc7s/XKWPpnbjuyCyv9KV1
EnRfSb0tITqWJudOVPH0TlwladkoMtTe4Nvak3FSWsdJ+68EdfHTQpqjGJzXNVVJ8wmUxldUWcLh9b8hoo+wxtVEVHsJuaJ7SOjQ
aACS8MywzmJKZ43wDKgM6tQmL1R9n5OZSGneebv8PosgCvgYBGyjgI9bwA4K+LgF7KKAj1vAHgr4uAXso4CPW8ABCvi4BRyigI9b
wBEK+MgTHZjKOnYJYy7r2CWMyaxjlzBms45dwpjOOnYJYz7r2CWMCa1jlzBmtI5dwpjSOnYJY07r2LEdmNM6dgljTuvYJYw5rWOX
MOa0jl3CmNM6dgljTuvYJYw5rWOXMOa0jl3CmNM6dgljTuvYt7NgTuvYJYw5rSORMLjDWHseFHgOVNf5T2072+On7vMErTLJPuds
OE3GLXNltZ9cnT35wBb7yu0uwvf1zneAsHji5XS4POG0bdjg4QLWuNn93bkve5NzRseeQYezzJv7hT2V9aGyukMP5+T6E1zmhBdV
KcZj3UEqc+JbVghOecwMe/GW1weZzNhyxsOFWrfYm7RzPz8upWe3jIvFDZPMTu+08gWTDOlFVc6qUntUhZrk8yMgNvnT66wag0Oz
cGbizDzkzDTyRBRDhixPaHore6JObOo4tm9OfZ4y3nkIVX06y7Mt2rKtG5Pj52vCs2y24LGW9oZyE7KrhQZ9aDRId0oYeGRJ++qx
5x0HjRBYSp9MRmE28+rh0hFLjBhjdtjPglp34M+CbnHoj6aXqxOe9EcrLxllWHfDATPaW6YOhu08CvcZTAfqB+rHj6sfZqH03Ibf
ieWVA60nQm1afqMjzzr086wslR9mcmBtX7/xfjmcgzazOBLesG43sF13ELkOsUlEBqRXW8OqKGnCDVsjPUdyy1KmTqk/BJ/+qU6J
O5gIrnKRqYs1TJrobUrOLg1rbk9sQFV/4Gw4FeXB6lfTf3EDwcEEcPAGFquSUQO9qtecpLiwb4cYmRLORZU/mPPOCbz+3DtsE/O1
47CNlCybLUyzSQvWe8GZ1auJ+qoSNjqYKjbn4S9P8zXjkvcNJp1mM7TTaKfRTqOdRjuNdhrt9N/UTjffAtFSo6VGS42WGi01Wmq0
1D+CpV77GN/2/VZdGZMU6iYf6GYcizaTFv7MbY3qWaehodUj+hHoR6AfgX4E+hHoR6Af8XfNzK/sNAyvll5ENjOEgXWD0kGYR1v/
4Kvk5l7EwoyDyJjV3YCMN4hoBRMkujoXwBgQrL2JRfgpFZ9p2gHbXvsWAtJteHhwjSsZgnRS93LGy2Gz2OciZkUhWqD3VsWTorkx
cEnRgvXOOm+Uth7qe9SKjpcjVlZcAx+1iuaWyuEsZ3RkwP0pzTMhO81yTafB7QHzfn9PqCN0f3XTWt3YKVteEA9fyr5WpGhH/XdQ
K55rYUyrAjMDNNiKWk497X2b20VEWmWqR7ZnOAYTcNcWfeelgtAS3A+thyL+UUVso4iPXcQOivgYRGzkKc6dgH+z/F3y2OIXbzsN
8ZRyzpr7jrf2XxzwctKqYNJFmUhf+p0YXdfXlP7Mr3c2+rXeOjt+vJV+269NIUn4ce3SZSuuilJk72ici2HMOGv1YSDfRTqweVHP
U8tqc8dYLJrEycdP4OgAy/kdG7AP3YBz6AbcQzfgHboB/9ANBN+zAUCfUGdQZ1BnTHXmMy3YqTI2f9Q7Q/IdS7RDgQqGCoYK1kvB
lGWCFGydAhUMFQwVbB8L9ucNHRHIgDUEqF+oX6hf+xiwbv1aJ0D9Qv1C/drXftk6+2WjfqF+oX7ta79snf1C/UL9Qv3a2345Ovvl
oH6hfqF+7Wu/HJ39Qv1C/UL92tt+uTr75aJ+oX6hfu1rv1yd/UL9Qv1C/drHfknl+SlPRoABm1OghqGGoYbtYcEgDdugQA1DDUMN
28OGveUPVyJNxdcGuN9lx9aoUNNQ01DT9rBlOk3boUJNQ01DTdsnLps+FUlMU+kbFmdFkUx4xngJAYENSxQ0m6XNxvyPGz3qvVGe
02ZLoHX26pzRqkzGVfrqst6r/+paPt5c2G/uiR28ubr8PWrjzIyWU8Pip1/pQ1sVqaCjn+VoOg4ZyFhJR+A+/uakkHp4g8FpFA18
4oWuG9i+53fsJ82FKN+L5toON+w6fkSzedP6wuqdkdbFq3f0XyK3dPcOLv9TM+ivk7/+Czo+FFksqgEA
"""

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
PITCH = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
# octave offset: midi = (octave + offset) * 12 + pitch class
OCTAVES = {"c3": 2, "c4": 1}       # c3: C3 = 60 (MPC / Akai), c4: C4 = 60 (Logic, Ableton...)

SEP = r"(?<![A-Za-z0-9])"
END = r"(?![A-Za-z0-9])"
NOTE_RE = re.compile(SEP + r"([A-Ga-g])(#|b|s|♯|♭)?(-?\d)" + END)
VEL_RE = re.compile(SEP + r"(?:v|vl|vel|velo|velocity)[ _\-]?(\d{1,3})" + END, re.I)
DYN_RE = re.compile(SEP + r"(ppp|pp|p|mp|mf|f|ff|fff)" + END)
NUM_RE = re.compile(SEP + r"(\d{1,3})" + END)
DYNAMICS = {"ppp": 16, "pp": 32, "p": 48, "mp": 64, "mf": 80, "f": 96, "ff": 112, "fff": 127}

# MPC filter types (index stored in the .xpm). 19-28 exist on the MPC but are not mapped here;
# the interface lets you type any index.
FILTER_TYPES = [
    (0, "Off", "Apagado"),
    (1, "Low Pass 1-pole", "Paso bajo 1 polo"), (2, "Low Pass 2-pole", "Paso bajo 2 polos"),
    (3, "Low Pass 4-pole", "Paso bajo 4 polos"), (4, "Low Pass 6-pole", "Paso bajo 6 polos"),
    (5, "Low Pass 8-pole", "Paso bajo 8 polos"),
    (6, "High Pass 1-pole", "Paso alto 1 polo"), (7, "High Pass 2-pole", "Paso alto 2 polos"),
    (8, "High Pass 4-pole", "Paso alto 4 polos"), (9, "High Pass 6-pole", "Paso alto 6 polos"),
    (10, "High Pass 8-pole", "Paso alto 8 polos"),
    (11, "Band Pass 2-pole", "Paso banda 2 polos"), (12, "Band Pass 4-pole", "Paso banda 4 polos"),
    (13, "Band Pass 6-pole", "Paso banda 6 polos"), (14, "Band Pass 8-pole", "Paso banda 8 polos"),
    (15, "Band Stop 2-pole", "Elimina banda 2 polos"), (16, "Band Stop 4-pole", "Elimina banda 4 polos"),
    (17, "Band Stop 6-pole", "Elimina banda 6 polos"), (18, "Band Stop 8-pole", "Elimina banda 8 polos"),
    (29, "MPC Low Pass", "Paso bajo MPC"),
]

# Sound settings exposed to the user. Values in the interface are 0-100 (stored as 0-1).
ENV_KEYS = ["Attack", "Hold", "Decay", "Sustain", "Release"]
FILTER_KEYS = {"cutoff": "filterCutoff", "resonance": "filterResonance",
               "envAmount": "filterEnvelopeAmount", "keytrack": "filterKeytrack",
               "velocity": "filterVelocity"}


class KeygroupError(Exception):
    pass


# ----------------------------------------------------------------------------- notes
def note_name(midi, octave="c3"):
    return f"{NOTE_NAMES[midi % 12]}{midi // 12 - OCTAVES[octave]}"


def parse_note(text, octave="c3"):
    """'C#3', 'Db2', 'c-1' or a MIDI number '60' -> MIDI note, or None."""
    text = str(text).strip()
    if re.fullmatch(r"\d{1,3}", text):
        n = int(text)
        return n if 0 <= n <= 127 else None
    m = re.fullmatch(r"([A-Ga-g])(#|b|s|♯|♭)?(-?\d)", text)
    return _note_from_match(m, octave) if m else None


def _note_from_match(m, octave):
    pc = PITCH[m.group(1).upper()]
    acc = m.group(2)
    if acc in ("#", "s", "♯"):
        pc += 1
    elif acc in ("b", "♭"):
        pc -= 1
    n = (int(m.group(3)) + OCTAVES[octave]) * 12 + pc
    return n if 0 <= n <= 127 else None


def parse_name(stem, octave="c3", numbers=False):
    """Find root note and velocity in a file name (without extension).
    Returns dict(note, note_span, vel, vel_span). The last note token wins."""
    out = {"note": None, "note_span": None, "vel": None, "vel_span": None}
    vm = list(VEL_RE.finditer(stem))
    if vm:
        v = int(vm[-1].group(1))
        if 0 <= v <= 127:
            out["vel"], out["vel_span"] = v, vm[-1].span()
    else:
        dm = list(DYN_RE.finditer(stem))
        if dm:
            out["vel"], out["vel_span"] = DYNAMICS[dm[-1].group(1)], dm[-1].span()
    vs = out["vel_span"]
    for m in reversed(list(NOTE_RE.finditer(stem))):
        if vs and m.start() < vs[1] and vs[0] < m.end():
            continue
        n = _note_from_match(m, octave)
        if n is not None:
            out["note"], out["note_span"] = n, m.span()
            break
    if out["note"] is None and numbers:
        for m in reversed(list(NUM_RE.finditer(stem))):
            if vs and m.start() < vs[1] and vs[0] < m.end():
                continue
            n = int(m.group(1))
            if 0 <= n <= 127:
                out["note"], out["note_span"] = n, m.span()
                break
    return out


# ----------------------------------------------------------------------------- audio files
def audio_info(path):
    """Frames, sample rate, loop (start, end - end exclusive) and embedded root note of a
    WAV (smpl chunk) or AIFF (INST sustain loop + MARK markers, as Logic's Auto Sampler writes)."""
    info = {"frames": 0, "rate": 0, "loop_start": None, "loop_end": None, "root": None}
    try:
        with open(path, "rb") as f:
            head = f.read(12)
            if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
                _wav(f, info)
            elif head[:4] == b"FORM" and head[8:12] in (b"AIFF", b"AIFC"):
                _aiff(f, info)
    except (OSError, struct.error):
        pass
    return info


def _chunks(f, big_endian):
    fmt = ">4sI" if big_endian else "<4sI"
    while True:
        h = f.read(8)
        if len(h) < 8:
            return
        cid, size = struct.unpack(fmt, h)
        pos = f.tell()
        yield cid, size, pos
        f.seek(pos + size + (size & 1))


def _wav(f, info):
    block = 0
    data = 0
    for cid, size, pos in _chunks(f, False):
        if cid == b"fmt ":
            fmt = f.read(16)
            _, ch, rate, _, block, _ = struct.unpack("<HHIIHH", fmt)
            info["rate"] = rate
        elif cid == b"data":
            data = size
        elif cid == b"smpl" and size >= 36:
            s = f.read(min(size, 60))
            unity = struct.unpack_from("<I", s, 12)[0]
            loops = struct.unpack_from("<I", s, 28)[0]
            if 0 <= unity <= 127:
                info["root"] = unity
            if loops and len(s) >= 60:
                start, end = struct.unpack_from("<II", s, 44)
                if end > start:
                    info["loop_start"], info["loop_end"] = start, end + 1   # dwEnd is inclusive
    if block:
        info["frames"] = data // block


def _aiff(f, info):
    markers, loop = {}, None
    for cid, size, pos in _chunks(f, True):
        if cid == b"COMM":
            c = f.read(18)
            ch, frames, bits = struct.unpack(">HIH", c[:8])
            exp, mant = struct.unpack(">HQ", c[8:18])
            info["frames"] = frames
            if mant:
                info["rate"] = round(mant * 2.0 ** ((exp & 0x7FFF) - 16383 - 63))
        elif cid == b"INST" and size >= 1:
            inst = f.read(min(size, 20))
            info["root"] = inst[0]
            if len(inst) >= 14:
                mode, begin, end = struct.unpack_from(">hhh", inst, 8)    # sustain loop
                if mode:
                    loop = (begin, end)
        elif cid == b"MARK" and size >= 2:
            m = f.read(size)
            q = 2
            for _ in range(struct.unpack_from(">H", m, 0)[0]):
                if q + 7 > len(m):
                    break
                mid, mpos = struct.unpack_from(">hI", m, q)
                ln = m[q + 6]
                q += 7 + ln + (0 if ln % 2 else 1)     # pstring padded to an even length
                markers[mid] = mpos
    if loop and loop[0] in markers and loop[1] in markers:
        start, end = markers[loop[0]], markers[loop[1]]
        if end > start:
            info["loop_start"], info["loop_end"] = start, end


# ----------------------------------------------------------------------------- scanning
def scan_folder(folder, recursive=False, octave="c3", numbers=False):
    """List the audio files of a folder with what their names say."""
    folder = Path(folder).expanduser()
    if not folder.is_dir():
        raise KeygroupError(f"folder not found: {folder}")
    it = folder.rglob("*") if recursive else folder.iterdir()
    files = sorted((p for p in it if p.is_file() and p.suffix.lower() in AUDIO_EXT
                    and not p.name.startswith("._")), key=lambda p: str(p).lower())
    out = []
    for p in files:
        parsed = parse_name(p.stem, octave, numbers)
        ai = audio_info(p)
        note, source = parsed["note"], "name"
        if note is None and ai["root"] is not None:
            note, source = ai["root"], "file"
        if note is None:
            source = ""
        out.append({"path": str(p), "file": str(p.relative_to(folder)), "stem": p.stem,
                    "note": note, "vel": parsed["vel"], "source": source,
                    "frames": ai["frames"], "rate": ai["rate"], "loop_start": ai["loop_start"],
                    "loop_end": ai["loop_end"],
                    "on": True})
    return out


def guess_name(samples, folder=None):
    """Program name from the first sample name, cut before the note token."""
    for s in samples:
        parsed = parse_name(s["stem"])
        cut = [sp[0] for sp in (parsed["note_span"], parsed["vel_span"]) if sp]
        if cut:
            name = s["stem"][:min(cut)].strip(" -_.")
            if name:
                return name
    return Path(folder).name if folder else "Keygroup"


def instrument_name(stem):
    """Instrument part of a sample name: what comes before the note / velocity token
    ("Analog_Pad-C3-V127-E36P" -> "Analog_Pad"). None if the name has no such token."""
    parsed = parse_name(stem)
    spans = [sp for sp in (parsed["note_span"], parsed["vel_span"]) if sp]
    if not spans:
        return None
    name = stem[:min(sp[0] for sp in spans)].strip(" -_.")
    if not name:    # note first ("C3 Piano"): keep the rest without the tokens
        rest = stem
        for a, b in sorted(spans, reverse=True):
            rest = rest[:a] + " " + rest[b:]
        name = re.sub(r"[\s_\-.]+", " ", rest).strip()
    return name or None


def group_samples(samples, fallback="Keygroup"):
    """Split a scan into instruments by name prefix. Samples without a note token join the
    instrument whose name starts their own name, or get their own group.
    Returns [(name, [samples])] sorted by name."""
    groups = {}
    loose = []
    for s in samples:
        n = instrument_name(s["stem"])
        if n is None:
            loose.append(s)
        else:
            groups.setdefault(n, []).append(s)
    for s in loose:
        low = s["stem"].lower()
        match = max((n for n in groups if low.startswith(n.lower())), key=len, default=None)
        groups.setdefault(match or s["stem"] or fallback, []).append(s)
    return sorted(groups.items(), key=lambda kv: kv[0].lower())


def unique_names(names):
    """Make program names unique and safe for files (case-insensitive)."""
    seen, out = set(), []
    for n in names:
        base = safe_name(n)
        cand, k = base, 2
        while cand.lower() in seen:
            cand, k = f"{base} ({k})", k + 1
        seen.add(cand.lower())
        out.append(cand)
    return out


# ----------------------------------------------------------------------------- envelope times
# Measured on an MPC (3.x): Attack, Hold, Decay and Release all follow
#   time = 30000 ** (value / 100) ms      (0 -> 0 ms, 10 -> 2.8 ms, 40 -> 61.8 ms, 60 -> 485.6 ms,
#                                           80 -> 3.82 s, 100 -> 30 s)
# Sustain is linear and the MPC shows it as 0-127.
ENV_MAX_MS = 30000.0
ENV_TIME_KEYS = ("Attack", "Hold", "Decay", "Release")


def env_ms(value):
    """Envelope knob (0-100) -> milliseconds, as the MPC shows it."""
    value = float(value)
    return 0.0 if value <= 0 else ENV_MAX_MS ** (min(value, 100.0) / 100.0)


def env_value(ms):
    """Milliseconds -> envelope knob (0-100). Below 1 ms is 0."""
    ms = float(ms)
    return 0.0 if ms < 1.0 else min(100.0, 100.0 * math.log(ms) / math.log(ENV_MAX_MS))


def parse_env(text, key):
    """CLI value: "250ms", "1.5s" (times, for A/H/D/R) or a plain 0-100 knob value."""
    t = str(text).strip().lower().replace(",", ".")
    m = re.fullmatch(r"([\d.]+)\s*(ms|s)", t)
    if m and key in ENV_TIME_KEYS:
        return round(env_value(float(m.group(1)) * (1000.0 if m.group(2) == "s" else 1.0)), 2)
    return float(t)


def T(ms):
    """Preset helper: time in ms -> knob value."""
    return round(env_value(ms), 1)


# ----------------------------------------------------------------------------- sound presets
def _snd(a, h, d, s, r, ftype=0, cut=100, res=0, env=0, fa=0, fh=0, fd=4.7, fs=100, fr=0,
         key=0, fvel=0, vel=100):
    return {"amp": dict(zip(ENV_KEYS, (a, h, d, s, r))),
            "fenv": dict(zip(ENV_KEYS, (fa, fh, fd, fs, fr))),
            "filter": {"type": ftype, "cutoff": cut, "resonance": res, "envAmount": env,
                       "keytrack": key, "velocity": fvel},
            "velSens": vel, "blend": 0, "serial": False}


# Starting points, 0-100 like the MPC knobs. Edit them in the app and save your own.
# Times are in ms (converted with the MPC curve above); sustain in % (100 = 127 on the MPC).
BUILTIN_PRESETS = {
    "Pad": _snd(T(600), 0, T(1500), 100, T(1800), 3, 70, 10, 15,
                fa=T(800), fd=T(2000), fs=70, fr=T(1500), vel=60),
    "Lead": _snd(T(5), 0, T(400), 90, T(250), 3, 80, 20, 20,
                 fd=T(350), fs=40, fr=T(250), key=30, vel=80),
    "Pluck": _snd(0, 0, T(450), 0, T(300), 3, 45, 15, 45,
                  fd=T(250), fs=0, fr=T(250), fvel=20, vel=100),
    "Keys": _snd(0, 0, T(2500), 50, T(400), vel=100),
    "Bass": _snd(0, 0, T(600), 85, T(80), 3, 60, 10, 25, fd=T(200), fs=30, fr=T(80), vel=90),
    "Strings": _snd(T(350), 0, T(1000), 100, T(900), 2, 85, 0, 0, vel=70),
}
# Built-in presets of 1.1-1.3 (knob values chosen before the MPC curve was measured). A preset still
# exactly like this is upgraded to the new values above when presets.json is loaded.
_LEGACY_BUILTIN = {
    "Pad": _snd(45, 0, 50, 100, 55, 3, 70, 10, 15, fa=50, fd=60, fs=70, fr=50, vel=60),
    "Lead": _snd(2, 0, 30, 90, 20, 3, 80, 20, 20, fd=35, fs=40, fr=20, key=30, vel=80),
    "Pluck": _snd(0, 0, 35, 0, 25, 3, 45, 15, 45, fd=30, fs=0, fr=25, fvel=20, vel=100),
    "Keys": _snd(0, 0, 60, 60, 30, fd=47, vel=100),
    "Bass": _snd(0, 0, 40, 85, 10, 3, 60, 10, 25, fd=25, fs=30, fr=10, vel=90),
    "Strings": _snd(30, 0, 40, 100, 45, 2, 85, 0, 0, fd=47, vel=70),
}

PRESET_WORDS = [("Pad", ("pad", "atmo", "ambient", "drone", "texture")),
                ("Pluck", ("pluck", "pizz", "arp", "mallet", "bell")),
                ("Bass", ("bass", "sub", "808")),
                ("Lead", ("lead", "solo", "saw", "synth")),
                ("Keys", ("keys", "piano", "ep", "rhodes", "wurli", "organ", "clav")),
                ("Strings", ("string", "violin", "cello", "brass", "choir", "ensemble"))]


def guess_preset(name, presets=None):
    """Preset name suggested by words in the instrument name, or None."""
    presets = BUILTIN_PRESETS if presets is None else presets
    words = re.findall(r"[a-z0-9]+", re.sub(r"([a-z])([A-Z])", r"\1 \2", name).lower())
    for preset, keys in PRESET_WORDS:
        if preset in presets and any(w.startswith(k) for w in words for k in keys):
            return preset
    for p in presets:   # user presets whose name appears in the instrument name
        if p.lower() in words:
            return p
    return None


def app_dir():
    """Settings folder shared by the app and the command line."""
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    d = base / "Wavethings Keygroup Creator"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_presets():
    """User presets (presets.json in the settings folder); the built-in ones the first time."""
    try:
        data = json.loads((app_dir() / "presets.json").read_text(encoding="utf-8"))
        if isinstance(data, dict):
            for name, old in _LEGACY_BUILTIN.items():
                if data.get(name) == old:
                    data[name] = copy.deepcopy(BUILTIN_PRESETS[name])
            return data
    except (OSError, ValueError):
        pass
    return copy.deepcopy(BUILTIN_PRESETS)


def save_presets(presets):
    f = app_dir() / "presets.json"
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(presets, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(f)


# ----------------------------------------------------------------------------- mapping
def velocity_ranges(values, mode="auto"):
    """Distinct velocity values (sorted) -> list of (start, end). Modes:
    upper: each value is the top of its range (V40, V80, V127 -> 0-40, 41-80, 81-127)
    center: boundaries half way between values
    even: the 0-127 range split in equal parts, in the order of the values
    auto: even if the values look like layer numbers (1, 2, 3...), otherwise upper."""
    n = len(values)
    if n == 0:
        return []
    if mode == "auto":
        mode = "even" if values == list(range(1, n + 1)) and n <= MAX_LAYERS else "upper"
    if n == 1:
        return [(0, 127)]
    if mode == "even":
        edges = [round(i * 128 / n) for i in range(n + 1)]
        return [(edges[i], edges[i + 1] - 1) for i in range(n)]
    if mode == "center":
        ends = [(values[i] + values[i + 1]) // 2 for i in range(n - 1)] + [127]
    else:
        ends = values[:-1] + [127]
    starts = [0] + [e + 1 for e in ends[:-1]]
    return list(zip(starts, ends))


def zone_bounds(roots, mode="center", extend=True):
    """Sorted distinct root notes -> list of (low, high) key ranges."""
    n = len(roots)
    lows, highs = [0] * n, [0] * n
    for i, r in enumerate(roots):
        if mode == "up":            # root at the bottom of its zone
            lows[i] = r
        elif mode == "down":        # root at the top of its zone
            lows[i] = roots[i - 1] + 1 if i else r
        else:                       # centered, same split the MPC uses
            lows[i] = (roots[i - 1] + r + 1) // 2 if i else r
    for i in range(n):
        highs[i] = lows[i + 1] - 1 if i + 1 < n else roots[-1]
    if mode == "down":
        lows[0] = roots[0]
    if extend and n:
        lows[0], highs[-1] = 0, 127
    return list(zip(lows, highs))


def build_map(samples, zones="center", extend=True, vel_mode="auto"):
    """samples: dicts with path, note, vel, on. Returns (keygroups, warnings, errors).
    Each keygroup: {low, high, root, layers: [{sample, vstart, vend, root}]}"""
    warnings, errors = [], []
    use = [s for s in samples if s.get("on", True)]
    missing = [s for s in use if s.get("note") is None]
    for s in missing:
        warnings.append(("no_note", Path(s["path"]).name))
    use = [s for s in use if s.get("note") is not None]
    if not use:
        errors.append(("no_samples", ""))
        return [], warnings, errors
    has_vel = any(s.get("vel") is not None for s in use)
    if has_vel:
        for s in use:
            if s.get("vel") is None:
                warnings.append(("no_vel", Path(s["path"]).name))
    vel_of = lambda s: s["vel"] if s.get("vel") is not None else 127
    values = sorted({vel_of(s) for s in use})
    if len(values) > MAX_LAYERS:
        errors.append(("too_many_layers", str(len(values))))
        return [], warnings, errors
    ranges = dict(zip(values, velocity_ranges(values, vel_mode)))
    by_layer = {v: {} for v in values}
    for s in sorted(use, key=lambda s: Path(s["path"]).name.lower()):
        slot = by_layer[vel_of(s)]
        if s["note"] in slot:
            warnings.append(("duplicate", Path(s["path"]).name))
            continue
        slot[s["note"]] = s
    roots = sorted({n for slot in by_layer.values() for n in slot})
    if len(roots) > MAX_KEYGROUPS:
        errors.append(("too_many_keygroups", str(len(roots))))
        return [], warnings, errors
    out = []
    for r, (lo, hi) in zip(roots, zone_bounds(roots, zones, extend)):
        layers = []
        for v in values:
            slot = by_layer[v]
            if r in slot:
                s = slot[r]
            else:   # this layer has no sample at this note: borrow the nearest one
                s = slot[min(slot, key=lambda n: (abs(n - r), n))]
            layers.append({"sample": s, "vstart": ranges[v][0], "vend": ranges[v][1],
                           "root": s["note"]})
        out.append({"low": lo, "high": hi, "root": r, "layers": layers})
    return out, warnings, errors


# ----------------------------------------------------------------------------- .xpm files
def read_xpm(data):
    """Bytes of an MPC 3.x program -> (header bytes, json dict)."""
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    i = data.find(b"{")
    if i < 0 or not data.startswith(b"ACVS"):
        raise KeygroupError("not an MPC 3.x program (.xpm saved by MPC 3.x)")
    return data[:i], json.loads(data[i:].decode("utf-8"))


def write_xpm(header, doc):
    raw = header + json.dumps(doc, indent=4, ensure_ascii=False).encode("utf-8")
    gz = bytearray(gzip.compress(raw, 9, mtime=0))
    gz[9] = 0x13            # same OS byte the MPC writes
    return bytes(gz)


def builtin_template():
    return base64.b64decode("".join(TEMPLATE_B64.split()))


def load_template(path=None):
    data = Path(path).expanduser().read_bytes() if path else builtin_template()
    header, doc = read_xpm(data)
    d = doc.get("data", {})
    if d.get("type") != 1 or not d.get("drum", {}).get("instruments"):
        raise KeygroupError("the template must be a keygroup program saved by MPC 3.x")
    if not path:
        # MPC default is 0.5 (both filters mixed); start the built-in template with filter 1 only
        for ss in [d["keygroup"]["synthSection"]] + [i["synthSection"] for i in d["drum"]["instruments"]]:
            ss["filterBlend"] = 0.0
    return header, doc


def template_sound(doc):
    """Current sound settings of a template, as interface values (0-100)."""
    ss = doc["data"]["drum"]["instruments"][0]["synthSection"]
    f0 = ss["filterData"]["value0"]
    pct = lambda x: round(float(x) * 100, 1)
    return {
        "amp": {k: pct(ss["ampEnvelope"][k]["value0"]) for k in ENV_KEYS},
        "fenv": {k: pct(ss["filterEnvelope"][k]["value0"]) for k in ENV_KEYS},
        "filter": dict({"type": int(f0["filterType"])},
                       **{k: pct(f0[v]) for k, v in FILTER_KEYS.items()}),
        "velSens": pct(ss.get("velocitySensitivity", 1.0)),
        "blend": pct(ss.get("filterBlend", 0.5)),          # 0 = only filter 1, 100 = only filter 2
        "serial": bool(ss.get("filterSerialRouting", False)),
    }


def _clamp01(v):
    return max(0.0, min(1.0, float(v) / 100.0))


def apply_sound(ss, sound):
    if not sound:
        return
    for env, key in (("amp", "ampEnvelope"), ("fenv", "filterEnvelope")):
        for k, v in (sound.get(env) or {}).items():
            if k in ENV_KEYS and v is not None:
                ss[key][k]["value0"] = _clamp01(v)
    flt = sound.get("filter") or {}
    f0 = ss["filterData"]["value0"]
    if flt.get("type") is not None:
        f0["filterType"] = int(flt["type"])
    for k, v in FILTER_KEYS.items():
        if flt.get(k) is not None:
            f0[v] = _clamp01(flt[k])
    if sound.get("velSens") is not None:
        ss["velocitySensitivity"] = _clamp01(sound["velSens"])
    if sound.get("blend") is not None:
        ss["filterBlend"] = _clamp01(sound["blend"])
    if sound.get("serial") is not None:
        ss["filterSerialRouting"] = bool(sound["serial"])


def _find_layers(inst):
    layers = inst["layersv"]
    empty = next((l for l in layers if not l.get("sampleName")), None)
    full = next((l for l in layers if l.get("sampleName")), None)
    if empty is None:
        empty = copy.deepcopy(layers[-1])
        empty.update(sampleName="", sampleFile="", rootNote=0, keyTrackEnable=False)
        empty["sliceInfo"].update(End=0, LoopStart=0, LoopMode=0)
    if full is None:
        full = copy.deepcopy(empty)
    return full, empty


def build_program(keygroups, name, header, doc, files, sound=None, seed=None, loops=True):
    """keygroups from build_map; files: {source path: file name next to the .xpm}."""
    rnd = random.Random(seed)
    doc = copy.deepcopy(doc)
    d = doc["data"]
    d["name"] = name
    proto = copy.deepcopy(d["drum"]["instruments"][0])
    full, empty = _find_layers(proto)
    nlayers = max(len(proto["layersv"]), MAX_LAYERS)
    apply_sound(proto["synthSection"], sound)
    apply_sound(d["keygroup"]["synthSection"], sound)
    instruments = []
    used = {}
    for kg in keygroups:
        inst = copy.deepcopy(proto)
        inst["lowNote"], inst["highNote"] = kg["low"], kg["high"]
        inst["tempo"] = 120.0
        inst["randomPlaySeed"] = rnd.randrange(1, 999999)
        lseed = rnd.randrange(1, 999999)
        layers = []
        for i in range(nlayers):
            if i < len(kg["layers"]):
                ly = kg["layers"][i]
                s = ly["sample"]
                fname = files[s["path"]]
                L = copy.deepcopy(full)
                L.update(active=True, mute=False, velocityStart=ly["vstart"],
                         velocityEnd=ly["vend"], rootNote=ly["root"] + 1, keyTrackEnable=True,
                         sampleName=Path(fname).stem, sampleFile=fname, sampleStart=0,
                         sampleEnd=0, loop=False, loopStart=0, loopEnd=0)
                si = L["sliceInfo"]
                frames = int(s.get("frames") or 0)
                ls, le = s.get("loop_start"), s.get("loop_end")
                si["Start"] = 0
                if loops and ls is not None:
                    # like the MPC when it loads a looped sample: the sample ends at the loop end
                    # and loops from the loop start (forward)
                    si["End"] = int(le) if le else frames
                    si["LoopStart"], si["LoopMode"] = int(ls), 1
                else:
                    si["End"], si["LoopStart"], si["LoopMode"] = frames, 0, 0
                used.setdefault(fname, ly["root"])
            else:
                L = copy.deepcopy(empty)
            L["sliceIncrementRngSeed"] = lseed
            layers.append(L)
        inst["layersv"] = layers
        instruments.append(inst)
    d["drum"]["instruments"] = instruments
    d["keygroup"]["numKeygroups"] = len(instruments)
    sproto = d["samples"][0] if d.get("samples") else {
        "version": 1, "name": "", "path": "", "loadImpl": 0,
        "metadata": {"tempo": 120.0, "rootNote": 60, "tune": 0.0, "key": "C Major"}}
    samples = []
    for fname, root in used.items():
        e = copy.deepcopy(sproto)
        e["name"], e["path"] = Path(fname).stem, fname
        md = e.setdefault("metadata", {})
        md.update(tempo=120.0, rootNote=root, tune=0.0, key=f"{NOTE_NAMES[root % 12]} Major")
        samples.append(e)
    d["samples"] = samples
    return write_xpm(header, doc)


def data_folder_name(name):
    """Folder next to the .xpm where MPC 3.x keeps a program's samples."""
    return f"{name}_[ProgramData]"


def safe_name(name):
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip(" .")
    return name or "Keygroup"


def generate(samples, name, output, zones="center", extend=True, vel_mode="auto", sound=None,
             template=None, hardlink=False, overwrite=True, log=print, loops=True,
             preview=True, preview_seconds=6.0):
    """Write <output>/<name>.xpm and its samples in <output>/<name>_[ProgramData]/, the layout
    MPC 3.x uses when it saves a program. Returns (xpm path, keygroups, warnings)."""
    keygroups, warnings, errors = build_map(samples, zones, extend, vel_mode)
    if errors:
        raise KeygroupError(errors[0][0] + (": " + errors[0][1] if errors[0][1] else ""))
    header, doc = load_template(template)
    name = safe_name(name)
    out = Path(output).expanduser()
    xpm = out / f"{name}.xpm"
    dest = out / data_folder_name(name)
    dest.mkdir(parents=True, exist_ok=True)
    if xpm.exists() and not overwrite:
        raise KeygroupError(f"exists: {xpm}")
    files, taken = {}, {}
    for kg in keygroups:
        for ly in kg["layers"]:
            src = Path(ly["sample"]["path"])
            if str(src) in files:
                continue
            fname = src.name
            k = 2
            while fname.lower() in taken and taken[fname.lower()] != src:
                fname = f"{src.stem} ({k}){src.suffix}"
                k += 1
            taken[fname.lower()] = src
            files[str(src)] = fname
            target = dest / fname
            if target.exists() and _same(target, src):
                continue
            if target.exists():
                target.unlink()
            if hardlink:
                try:
                    os.link(src, target)
                    continue
                except OSError:
                    pass
            shutil.copy2(src, target)
    xpm.write_bytes(build_program(keygroups, name, header, doc, files, sound, loops=loops))
    log(f"{xpm}  ({len(keygroups)} keygroups, {len(files)} samples)")
    if preview:
        src = preview_sample(keygroups)
        try:
            write_preview(src["path"], out, name, preview_seconds)
        except Exception as e:  # a failed preview never stops the program
            warnings.append(("preview_failed", f"{Path(src['path']).name}: {e}"))
    return xpm, keygroups, warnings


PREVIEW_NOTE = 60   # C3 on the MPC


def preview_sample(keygroups, note=PREVIEW_NOTE):
    """Sample used for the browser preview: the one whose root is closest to C3, loudest layer."""
    best = None
    for kg in keygroups:
        for ly in kg["layers"]:
            key = (abs(ly["root"] - note), ly["root"], -ly["vend"])
            if best is None or key < best[0]:
                best = (key, ly["sample"])
    return best[1]


def preview_path(output, name):
    """MPC browser preview: <output>/[Previews]/<name>.xpm.ogg"""
    return Path(output).expanduser() / "[Previews]" / f"{name}.xpm.ogg"


def write_preview(src, output, name, seconds=6.0):
    import ogg_preview
    dest = preview_path(output, name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    ogg_preview.make_preview(src, dest, seconds)
    return dest


def _same(a, b):
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


# ----------------------------------------------------------------------------- command line
def main(argv=None):
    ap = argparse.ArgumentParser(description="MPC 3.x keygroup program (.xpm) from a folder of samples")
    ap.add_argument("folder", help="folder with the samples")
    ap.add_argument("-o", "--output", default=".", help="output folder (default: current)")
    ap.add_argument("-n", "--name", help="program name (default: taken from the sample names)")
    ap.add_argument("-s", "--split", action="store_true",
                    help="one program per instrument found in the names (Pad-C3.., Lead-C3..)")
    ap.add_argument("-p", "--preset", help="sound preset (Pad, Lead, Pluck, Keys, Bass, Strings or "
                    "your own); 'auto' picks one from each instrument name")
    ap.add_argument("-r", "--recursive", action="store_true", help="include subfolders")
    ap.add_argument("--octave", choices=OCTAVES, default="c3", help="c3: C3=60 (MPC, default), c4: C4=60")
    ap.add_argument("--numbers", action="store_true", help="accept MIDI note numbers in names (_060_)")
    ap.add_argument("--zones", choices=["center", "up", "down"], default="center",
                    help="where the root sits in its key range (default: center)")
    ap.add_argument("--no-extend", action="store_true", help="do not stretch first/last zone to 0/127")
    ap.add_argument("--vel", choices=["auto", "upper", "center", "even"], default="auto",
                    help="how velocity values become layer ranges")
    ap.add_argument("-t", "--template", help="MPC 3.x keygroup .xpm to use as template")
    ap.add_argument("--hardlink", action="store_true", help="hard-link samples instead of copying")
    ap.add_argument("--amp", help="amp envelope A,H,D,S,R: times as 250ms / 1.5s (or 0-100 knob "
                    "values), sustain 0-100, e.g. 5ms,0,400ms,90,250ms")
    ap.add_argument("--fenv", help="filter envelope A,H,D,S,R, same format as --amp")
    ap.add_argument("--filter", help="filter TYPE,CUTOFF,RESONANCE,ENVAMOUNT (type index, rest 0-100)")
    ap.add_argument("--blend", type=float,
                    help="filter 1/2 mix, 0 = only filter 1 (default), 100 = only filter 2")
    ap.add_argument("--serial", action="store_true", help="filters in series instead of parallel")
    ap.add_argument("--no-loops", action="store_true", help="ignore the loop points stored in the samples")
    ap.add_argument("--no-preview", action="store_true",
                    help="do not write the browser preview ([Previews]/NAME.xpm.ogg)")
    ap.add_argument("--preview-seconds", type=float, default=6.0, help="preview length (default 6)")
    ap.add_argument("--list", action="store_true", help="only show the mapping, write nothing")
    ap.add_argument("-V", "--version", action="version", version=VERSION)
    a = ap.parse_args(argv)
    try:
        samples = scan_folder(a.folder, a.recursive, a.octave, a.numbers)
        sound = {}
        for key in ("amp", "fenv"):
            val = getattr(a, key)
            if val:
                sound[key] = {k: parse_env(x, k) for k, x in zip(ENV_KEYS, val.split(","))}
        if a.filter:
            parts = [float(x) for x in a.filter.split(",")]
            sound["filter"] = dict(zip(["type", "cutoff", "resonance", "envAmount"], parts))
            sound["filter"]["type"] = int(sound["filter"]["type"])
        if a.blend is not None:
            sound["blend"] = a.blend
        if a.serial:
            sound["serial"] = True
        presets = load_presets()
        if a.preset and a.preset != "auto" and a.preset not in presets:
            sys.exit(f"error: unknown preset {a.preset!r} ({', '.join(presets)})")
        if a.split:
            groups = group_samples(samples, Path(a.folder).name)
        else:
            groups = [(a.name or guess_name(samples, a.folder), samples)]
        names = unique_names([g[0] for g in groups])
        failed = 0
        for name, (_, smp) in zip(names, groups):
            pname = a.preset if a.preset != "auto" else guess_preset(name, presets)
            snd = copy.deepcopy(presets.get(pname, {})) if pname else {}
            for k, v in sound.items():        # explicit options win over the preset
                if isinstance(v, dict):
                    snd.setdefault(k, {}).update(v)
                else:
                    snd[k] = v
            print(f"[{name}]" + (f"  preset: {pname}" if pname else ""))
            keygroups, warnings, errors = build_map(smp, a.zones, not a.no_extend, a.vel)
            for w in warnings:
                print(f"  ! {w[0]}: {w[1]}")
            for kg in keygroups:
                lay = ", ".join(f"{Path(l['sample']['path']).name} [{l['vstart']}-{l['vend']}]"
                                for l in kg["layers"])
                print(f"  {note_name(kg['low'], a.octave):>4}-{note_name(kg['high'], a.octave):<4} "
                      f"root {note_name(kg['root'], a.octave):<4} {lay}")
            if errors:
                print(f"  error: {errors[0][0]} {errors[0][1]}")
                failed += 1
                continue
            if not a.list:
                _, _, w = generate(smp, name, a.output, a.zones, not a.no_extend, a.vel, snd,
                                   a.template, a.hardlink, loops=not a.no_loops,
                                   preview=not a.no_preview, preview_seconds=a.preview_seconds)
                for x in w:
                    if x[0] == "preview_failed":
                        print(f"  ! preview: {x[1]}")
        if failed:
            sys.exit(f"{failed} program(s) not created")
    except KeygroupError as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
