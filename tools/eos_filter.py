#!/usr/bin/env python3
"""Model of the EOS 4.70 voice-filter coefficient format (hypothesis, see notes/filter_format.md).

Block written by each filter class into sound-chip RAM (0x80 bytes per voice):
  word 0, 4, 8 : pole-pair stages
  word 1, 5    : zero-pair stages
  word 9       : zero-pair stage, or output gain when mode bit 6 is set
Each 32-bit word = [low-frame half-word][high-frame half-word]; the chip morphs between them.
Each half-word   = X (upper byte, log bandwidth) : F (lower byte, log frequency)
  F: 32 steps / octave,  f ~= 9824 * 2**((F-215)/32) Hz   (calibrated from Dual EQ display)
  X: 16 steps / octave of (1-r),  r = 1 - 2**((X-255)/16)  (X=0xFF -> r=0, i.e. no effect)
0xFFCF in a half (X=FF) is a neutral stage.

The F->Hz constant is good to roughly +/- a quarter octave; morph is modelled as linear
interpolation of X and F, which matches how EOS builds frames but is not verified on hardware.
"""
import sys
import numpy as np

FS = 48000.0
# F scale. Hardware-measured 2026-10-17 (stock sweeps, notes/filter_format.md): 30.7 steps/oct,
# 10421 Hz at F=215. The earlier Dual-EQ-display estimate was 32 steps/oct, 9824 Hz.
F_REF_HZ, F_REF, F_PER_OCT = 10421.0, 215.0, 30.7


def f_hz(F):
    return F_REF_HZ * 2.0 ** ((F - F_REF) / F_PER_OCT)


def half(word, hi):
    h = (word >> 16) & 0xffff if hi else word & 0xffff
    return h >> 8, h & 0xff


def stage(word, morph):
    """Return (r, theta) for a stage word at morph 0..1 (0 = low frame)."""
    x0, f0 = half(word, True)
    x1, f1 = half(word, False)
    x = x0 + (x1 - x0) * morph
    f = f0 + (f1 - f0) * morph
    r = max(0.0, 1.0 - 2.0 ** ((x - 255.0) / 16.0))
    hz = f_hz(f)
    th = min(np.pi, 2 * np.pi * hz / FS)
    return r, th


def biquad_mag(r, th, w):
    z1 = np.exp(-1j * w)
    return np.abs(1 - 2 * r * np.cos(th) * z1 + r * r * z1 * z1)


def response(block, morph, gain_word9=True, n=2048):
    w = np.linspace(2 * np.pi * 20 / FS, np.pi, n)
    mag = np.ones_like(w)
    for i in (0, 4, 8):
        mag /= biquad_mag(*stage(block[i], morph), w)
    for i in (1, 5) if gain_word9 else (1, 5, 9):
        mag *= biquad_mag(*stage(block[i], morph), w)
    return w * FS / (2 * np.pi), 20 * np.log10(mag + 1e-12)


# ---- re-implementations of the EOS frame builders (decompiled from 0x65E18..0x67E9C) ----
NEUTRAL = 0xffcfffcf
RES16 = [0x8408ffcf, 0x8008fbd2, 0x7d08f8d4, 0x7a08f5d6, 0x7708f2d9, 0x7308efdb, 0x7008ecdd,
         0x6d07e9e0, 0x6a07e6e2, 0x6707e3e4, 0x6307e0e7, 0x6006dde9, 0x5d06daeb, 0x5a05d7ed,
         0x5205d4ef, 0x5205d4ef]  # table at 0x6875C


def blk(**kw):
    b = [NEUTRAL] * 10
    for k, v in kw.items():
        b[int(k[1:])] = v & 0xffffffff
    return b


def lp(poles, q):            # q 0..127 (resonance)
    s = RES16[(q >> 3) & 15]
    return blk(w0=s, w4=s if poles >= 4 else NEUTRAL, w8=s if poles >= 6 else NEUTRAL)


def hp2(q):
    return blk(w1=0x80048004, w4=(0x8004ffcf - (q >> 2) * 0x01000100))


def swept_eq1(gain):         # gain 0..127, 64 = flat
    i = (gain - 0x40) >> 1
    z = ((0x77 + i) << 24) | (0x07 << 16) | ((0xdf + i) << 8) | 0xd7
    p = ((0x77 - i) << 24) | (0x07 << 16) | ((0xdf - i) << 8) | 0xd7
    return blk(w5=z, w8=p)


def vocal_ah_ay_ee(body):    # body 0..127
    u = (body >> 2) | ((body >> 2) << 16)
    return blk(w0=0x709570b1 + u, w1=0xffc0ffc0, w4=0x706f709d + u, w8=0x70547035 + u)


def dual_eq(lo1, hi1, g1, lo2, hi2, g2):   # all 0..127, gains 64 = flat
    def sec(lo, hi, g):
        fl, fh = (lo * 0xd2 >> 7) + 7, (hi * 0xd2 >> 7) + 7
        xl, xh = (fl >> 1) + 0x74, (fh >> 1) + 0x74
        g = max(-32, min(31, (g - 0x40) >> 1))
        mk = lambda s: ((xl + s) << 24) | (fl << 16) | ((xh + s) << 8) | fh
        return mk(g), mk(-g)
    z1, p1 = sec(lo1, hi1, g1)
    z2, p2 = sec(lo2, hi2, g2)
    return blk(w1=z1, w4=p1, w5=z2, w8=p2)


def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    cases = [
        ('4 Pole Low-pass, res 0 / 100', [(lp(4, 0), False), (lp(4, 100), False)]),
        ('2nd Order High-pass, res 0 / 100', [(hp2(0), False), (hp2(100), False)]),
        ('Swept EQ 1 oct, +18 dB / -18 dB', [(swept_eq1(112), False), (swept_eq1(16), False)]),
        ('Vocal Ah-Ay-Ee, body 0', [(vocal_ah_ay_ee(0), True)]),
        ('Dual EQ Morph: +12 dB @ lo, -12 dB @ hi', [(dual_eq(40, 100, 96, 70, 120, 32), False)]),
    ]
    fig, axes = plt.subplots(len(cases), 1, figsize=(9, 3.0 * len(cases)))
    for ax, (title, variants) in zip(axes, cases):
        for b, zero9 in variants:
            for m in (0.0, 0.25, 0.5, 0.75, 1.0):
                f, db = response(b, m, gain_word9=not zero9)
                ax.semilogx(f, db - db.max(), lw=1, label=f'morph {m:.2f}' if b is variants[0][0] else None)
        ax.set_title(title, fontsize=10)
        ax.set_ylim(-60, 5)
        ax.set_xlim(20, FS / 2)
        ax.grid(True, which='both', alpha=.3)
    axes[0].legend(fontsize=7, ncol=5)
    axes[-1].set_xlabel('Hz (model, fs=48 kHz assumed)')
    fig.tight_layout()
    out = sys.argv[1] if len(sys.argv) > 1 else 'filter_model.png'
    fig.savefig(out, dpi=110)
    print('wrote', out)
    # formant check
    b = vocal_ah_ay_ee(0)
    for m, vowel in ((0, 'Ah'), (1, 'Ee')):
        fs = sorted(9824 * 2 ** ((half(b[i], m == 0)[1] - 215) / 32) for i in (0, 4, 8))
        print(vowel, 'formants (Hz):', [round(x) for x in fs])


if __name__ == '__main__':
    main()
