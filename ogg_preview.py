"""Wavethings Keygroup Creator - browser previews (.xpm.ogg) for the MPC.

Reads a WAV/AIFF sample and writes it as Ogg Vorbis with a small built-in encoder, so no ffmpeg or
other program is needed. Quality is aimed at short previews, not at archiving. Pure standard
library (Python 3.9+).
"""
import array
import cmath
import heapq
import math
import random
import struct
import sys

# ============================================================================ reading audio
def read_audio(path, max_seconds=None):
    """WAV (PCM 8/16/24/32, float 32/64) or AIFF/AIFC (PCM, sowt, fl32/fl64).
    Returns (rate, [channel lists of floats in -1..1])."""
    with open(path, "rb") as f:
        head = f.read(12)
        if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
            return _read_wav(f, max_seconds)
        if head[:4] == b"FORM" and head[8:12] in (b"AIFF", b"AIFC"):
            return _read_aiff(f, head[8:12] == b"AIFC", max_seconds)
    raise ValueError("unsupported audio file")


def _chunks(f, big):
    fmt = ">4sI" if big else "<4sI"
    while True:
        h = f.read(8)
        if len(h) < 8:
            return
        cid, size = struct.unpack(fmt, h)
        pos = f.tell()
        yield cid, size
        f.seek(pos + size + (size & 1))


def _read_wav(f, max_seconds):
    fmt = None
    for cid, size in _chunks(f, False):
        if cid == b"fmt ":
            b = f.read(size)
            tag, ch, rate, _, block, bits = struct.unpack_from("<HHIIHH", b)
            if tag == 0xFFFE and len(b) >= 26:
                tag = struct.unpack_from("<H", b, 24)[0]
            fmt = (tag, ch, rate, block, bits)
        elif cid == b"data" and fmt:
            tag, ch, rate, block, bits = fmt
            n = size // block
            if max_seconds:
                n = min(n, int(rate * max_seconds))
            data = f.read(n * block)
            kind = "f" if tag == 3 else "i"
            return rate, _deinterleave(_decode(data, bits, kind, False), ch)
    raise ValueError("no audio data")


