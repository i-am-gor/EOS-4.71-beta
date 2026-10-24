#!/usr/bin/env python3
"""Simulated filter responses: the real filter code of an EOS image (computeFrames in Unicorn, sweep_test.block_for)
turned into a frequency response with the chip's measured stage law (notes/filter_format.md, "Measured stage law",
2026-10-20, 1.9 dB RMS over 73 single-stage words):
  pole stage  H = w0^2 / (s^2 + b s + w0^2)     zero stage  H = (s^2 + b s + w0^2) / wn^2,  wn = 2 pi 8060 Hz
  f0 = 1398.5 Hz * 2^((F - 0x80) / 31.42)       b (absolute damping, Hz) interpolated in log over the measured X points
  cutoff morph m = cutoff / 255, linear in X and F between the low and high frame (as EOS builds the frames)
  word 9 with mode bit 6 (output gain / level compensation) is not modelled: its format is not known, so absolute
  level versus Q is not simulated; compare shapes (passband-aligned). Linear only: no distortion or clipping.
Output: OUT.json {tag: [{f, level}]} at the same 1/3-octave bands as the measurements, relative to the simulated
flat Swept-EQ reference, with tags like the hardware runs (2pole_c64_q32 ...).

usage: sim_filters.py IMAGE.bin OUT.json [CUTS] [QS]
"""
import json, math, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import emu_obxa as emu            # noqa: E402
import sweep_test as sw           # noqa: E402
import eos_filter as ef           # noqa: E402

VT = {'2pole': 0x68878, '4pole': 0x688A4, '6pole': 0x688D0, 'hp2': 0x688FC, 'hp4': 0x68928, 'bp2': 0x689D8,
      'bp4': 0x68A04, 'cbp': 0x68A30}
REF_VT = 0x68954                  # Swept EQ 1 octave; gain 64 = flat
BANDS = [round(40 * 2 ** (i / 3)) for i in range(26) if 40 * 2 ** (i / 3) <= 12600]
XP = [0x60, 0x80, 0xA0, 0xC0, 0xE0, 0xF0, 0xFF]
BP = [21, 61, 233, 1015, 4053, 6209, 8104]


def damping(X):
    if X <= XP[0]:
        return BP[0] * 2 ** ((X - XP[0]) / 16)     # one octave per 16 steps below the measured range
    return float(np.exp(np.interp(X, XP, np.log(BP))))


def half(word, hi):
    h = (word >> 16) & 0xFFFF if not hi else word & 0xFFFF
    return h >> 8, h & 0xFF


def response(blk, flags, m, f):
    s = 2j * np.pi * f
    H = np.ones_like(f, dtype=complex)
    for t, w in sw.stages(blk, flags):
        x0, f0 = half(w, False); x1, f1 = half(w, True)
        X, F = x0 + (x1 - x0) * m, f0 + (f1 - f0) * m
        w0 = 2 * np.pi * 1398.5 * 2 ** ((F - 0x80) / 31.42)
        b = 2 * np.pi * damping(X)
        sec = s * s + b * s + w0 * w0
        H *= (w0 * w0) / sec if t == 'P' else sec / (2 * np.pi * 8060) ** 2
    return 20 * np.log10(np.abs(H) + 1e-12)        # word 9 (mode bit 6) gain is not modelled: format unknown


def main():
    img, out = sys.argv[1], sys.argv[2]
    cuts = [int(v) for v in sys.argv[3].split(',')] if len(sys.argv) > 3 else list(range(0, 241, 16))
    qs = [int(v) for v in sys.argv[4].split(',')] if len(sys.argv) > 4 else list(range(0, 113, 8)) + [127]
    E = emu.Emu(open(img, 'rb').read())
    f = np.array(BANDS, float)
    rblk, rfl = sw.block_for(E, REF_VT, 64)
    ref = response(rblk, rfl, 128 / 255, f)
    res = {}
    for name, vt in VT.items():
        for q in qs:
            blk, fl = sw.block_for(E, vt, q)
            for c in cuts:
                lv = response(blk, fl, c / 255, f) - ref
                res[f'{name}_c{c}_q{q}'] = [dict(f=int(b), level=round(float(v), 2)) for b, v in zip(BANDS, lv)]
    json.dump(dict(ref_flatness_db=round(float(ref.max() - ref.min()), 2), bands=res), open(out, 'w'))
    print(f'{out}: {len(res)} settings; simulated reference spread {ref.max() - ref.min():.2f} dB')


if __name__ == '__main__':
    main()
