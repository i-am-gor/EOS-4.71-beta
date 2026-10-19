#!/usr/bin/env python3
"""Sine-sweep headroom test of EOS voice filters (simulation of the decoded stage model).

For each filter, its real coefficient block is produced by running the filter's own computeFrames
in Unicorn (stock or patched image), with FUN_0010D3B0 hooked to read the mode flags.
A full-scale log sine sweep (20 Hz - 20 kHz) is run through the stages in order
  stage k = pole pair (word 4k) then zero pair (word 4k+1); word 9 is a zero unless mode bit 6 (gain)
for 33 static cutoff (morph) positions, plus one run with a 2 Hz LFO sweeping the cutoff.
Reported: peak level at each internal stage output, relative to the input sweep's peak (0 dB).
Pole stages are DC-normalised and zero stages monic, as in tools/eos_filter.py (hypothesis).

usage: sweep_test.py STOCK.bin [PATCHED.bin] [--q 127] [--plot out.png]
"""
import argparse, math, os, struct, sys
import numpy as np
from scipy.signal import lfilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eos_filter as ef   # noqa: E402
import emu_obxa as emu    # noqa: E402

FS = ef.FS
FILTERS = [  # (name, vtable) in menu order; morph filters need a param struct and are left out
    ('2 Pole Low-pass', 0x68878), ('4 Pole Low-pass', 0x688A4), ('6 Pole Low-pass', 0x688D0),
    ('2nd Order High-pass', 0x688FC), ('4th Order High-pass', 0x68928), ('2nd Order Band-pass', 0x689D8),
    ('4th Order Band-pass', 0x68A04), ('Contrary Band-pass', 0x68A30), ('Swept EQ 1 octave', 0x68954),
    ('Swept EQ 2->1 oct', 0x68980), ('Swept EQ 3->1 oct', 0x689AC), ('Phaser 1', 0x68A5C),
    ('Phaser 2', 0x68A88), ('Bat-Phaser', 0x68AB4), ('Flanger Lite', 0x68AE0), ('Vocal Ah-Ay-Ee', 0x68B0C),
    ('Vocal Oo-Ah', 0x68B38),
]


def block_for(E, vt, q):
    fn = struct.unpack('>I', E.img[vt + 0x14 - emu.BASE:][:4])[0]
    _, blk, calls = E.call(fn, [0, emu.BLK, 0, q], blk_init=ef.NEUTRAL)
    flags = calls[0][2] if calls else 0
    return list(blk[:10]), flags


def stage_coefs(word, m, pole):
    r, th = ef.stage(word, m)
    a = np.array([1.0, -2 * r * math.cos(th), r * r])
    if pole:
        return np.array([a.sum()]), a          # DC-normalised all-pole section
    return a, np.array([1.0])                  # monic zero section


def stages(blk, flags):
    out = []
    for k in range(3):
        out.append(('P', blk[4 * k]))
        zi = 4 * k + 1
        if not (zi == 9 and flags & 0x40):
            out.append(('Z', blk[zi]))
    return [(t, w) for t, w in out if w != ef.NEUTRAL]


def sweep(seconds=2.0, f0=20.0, f1=20000.0):
    t = np.arange(int(seconds * FS)) / FS
    k = math.log(f1 / f0)
    return np.sin(2 * math.pi * f0 * seconds / k * (np.exp(t * k / seconds) - 1))


X = sweep()


def static_levels(blk, flags, morphs):
    st = stages(blk, flags)
    worst = []          # per morph: list of node peaks (dB)
    for m in morphs:
        y, peaks = X, []
        for t, w in st:
            b, a = stage_coefs(w, m, t == 'P')
            y = lfilter(b, a, y)
            peaks.append(20 * math.log10(np.abs(y).max() + 1e-12))
        worst.append(peaks)
    return st, worst


def lfo_levels(blk, flags, rate=2.0):
    """Direct-form I, coefficients updated every sample from a triangle-free sine LFO on morph."""
    st = stages(blk, flags)
    n = len(X)
    m = 0.5 + 0.5 * np.sin(2 * math.pi * rate * np.arange(n) / FS)
    y = X.copy()
    peaks = []
    for t, w in st:
        xl, fl = ef.half(w, True)
        xh, fh = ef.half(w, False)
        xs, fs_ = xl + (xh - xl) * m, fl + (fh - fl) * m
        r = np.maximum(0, 1 - 2.0 ** ((xs - 255) / 16))
        th = np.minimum(np.pi, 2 * np.pi * 9824 * 2.0 ** ((fs_ - 215) / 32) / FS)
        a1, a2 = -2 * r * np.cos(th), r * r
        out = np.zeros(n)
        x1 = x2 = y1 = y2 = 0.0
        if t == 'P':
            g = 1 + a1 + a2
            for i in range(n):
                v = g[i] * y[i] - a1[i] * y1 - a2[i] * y2
                y2, y1 = y1, v
                out[i] = v
        else:
            for i in range(n):
                v = y[i] + a1[i] * x1 + a2[i] * x2
                x2, x1 = x1, y[i]
                out[i] = v
        y = out
        peaks.append(20 * math.log10(np.abs(y).max() + 1e-12))
    return peaks


def report(label, E, q, morphs, do_lfo):
    rows = []
    for name, vt in FILTERS:
        blk, flags = block_for(E, vt, q)
        st, lv = static_levels(blk, flags, morphs)
        if not st:
            continue
        node_max = max(max(p) for p in lv)
        mi = int(np.argmax([max(p) for p in lv]))
        si = int(np.argmax(lv[mi]))
        lfo = max(lfo_levels(blk, flags)) if do_lfo else float('nan')
        rows.append((name, node_max, morphs[mi], si + 1, len(st), max(p[-1] for p in lv), lfo))
    print(f'\n== {label}, resonance/param {q}')
    print(f'  {"filter":22s} {"max internal":>12s} {"at morph":>8s} {"stage":>7s} {"output max":>10s} {"LFO run":>8s}')
    for name, nm, m, s, ns, out, lfo in rows:
        print(f'  {name:22s} {nm:10.1f} dB {m:8.2f} {s:>3d}/{ns:<3d} {out:8.1f} dB {lfo:6.1f} dB')
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('stock'); ap.add_argument('patched', nargs='?')
    ap.add_argument('--q', type=int, default=127)
    ap.add_argument('--lfo', action='store_true', help='also run the per-sample LFO test (slow)')
    a = ap.parse_args()
    morphs = list(np.linspace(0, 1, 33))
    S = emu.Emu(open(a.stock, 'rb').read())
    rs = report('STOCK 4.70', S, a.q, morphs, a.lfo)
    if a.patched:
        P = emu.Emu(open(a.patched, 'rb').read())
        global FILTERS
        keep = FILTERS
        FILTERS = keep[:3]
        rp = report('PATCHED', P, a.q, morphs, a.lfo)
        FILTERS = keep
        budget = max(r[1] for r in rs)
        print(f'\nStock headroom budget (highest internal level of any stock filter above): {budget:.1f} dB')
        for r in rp:
            flag = 'OVER budget' if r[1] > budget + 0.5 else 'within budget'
            print(f'  {r[0]:22s} {r[1]:6.1f} dB  {flag} (stock same filter: '
                  f'{next(x[1] for x in rs if x[0] == r[0]):.1f} dB)')


if __name__ == '__main__':
    main()