def _read_aiff(f, aifc, max_seconds):
    comm = None
    for cid, size in _chunks(f, True):
        if cid == b"COMM":
            b = f.read(size)
            ch, frames, bits = struct.unpack_from(">hIh", b)
            exp, mant = struct.unpack_from(">HQ", b, 8)
            rate = round(mant * 2.0 ** ((exp & 0x7FFF) - 16383 - 63)) if mant else 44100
            comp = b[18:22] if aifc and len(b) >= 22 else b"NONE"
            comm = (ch, frames, bits, rate, comp)
        elif cid == b"SSND" and comm:
            ch, frames, bits, rate, comp = comm
            offset = struct.unpack(">I", f.read(4))[0]
            f.read(4 + offset)
            if max_seconds:
                frames = min(frames, int(rate * max_seconds))
            block = ch * ((bits + 7) // 8)
            if comp in (b"fl32", b"FL32"):
                bits, kind, little = 32, "f", False
            elif comp in (b"fl64", b"FL64"):
                bits, kind, little = 64, "f", False
            elif comp == b"sowt":
                kind, little = "i", True
            elif comp in (b"NONE", b"twos"):
                kind, little = "i", False
            else:
                raise ValueError("unsupported AIFC compression")
            block = ch * (bits // 8)
            data = f.read(frames * block)
            return rate, _deinterleave(_decode(data, bits, kind, not little), ch)
    raise ValueError("no audio data")


def _decode(data, bits, kind, big):
    swap = big != (sys.byteorder == "big")
    if kind == "f":
        a = array.array("f" if bits == 32 else "d")
        a.frombytes(data[:len(data) - len(data) % a.itemsize])
        if swap:
            a.byteswap()
        return [max(-1.0, min(1.0, v)) for v in a]
    if bits == 8:       # WAV 8-bit is unsigned, AIFF 8-bit signed
        a = array.array("B" if not big else "b", data)
        return [(v - 128) / 128.0 for v in a] if not big else [v / 128.0 for v in a]
    if bits == 16:
        a = array.array("h")
        a.frombytes(data[:len(data) & ~1])
        if swap:
            a.byteswap()
        return [v / 32768.0 for v in a]
    if bits == 24:
        n = len(data) // 3
        out = bytearray(n * 4)
        if big:
            out[3::4], out[2::4], out[1::4] = data[0:n * 3:3], data[1:n * 3:3], data[2:n * 3:3]
        else:
            out[1::4], out[2::4], out[3::4] = data[0:n * 3:3], data[1:n * 3:3], data[2:n * 3:3]
        a = array.array("i")
        a.frombytes(bytes(out))
        if sys.byteorder == "big":
            a.byteswap()
        return [v / 2147483648.0 for v in a]
    if bits == 32:
        a = array.array("i")
        a.frombytes(data[:len(data) & ~3])
        if swap:
            a.byteswap()
        return [v / 2147483648.0 for v in a]
    raise ValueError(f"unsupported bit depth {bits}")


def _deinterleave(samples, ch):
    return [samples[c::ch] for c in range(ch)]


def prepare(chans, rate, seconds=6.0, fade=0.25):
    """Up to two channels, cut to `seconds` with a short fade out, silence trimmed at the end."""
    if len(chans) > 2:
        chans = [chans[0], chans[1]]
    n = min(len(chans[0]), int(rate * seconds)) if seconds else len(chans[0])
    chans = [c[:n] for c in chans]
    end = n
    while end > 0 and all(abs(c[end - 1]) < 1e-4 for c in chans):
        end -= 1
    chans = [c[:max(end, 1)] for c in chans]
    n = len(chans[0])
    if seconds and n >= int(rate * seconds) - 1:
        nf = min(n, int(rate * fade))
        for c in chans:
            for i in range(nf):
                c[n - nf + i] *= 1.0 - (i + 1) / nf
    return chans


# ============================================================================ Vorbis encoder
N = 2048                # long block (only long blocks are used)
HALF = N // 2
RANGEBITS = 10          # floor X range = 1024 = HALF
MULT = 2                # floor1 multiplier -> Y range 0..127, ~1.1 dB per step
YRANGE = 128
FINE_Q = 15             # fine residue book: -15..15
COARSE_STEP = 31        # coarse book: -7..7 x 31
COARSE_Q = 7
PART = 16               # residue partition size
POSTS = [0, HALF, 1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 18, 22, 27, 33, 40, 48, 58, 70, 84, 100, 120, 145,
         175, 210, 250, 300, 360, 430, 512, 610, 730, 870]
FLOOR_CLASS_DIM = 4     # (len(POSTS) - 2) / 4 = 8 partitions
INV_DB0 = 1.0649863e-07
INV_DB_STEP = math.log(1.0 / INV_DB0) / 255.0
INV_DB = [INV_DB0 * math.exp(i * INV_DB_STEP) for i in range(256)]
INV_DB[255] = 1.0


class BitWriter:
    def __init__(self):
        self.buf = bytearray()
        self.acc = 0
        self.n = 0

    def write(self, value, bits):
        if bits <= 0:
            return
        self.acc |= (value & ((1 << bits) - 1)) << self.n
        self.n += bits
        while self.n >= 8:
            self.buf.append(self.acc & 0xFF)
            self.acc >>= 8
            self.n -= 8

    def bytes(self):
        out = bytearray(self.buf)
        if self.n:
            out.append(self.acc & 0xFF)
        return bytes(out)


def ilog(v):
    r = 0
    while v > 0:
        r += 1
        v >>= 1
    return r


def vorbis_float(x):
    if x == 0:
        return 0
    sign = 0x80000000 if x < 0 else 0
    m, e = abs(x), 788
    while m >= (1 << 21):
        m /= 2.0
        e += 1
    while m != int(m) and m < (1 << 20):
        m *= 2.0
        e -= 1
    return sign | (e << 21) | int(m)


def huffman_lengths(counts, limit=24):
    """Code lengths for every entry (counts are smoothed so all entries are used)."""
    counts = [c + 1 for c in counts]
    while True:
        heap = [(c, i, None) for i, c in enumerate(counts)]
        heapq.heapify(heap)
        parent = {}
        uid = len(counts)
        while len(heap) > 1:
            a = heapq.heappop(heap)
            b = heapq.heappop(heap)
            parent[a[1]] = uid
            parent[b[1]] = uid
            heapq.heappush(heap, (a[0] + b[0], uid, None))
            uid += 1
        depth = {heap[0][1]: 0}
        lengths = []
        # walk up from leaves
        memo = {}
        def d(node):
            if node in memo:
                return memo[node]
            if node not in parent:
                memo[node] = 0
                return 0
            memo[node] = d(parent[node]) + 1
            return memo[node]
        sys.setrecursionlimit(max(10000, sys.getrecursionlimit()))
        lengths = [max(1, d(i)) for i in range(len(counts))]
        if max(lengths) <= limit:
            return lengths
        counts = [c // 2 + 1 for c in counts]


def make_codewords(lengths):
    """Canonical Vorbis codeword assignment (as libvorbis _make_words)."""
    marker = [0] * 33
    codes = []
    for length in lengths:
        entry = marker[length]
        if length < 32 and (entry >> length):
            raise ValueError("overpopulated codebook")
        codes.append(entry)
        for j in range(length, 0, -1):
            if marker[j] & 1:
                marker[j] = marker[j] + 1 if j == 1 else marker[j - 1] << 1
                break
            marker[j] += 1
        for j in range(length + 1, 33):
            if (marker[j] >> 1) == entry:
                entry = marker[j]
                marker[j] = marker[j - 1] << 1
            else:
                break
    # bit-reverse so a codeword can be written LSB-first in one call
    rev = []
    for c, l in zip(codes, lengths):
        r = 0
        for _ in range(l):
            r = (r << 1) | (c & 1)
            c >>= 1
        rev.append(r)
    return rev


class Codebook:
    def __init__(self, dims, entries, lookup=None):
        self.dims, self.entries, self.lookup = dims, entries, lookup  # lookup: (min, delta, nvals)
        self.counts = [0] * entries
        self.lengths = None
        self.codes = None

    def finalize(self):
        self.lengths = huffman_lengths(self.counts)
        self.codes = make_codewords(self.lengths)

    def put(self, bw, entry):
        bw.write(self.codes[entry], self.lengths[entry])

    def header(self, bw):
        bw.write(0x564342, 24)
        bw.write(self.dims, 16)
        bw.write(self.entries, 24)
        bw.write(0, 1)  # not ordered
        bw.write(0, 1)  # not sparse
        for l in self.lengths:
            bw.write(l - 1, 5)
        if not self.lookup:
            bw.write(0, 4)
            return
        mn, delta, nvals = self.lookup
        bw.write(1, 4)
        bw.write(vorbis_float(mn), 32)
        bw.write(vorbis_float(delta), 32)
        vbits = max(1, ilog(nvals - 1))
        bw.write(vbits - 1, 4)
        bw.write(0, 1)  # no sequence
        for v in range(nvals):
            bw.write(v, vbits)


# ---------------------------------------------------------------- MDCT (via FFT of HALF/2)
class MDCT:
    def __init__(self, n):
        self.n = n
        m = n // 2              # outputs
        self.m = m
        q = m // 2              # complex FFT size
        self.q = q
        self.pre = [cmath.exp(-1j * math.pi * (4 * k + 1) / (4 * m)) for k in range(q)]
        self.post = [cmath.exp(-1j * math.pi * k / m) for k in range(q)]
        bits = ilog(q - 1)
        self.rev = [int(format(i, f"0{bits}b")[::-1], 2) for i in range(q)]
        self.tw = {}
        size = 2
        while size <= q:
            self.tw[size] = [cmath.exp(-2j * math.pi * k / size) for k in range(size // 2)]
            size *= 2
        self.window = [math.sin(math.pi / 2 * math.sin(math.pi * (i + 0.5) / n) ** 2) for i in range(n)]

    def fft(self, a):
        q = self.q
        a = [a[r] for r in self.rev]
        size = 2
        while size <= q:
            half = size // 2
            tw = self.tw[size]
            for start in range(0, q, size):
                for k in range(half):
                    i = start + k
                    j = i + half
                    t = a[j] * tw[k]
                    a[j] = a[i] - t
                    a[i] = a[i] + t
            size *= 2
        return a

    def forward(self, x):
        """x: n windowed samples -> n/2 coefficients (sum convention, no scaling)."""
        n, m = self.n, self.m
        h = m // 2
        u = [0.0] * m
        for i in range(h):
            u[i] = -x[3 * h - 1 - i] - x[3 * h + i]
            u[h + i] = x[i] - x[m - 1 - i]
        # DCT-IV of u via complex FFT
        t = [complex(u[2 * k], u[m - 1 - 2 * k]) * self.pre[k] for k in range(self.q)]
        T = self.fft(t)
        out = [0.0] * m
        for k in range(self.q):
            y = T[k] * self.post[k]
            out[2 * k] = y.real
            out[m - 1 - 2 * k] = -y.imag
        return out


# ---------------------------------------------------------------- floor 1
def _render_point(x0, y0, x1, y1, x):
    dy = y1 - y0
    adx = x1 - x0
    err = abs(dy) * (x - x0)
    off = err // adx
    return y0 - off if dy < 0 else y0 + off


def _render_line(x0, y0, x1, y1, v):
    dy = y1 - y0
    adx = x1 - x0
    ady = abs(dy)
    base = int(dy / adx)      # truncates toward zero, as C
    sy = base - 1 if dy < 0 else base + 1
    x, y, err = x0, y0, 0
    ady -= abs(base) * adx
    if x < len(v):
        v[x] = y
    for x in range(x0 + 1, min(x1, len(v))):
        err += ady
        if err >= adx:
            err -= adx
            y += sy
        else:
            y += base
        v[x] = y


class Floor:
    def __init__(self):
        xs = POSTS
        self.xs = xs
        self.n = len(xs)
        self.low = [0] * self.n
        self.high = [0] * self.n
        for i in range(2, self.n):
            lo, hi = 0, 1
            for j in range(i):
                if xs[j] < xs[i] and xs[j] > xs[lo]:
                    lo = j
                if xs[j] > xs[i] and xs[j] < xs[hi]:
                    hi = j
            self.low[i], self.high[i] = lo, hi
        self.order = sorted(range(self.n), key=lambda i: xs[i])
        # analysis bands: half way between neighbouring posts
        sx = [xs[i] for i in self.order]
        self.bands = {}
        for k, i in enumerate(self.order):
            a = 0 if k == 0 else (sx[k - 1] + sx[k] + 1) // 2      # band holds bin X itself
            b = HALF if k == len(sx) - 1 else (sx[k] + sx[k + 1] + 1) // 2
            self.bands[i] = (a, max(b, a + 1))
        # post whose band holds each bin, and neighbours in X order
        self.bin_post = [0] * HALF
        for i, (a, b) in self.bands.items():
            for k in range(a, min(b, HALF)):
                self.bin_post[k] = i
        self.low_s, self.high_s = {}, {}
        for k, i in enumerate(self.order):
            self.low_s[i] = self.order[k - 1] if k else None
            self.high_s[i] = self.order[k + 1] if k + 1 < len(self.order) else None

    def encode_values(self, target):
        """Target Y per post -> (values to write, final Y, step2 flags)."""
        n = self.n
        final = [0] * n
        flag = [False] * n
        vals = [0] * n
        final[0], final[1] = target[0], target[1]
        vals[0], vals[1] = target[0], target[1]
        flag[0] = flag[1] = True
        xs = self.xs
        for i in range(2, n):
            lo, hi = self.low[i], self.high[i]
            pred = _render_point(xs[lo], final[lo], xs[hi], final[hi], xs[i])
            hiroom, loroom = YRANGE - pred, pred
            room = 2 * hiroom if hiroom < loroom else 2 * loroom
            d = target[i] - pred
            if d == 0:
                val = 0
            elif d > 0 and 2 * d < room:
                val = 2 * d
            elif d < 0 and -2 * d - 1 < room:
                val = -2 * d - 1
            elif hiroom > loroom:
                val = d + loroom            # target above the room
            else:
                val = -d + hiroom - 1       # target below the room
            val = max(0, min(YRANGE - 1, val))
            vals[i] = val
            # decode exactly as the decoder will
            if val:
                flag[lo] = flag[hi] = flag[i] = True
                if val >= room:
                    final[i] = val - loroom + pred if hiroom > loroom else pred - val + hiroom - 1
                else:
                    final[i] = pred - (val + 1) // 2 if val & 1 else pred + val // 2
            else:
                final[i] = pred
            final[i] = max(0, min(YRANGE - 1, final[i]))
        return vals, final, flag

    def curve(self, final, flag):
        v = [0] * HALF
        lx, ly = 0, final[self.order[0]] * MULT
        hx, hy = 0, ly
        for i in self.order[1:]:
            if flag[i]:
                hy = final[i] * MULT
                hx = self.xs[i]
                _render_line(lx, ly, hx, hy, v)
                lx, ly = hx, hy
        if hx < HALF:
            _render_line(hx, hy, HALF, hy, v)
        return [INV_DB[max(0, min(255, y))] for y in v]


# ---------------------------------------------------------------- encoder
class VorbisEncoder:
    def __init__(self, rate, channels, quality=6.0, seed=1):
        self.rate, self.ch = rate, channels
        self.quality = quality          # residue magnitude aimed for (higher = better/bigger)
        self.mdct = MDCT(N)
        self.floor = Floor()
        self.scale = 1.0 / (N / 4)      # decoder roundtrip gain is 1 (checked with ffmpeg)
        self.serial = random.Random(seed).randrange(1, 2 ** 31)

    # analysis -> per frame/channel: None (silent) or (vals, residues)
    def _analyse(self, chans):
        n = len(chans[0])
        hop = HALF
        frames = -(-n // hop) + 1
        pad = [[0.0] * hop + list(c) + [0.0] * (hop * 2 + (frames + 1) * hop - n - hop) for c in chans]
        w = self.mdct.window
        absmin = 10 ** (-96 / 20)       # below -96 dB nothing is coded
        out = []
        fl = self.floor
        logstep = INV_DB_STEP * MULT
        for f in range(frames):
            start = f * hop
            frame = []
            for c in pad:
                seg = c[start:start + N]
                coef = self.mdct.forward([seg[i] * w[i] for i in range(N)])
                coef = [x * self.scale for x in coef]
                peak = max(abs(x) for x in coef)
                if peak < absmin * 4:
                    frame.append(None)
                    continue
                target = [0] * fl.n
                for i in range(fl.n):
                    a, b = fl.bands[i]
                    e = sum(x * x for x in coef[a:b]) / (b - a)
                    amp = max(math.sqrt(e) / self.quality, absmin)
                    y = int(round(math.log(amp / INV_DB0) / logstep))
                    target[i] = max(0, min(YRANGE - 1, y))
                lim = COARSE_Q * COARSE_STEP + FINE_Q
                for _ in range(8):      # raise the floor where a coefficient would not fit
                    vals, final, flag = fl.encode_values(target)
                    curve = fl.curve(final, flag)
                    over = {}
                    for k in range(HALF):
                        r = abs(coef[k]) / curve[k]
                        if r > lim:
                            i = fl.bin_post[k]
                            over[i] = max(over.get(i, 0), r)
                    if not over:
                        break
                    for i, r in over.items():
                        step = int(math.ceil(math.log(r / (lim * 0.8)) / logstep)) + 1
                        target[i] = min(YRANGE - 1, target[i] + step)
                        for j in (fl.low_s[i], fl.high_s[i]):   # neighbours shape the line too
                            if j is not None:
                                target[j] = min(YRANGE - 1, max(target[j], target[i] - 2))
                res = []
                for k in range(HALF):
                    q = int(round(coef[k] / curve[k]))
                    res.append(lim if q > lim else -lim if q < -lim else q)
                frame.append((vals, res))
            out.append(frame)
        return out, n

    def encode(self, chans):
        frames, nsamples = self._analyse(chans)
        floorbook = Codebook(1, YRANGE)
        classbook = Codebook(1, 3)
        fine = Codebook(2, (2 * FINE_Q + 1) ** 2, (-FINE_Q, 1, 2 * FINE_Q + 1))
        coarse = Codebook(2, (2 * COARSE_Q + 1) ** 2,
                          (-COARSE_Q * COARSE_STEP, COARSE_STEP, 2 * COARSE_Q + 1))
        self.books = [floorbook, classbook, fine, coarse]
        # turn residues into classes and book entries; gather statistics
        nf, nc = 2 * FINE_Q + 1, 2 * COARSE_Q + 1
        packets = []
        for frame in frames:
            pk = []
            for chd in frame:
                if chd is None:
                    pk.append(None)
                    continue
                vals, res = chd
                for i in range(2, len(vals)):
                    floorbook.counts[vals[i]] += 1
                parts = []
                for p in range(0, HALF, PART):
                    seg = res[p:p + PART]
                    m = max(abs(x) for x in seg)
                    if m == 0:
                        parts.append((0, None, None))
                        classbook.counts[0] += 1
                        continue
                    if m <= FINE_Q:
                        fe = [(seg[i] + FINE_Q) + (seg[i + 1] + FINE_Q) * nf for i in range(0, PART, 2)]
                        for e in fe:
                            fine.counts[e] += 1
                        parts.append((1, None, fe))
                        classbook.counts[1] += 1
                        continue
                    cs = [max(-COARSE_Q, min(COARSE_Q, int(round(x / COARSE_STEP)))) for x in seg]
                    fs = [max(-FINE_Q, min(FINE_Q, x - c * COARSE_STEP)) for x, c in zip(seg, cs)]
                    ce = [(cs[i] + COARSE_Q) + (cs[i + 1] + COARSE_Q) * nc for i in range(0, PART, 2)]
                    fe = [(fs[i] + FINE_Q) + (fs[i + 1] + FINE_Q) * nf for i in range(0, PART, 2)]
                    for e in ce:
                        coarse.counts[e] += 1
                    for e in fe:
                        fine.counts[e] += 1
                    parts.append((2, ce, fe))
                    classbook.counts[2] += 1
                pk.append((vals, parts))
            packets.append(pk)
        for b in self.books:
            b.finalize()
        audio = [self._packet(pk) for pk in packets]
        return self._ogg([self._ident(), self._comment(), self._setup()], audio, nsamples)

    # ------------------------------------------------------------ packets
    def _ident(self):
        bw = BitWriter()
        bw.write(1, 8)
        for c in b"vorbis":
            bw.write(c, 8)
        bw.write(0, 32)
        bw.write(self.ch, 8)
        bw.write(self.rate, 32)
        bw.write(0, 32)
        bw.write(0, 32)
        bw.write(0, 32)
        bw.write(8, 4)      # blocksize_0 = 256
        bw.write(11, 4)     # blocksize_1 = 2048
        bw.write(1, 1)
        return bw.bytes()

    def _comment(self):
        bw = BitWriter()
        bw.write(3, 8)
        for c in b"vorbis":
            bw.write(c, 8)
        vendor = b"Wavethings Keygroup Creator"
        bw.write(len(vendor), 32)
        for c in vendor:
            bw.write(c, 8)
        bw.write(0, 32)
        bw.write(1, 1)
        return bw.bytes()

    def _setup(self):
        bw = BitWriter()
        bw.write(5, 8)
        for c in b"vorbis":
            bw.write(c, 8)
        bw.write(len(self.books) - 1, 8)
        for b in self.books:
            b.header(bw)
        bw.write(0, 6)          # time domain transforms: 1, value 0
        bw.write(0, 16)
        bw.write(0, 6)          # floors: 1
        bw.write(1, 16)         # type 1
        nparts = (len(POSTS) - 2) // FLOOR_CLASS_DIM
        bw.write(nparts, 5)
        for _ in range(nparts):
            bw.write(0, 4)      # all partitions use class 0
        bw.write(FLOOR_CLASS_DIM - 1, 3)
        bw.write(0, 2)          # no subclasses
        bw.write(0 + 1, 8)      # subclass book: codebook 0
        bw.write(MULT - 1, 2)
        bw.write(RANGEBITS, 4)
        for x in POSTS[2:]:
            bw.write(x, RANGEBITS)
        bw.write(0, 6)          # residues: 1
        bw.write(1, 16)         # type 1
        bw.write(0, 24)         # begin
        bw.write(HALF, 24)      # end
        bw.write(PART - 1, 24)
        bw.write(3 - 1, 6)      # 3 classifications
        bw.write(1, 8)          # classbook
        for cascade in (0b00, 0b01, 0b11):
            bw.write(cascade & 7, 3)
            bw.write(0, 1)
        # class 1: pass 0 fine; class 2: pass 0 coarse, pass 1 fine
        bw.write(2, 8)
        bw.write(3, 8)
        bw.write(2, 8)
        bw.write(0, 6)          # mappings: 1
        bw.write(0, 16)         # type 0
        bw.write(0, 1)          # one submap
        bw.write(0, 1)          # no coupling
        bw.write(0, 2)
        bw.write(0, 8)          # submap 0: time
        bw.write(0, 8)          # floor 0
        bw.write(0, 8)          # residue 0
        bw.write(0, 6)          # modes: 1
        bw.write(1, 1)          # long block
        bw.write(0, 16)
        bw.write(0, 16)
        bw.write(0, 8)          # mapping 0
        bw.write(1, 1)          # framing
        return bw.bytes()

    def _packet(self, pk):
        fb, cb, fine, coarse = self.books
        bw = BitWriter()
        bw.write(0, 1)          # audio packet; mode number takes 0 bits
        bw.write(1, 1)          # previous window long
        bw.write(1, 1)          # next window long
        ybits = ilog(YRANGE - 1)
        for chd in pk:
            if chd is None:
                bw.write(0, 1)
                continue
            vals = chd[0]
            bw.write(1, 1)
            bw.write(vals[0], ybits)
            bw.write(vals[1], ybits)
            for v in vals[2:]:
                fb.put(bw, v)
        active = [c for c in pk if c is not None]
        nparts = HALF // PART
        for p in range(nparts):         # pass 0: class, then data
            for c in active:
                cb.put(bw, c[1][p][0])
            for c in active:
                cls, ce, fe = c[1][p]
                if cls == 1:
                    for e in fe:
                        fine.put(bw, e)
                elif cls == 2:
                    for e in ce:
                        coarse.put(bw, e)
        for p in range(nparts):         # pass 1
            for c in active:
                cls, ce, fe = c[1][p]
                if cls == 2:
                    for e in fe:
                        fine.put(bw, e)
        return bw.bytes()

    # ------------------------------------------------------------ ogg pages
    def _ogg(self, headers, audio, nsamples):
        out = bytearray()
        seq = 0

        def page(segs_data, granule, flags):
            nonlocal seq
            lacing, body = segs_data
            hdr = struct.pack("<4sBBqIIIB", b"OggS", 0, flags, granule, self.serial, seq, 0, len(lacing))
            data = bytearray(hdr + bytes(lacing) + body)
            crc = _crc(data)
            data[22:26] = struct.pack("<I", crc)
            out.extend(data)
            seq += 1

        def lace(pkt):
            n = len(pkt)
            return [255] * (n // 255) + [n % 255]

        # page 0: identification header alone
        page((lace(headers[0]), headers[0]), 0, 2)
        # comment + setup on their own page(s)
        self._write_packets(page, headers[1:], [0, 0], first_flags=0, last=False)
        grans = [min(i * HALF, nsamples) for i in range(len(audio))]
        grans[-1] = nsamples
        self._write_packets(page, audio, grans, first_flags=0, last=True)
        return bytes(out)

    @staticmethod
    def _write_packets(page, packets, granules, first_flags, last):
        """Lay packets into pages (~4 KB); a page ends after the last packet when `last`."""
        lacing, body, gran, cont = [], bytearray(), -1, False
        for k, (pkt, g) in enumerate(zip(packets, granules)):
            n = len(pkt)
            segs = [255] * (n // 255) + [n % 255]
            pos = 0
            for s in segs:
                if len(lacing) == 255:          # page full in the middle of a packet
                    page((lacing, bytes(body)), gran, 1 if cont else 0)
                    lacing, body, gran, cont = [], bytearray(), -1, True
                lacing.append(s)
                body.extend(pkt[pos:pos + s])
                pos += s
            gran = g
            # keep the last audio packet on its own page so the end trim is unambiguous
            if k < len(packets) - 1 and (len(body) >= 4000 or (last and k == len(packets) - 2)):
                page((lacing, bytes(body)), gran, 1 if cont else 0)
                lacing, body, gran, cont = [], bytearray(), -1, False
        if lacing:
            page((lacing, bytes(body)), gran, (1 if cont else 0) | (4 if last else 0))
        else:
            cont = False


_CRC = []
for _i in range(256):
    _r = _i << 24
    for _ in range(8):
        _r = ((_r << 1) ^ 0x04C11DB7) if _r & 0x80000000 else (_r << 1)
    _CRC.append(_r & 0xFFFFFFFF)


def _crc(data):
    c = 0
    for b in data:
        c = ((c << 8) ^ _CRC[((c >> 24) ^ b) & 0xFF]) & 0xFFFFFFFF
    return c


def encode_ogg(chans, rate, quality=6.0):
    return VorbisEncoder(rate, len(chans), quality).encode(chans)


def make_preview(src, dest, seconds=6.0, quality=6.0):
    """Write `src` (WAV/AIFF) as an Ogg Vorbis preview at `dest`."""
    rate, chans = read_audio(src, seconds + 0.5 if seconds else None)
    chans = prepare(chans, rate, seconds)
    data = encode_ogg(chans, rate, quality)
    with open(dest, "wb") as f:
        f.write(data)
    return len(data)
