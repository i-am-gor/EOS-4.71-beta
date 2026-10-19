#!/usr/bin/env python3
"""CEM3320 2-pole lowpass (Oberheim OB-Xa circuit) mapped onto the EOS 2-pole filter format.

Analog reference (linear part of the OB-Xa schematic, electricdruid.net/cem3320-filter-designs):
  stage 1  = summer (no cap); stages 2,3 = integrators (300p, no local feedback) -> state-variable filter
  LP feedback 100K/91K -> kL = 1.10 ; BP feedback through Res VCA sets damping d = 1/Q'
      H(s) = 1 / ((s/w)^2 + d (s/w) + kL)      w0 = w*sqrt(kL), Q = sqrt(kL)/d
  The diode limiter and OTA tanh are non-linear and cannot be reproduced by the E4's linear stages.

EOS mapping (see notes/filter_format.md): one pole-pair stage word per resonance step,
  upper half = low morph frame, lower half = high morph frame, half = X (log bandwidth) : F (log freq).
Poles are placed with the matched-z transform; zeros stay neutral like the stock 2-pole.
Resonance law: Q = Qmin * (Qmax/Qmin)**(q/127)  -> X is linear in q, F nearly constant,
which is exactly the shape of EOS's resonance formula FUN_00065E18, so only its constants change.

usage: cem3320.py [plot.png]
"""
import math, sys
import numpy as np
import eos_filter as ef

FS = ef.FS
KL = 100.0 / 91.0
QMIN, QMAX = 0.707, 20.0
F_LO, F_HI = 8, 238          # frame F bytes: ~110 Hz and ~16.2 kHz (model calibration)


def f_of(F):
    return 9824.0 * 2.0 ** ((F - 215.0) / 32.0)


def F_of(hz):
    return 215.0 + 32.0 * math.log2(hz / 9824.0)


def q_of(q):                 # resonance knob 0..127 -> Q
    return QMIN * (QMAX / QMIN) ** (q / 127.0)


def pole_half(f0, Q):
    """Analog SVF pole pair at f0 (natural), Q -> (X, F) bytes via matched-z."""
    w0T = 2 * math.pi * f0 / FS
    sig = w0T / (2 * Q)
    wd = w0T * math.sqrt(max(0.0, 1 - 1 / (4 * Q * Q)))
    r = math.exp(-sig)
    X = 255 + 16 * math.log2(1 - r)
    F = F_of(wd * FS / (2 * math.pi))
    return X, F


def clamp(v):
    return max(0, min(255, int(round(v))))


def stage_word(q):
    Q = q_of(q)
    xl, fl = pole_half(f_of(F_LO), Q)
    xh, fh = pole_half(f_of(F_HI), Q)
    return (clamp(xl) << 24) | (clamp(fl) << 16) | (clamp(xh) << 8) | clamp(fh), (xl, fl, xh, fh)


def table16():
    # stock code indexes the table with q>>3 (q = 0..127)
    return [stage_word(8 * j + 4)[0] for j in range(16)]


def fit_formula():
    """Least-squares fit of FUN_00065E18's form: byte = base + (slope*q')>>7, q' = min(127, q*17>>4)."""
    qs = np.arange(128)
    qp = np.minimum(127, (qs * 17) >> 4)
    raw = np.array([stage_word(q)[1] for q in qs])
    out = []
    for k, name in enumerate(('X_low', 'F_low', 'X_high', 'F_high')):
        A = np.vstack([np.ones_like(qp), qp / 128.0]).T
        (base, slope), *_ = np.linalg.lstsq(A, raw[:, k], rcond=None)
        err = np.abs(base + slope * qp / 128.0 - raw[:, k]).max()
        out.append((name, base, slope, err))
    return out


def analog_db(f, fc, Q):
    w0 = 2 * math.pi * fc
    s = 2j * np.pi * f
    w = w0 / math.sqrt(KL)
    d = math.sqrt(KL) / Q
    H = KL / ((s / w) ** 2 + d * (s / w) + KL)
    return 20 * np.log10(np.abs(H))


def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    tab = table16()
    print('CEM3320 2-pole RES16 table (replaces 0x6875C):')
    print('  ' + ' '.join(f'{w:08X}' for w in tab))
    print('stock:')
    print('  ' + ' '.join(f'{w:08X}' for w in ef.RES16))
    print('FUN_00065E18 constants fit (base + slope*q/128), max error in byte steps:')
    for name, b, s, e in fit_formula():
        print(f'  {name:7s} base {b:7.2f} slope {s:8.2f}  maxerr {e:.2f}')

    fig, axes = plt.subplots(3, 1, figsize=(9, 11))
    for ax, j, title in ((axes[0], 0, 'resonance 0'), (axes[1], 8, 'resonance 64'), (axes[2], 15, 'resonance 127')):
        for m, col in zip((0.0, 0.25, 0.5, 0.75, 0.95), plt.cm.viridis(np.linspace(0, .9, 5))):
            Fm = F_LO + (F_HI - F_LO) * m
            fc = f_of(Fm)
            f, db = ef.response(ef.blk(w0=tab[j]), m)
            f2, db2 = ef.response(ef.blk(w0=ef.RES16[j]), m)
            ref = analog_db(f, fc, q_of(8 * j + 4))
            ax.semilogx(f, db - db[0] + ref[0], color=col, lw=1.6, label=f'E4 CEM fit, fc≈{fc:.0f} Hz')
            ax.semilogx(f, ref, color=col, lw=0.8, ls='--')
            ax.semilogx(f2, db2 - db2[0] + ref[0], color=col, lw=0.8, ls=':')
        ax.set_title(f'CEM3320 2-pole: {title} (Q={q_of(8*j+4):.2f}) — solid: E4 fit, dashed: analog, dotted: stock E-mu',
                     fontsize=9)
        ax.set_ylim(-60, 30); ax.set_xlim(20, FS / 2); ax.grid(True, which='both', alpha=.3)
    axes[0].legend(fontsize=7)
    axes[-1].set_xlabel('Hz (model calibration, fs=48 kHz assumed)')
    fig.tight_layout()
    out = sys.argv[1] if len(sys.argv) > 1 else 'cem3320_fit.png'
    fig.savefig(out, dpi=110)
    print('wrote', out)


if __name__ == '__main__':
    main()
