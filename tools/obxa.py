#!/usr/bin/env python3
"""Oberheim OB-Xa CEM3320 filters mapped onto the EOS 2/4/6-pole lowpass stage words.

Analog models (linear parts of the schematics at electricdruid.net/cem3320-filter-designs):
  2-pole  state-variable: stage1 summer, stages 2+3 integrators (300p, 100K in), LP fb 100K/91K
          H2(s) = kL / ((s/ws)^2 + d (s/ws) + kL),  kL = 1.0989, natural w0 = ws*sqrt(kL)
          resonance = Res-VCA cancelling BP damping: d = d0 - (d0-dmin)*q/127 (linear VCA law)
  4-pole  ladder: 4 x (91K in, 100K fb, 300p) lossy stages, Res VCA from stage 4 to stage 1
          H4(s) = G^4 / ((1 + s/ws)^4 + k),  G = 100K/91K, k = kmax*q/127 (oscillates at k = 4)
  6-pole  4-pole ladder cascaded with the 2-pole SVF, both on the same ws (same CV, same 300p/100K):
          ladder peak at ws, SVF natural frequency 1.048*ws.
Not representable on the E4's linear stages: OTA tanh, the 2-pole's diode limiter, self-oscillation,
and (until the gain-word units are known) the ladder's 1/(1+k) passband loss.

EOS mapping: stage word = [X_lo F_lo | X_hi F_hi]; pole pairs placed by matched-z; real/low-angle pairs
use F floor 0. Frames: ws_lo / ws_hi chosen so the 2-pole matches the earlier CEM fit (F 8..238).
Peaks are matched to the stock E-mu filters at maximum resonance so the stock gain compensation still fits.

Tables are 32 steps (index = q>>2).   usage: obxa.py [plot.png]
"""
import math, sys
import numpy as np
import eos_filter as ef

FS = ef.FS
KL = 100.0 / 91.0
G = 100.0 / 91.0
F_LO, F_HI = 8, 238
STEPS = 32

# resonance ranges (peak-matched to stock maxima, see main())
Q2_MIN = 0.707
Q2_MAX = 10.0       # 2-pole: max Q
K4_MAX = 3.971      # 4-pole: max loop gain (4.0 = oscillation); peak-matched to stock LP4
LP6_CAP = 30         # 6-pole: table index capped at 30 (peak-matched to stock LP6)


def f_of(F):
    return 9824.0 * 2.0 ** ((F - 215.0) / 32.0)


def F_of(hz):
    return 215.0 + 32.0 * math.log2(hz / 9824.0)


WS_LO = f_of(F_LO) / math.sqrt(KL)
WS_HI = f_of(F_HI) / math.sqrt(KL)


def q_of_step(i):
    return min(127, 4 * i + 2)


def svf_Q(q):
    d0, dmin = math.sqrt(KL) / Q2_MIN, math.sqrt(KL) / Q2_MAX
    return math.sqrt(KL) / (d0 - (d0 - dmin) * q / 127.0)


def ladder_k(q):
    return K4_MAX * q / 127.0


def s_to_half(sigma, omega):
    """s-plane pole (rad/s) -> (X, F) with matched-z; F floored at 0 for near-real poles."""
    r = math.exp(sigma / FS)
    th = omega / FS
    X = 255 + 16 * math.log2(max(1e-12, 1 - r))
    F = F_of(th * FS / (2 * math.pi)) if th > 0 else -1e9
    return X, max(0.0, F)


def svf_poles(ws, Q):
    w0 = 2 * math.pi * ws * math.sqrt(KL)
    return [(-w0 / (2 * Q), w0 * math.sqrt(max(0.0, 1 - 1 / (4 * Q * Q))))]


def ladder_poles(ws, k):
    w = 2 * math.pi * ws
    c = k ** 0.25
    a = c / math.sqrt(2)
    return [(w * (-1 + a), w * a), (w * (-1 - a), w * a)]   # resonant pair A, damped pair B


def clamp(v):
    return max(0, min(255, int(round(v))))


def word(pole_lo, pole_hi):
    xl, fl = s_to_half(*pole_lo)
    xh, fh = s_to_half(*pole_hi)
    return (clamp(xl) << 24) | (clamp(fl) << 16) | (clamp(xh) << 8) | clamp(fh)


HI_CLAMP = True   # v2: keep the top of the range out of the region where the E4 ran away (2026-10-17)
HI_MODE = 'truncate'   # 'truncate': cut each pole line at F_CAP (full Q kept)
                       # 'stock'   : high frame never sharper than stock RES16 (Q tapers to stock)
F_CAP = 210            # hardware-clean up to F ~213-219 at every Q tested (notes/burst_investigation.md)


def clamp_high(w, i):
    if not HI_CLAMP:
        return w
    xl, fl = (w >> 24) & 0xff, (w >> 16) & 0xff
    xh, fh = (w >> 8) & 0xff, w & 0xff
    if HI_MODE == 'stock':
        s = ef.RES16[min(15, i >> 1)]
        xh, fh = max(xh, (s >> 8) & 0xff), min(fh, s & 0xff)
    elif fh > F_CAP:
        t = (F_CAP - fl) / (fh - fl) if fh != fl else 1.0
        xh = int(round(xl + (xh - xl) * t))
        fh = F_CAP
    return (w & 0xffff0000) | (max(0, min(255, xh)) << 8) | fh


VERSION = '3c'  # 2: v2 (burned 2026-10-17); 3: v3b (calibrated, boundary-safe); '3c': v3b + stock blend at low Q


# ---------------- v3 ----------------
KMIN = 0.02            # keep ladder poles slightly complex so their angle (F) can track frequency
X_DAMPED = 240         # high-frame halves with X >= this (r <= ~0.5) may use the full F range


def disp_hz(v):
    """EOS LP frequency display (FilterShared_formatParam_65d24)."""
    d, p = 255 - v, 0x4E20
    if d > 0:
        if d & 1:
            p, d = 0x4C72, d - 1
        for _ in range(d // 2):
            p = (p * 0x3EA) // 0x400
            p = (p * 0x3EA) // 0x400
    return float(p)


D_LO, D_HI = disp_hz(0), disp_hz(255)


def F_cal(hz):
    return ef.F_REF + ef.F_PER_OCT * math.log2(hz / ef.F_REF_HZ)


def s_to_half_cal(sigma, omega):
    r = math.exp(sigma / FS)
    X = 255 + 16 * math.log2(max(1e-12, 1 - r))
    F = F_cal(omega / (2 * math.pi)) if omega > 0 else -1e9
    return X, max(0.0, F)


def word_cal(pole_lo, pole_hi):
    xl, fl = s_to_half_cal(*pole_lo)
    xh, fh = s_to_half_cal(*pole_hi)
    return (clamp(xl) << 24) | (clamp(fl) << 16) | (clamp(xh) << 8) | clamp(fh)


def ladder_r3(k):
    """-3 dB frequency of the DC-normalised ladder (1+k)/((1+p)^4+k), relative to ws."""
    w = np.linspace(0.01, 3, 6000)
    p = 1j * w
    h = np.abs((1 + k) / ((1 + p) ** 4 + k))
    below = np.where(h < 10 ** (-3 / 20))[0]
    return float(w[below[0]]) if len(below) else 1.0


def ladder_scale(k):
    """ws = display * scale: -3 dB on the display at k=0, peak (at ws) on the display at k=K4_MAX."""
    wgt = k / K4_MAX
    return 1.0 / ((1 - wgt) * ladder_r3(k) + wgt)


def top_safe(w, i):
    """High-frame safety: damped poles keep any F; others never sharper/higher than stock RES16 at this
    resonance step - sharper ones are damped back to stock X (frequency tracking kept exact)."""
    xl, fl = (w >> 24) & 0xff, (w >> 16) & 0xff
    xh, fh = (w >> 8) & 0xff, w & 0xff
    if xh >= X_DAMPED:
        return w
    s = ef.RES16[min(15, i >> 1)]
    sx, sfh = (s >> 8) & 0xff, s & 0xff
    xh = max(xh, sx)
    fh = min(fh, max(sfh, 239))
    return (w & 0xffff0000) | (xh << 8) | fh


SAFE_SUM = 568         # v3b: every half must satisfy X + 1.5*F <= SAFE_SUM (stock RES16 top frames lie on
                       # X + 1.5F ~ 566-570; v1/v3 clipped exactly where damped poles sat above that line)
TOP_MODE = 'boundary'  # 'boundary' (v3b) or 'stock_taper' (v3, clipped on hardware 2026-10-17)


def half_safe(x, f):
    if x + 1.5 * f > SAFE_SUM:
        f = int((SAFE_SUM - x) / 1.5)
    return x, max(0, f)


def word_safe(w):
    xl, fl = half_safe((w >> 24) & 0xff, (w >> 16) & 0xff)
    xh, fh = half_safe((w >> 8) & 0xff, w & 0xff)
    return (xl << 24) | (fl << 16) | (xh << 8) | fh


BLEND_Q = (16, 96)     # v3c: ladder rows blend from stock RES16 (q <= 16) to the ladder (q >= 96);
                       # the chip model is wrong for damped near-real poles (measured v3b Q0 4-pole far too
                       # dark), so low resonance uses stock's hardware-proven sections instead


def blend_words(a, b, t):
    """Half-word-wise linear blend of two stage words (t=0 -> a, t=1 -> b)."""
    out = 0
    for sh in (24, 16, 8, 0):
        va, vb = (a >> sh) & 0xff, (b >> sh) & 0xff
        out |= int(round(va + (vb - va) * t)) << sh
    return out


def tables_v3c():
    svf, lada, ladb = tables_v3()
    lo, hi = BLEND_Q
    for i in range(STEPS):
        q = q_of_step(i)
        t = min(1.0, max(0.0, (q - lo) / (hi - lo)))
        s = ef.RES16[min(15, i >> 1)]
        lada[i] = word_safe(blend_words(s, lada[i], t))
        ladb[i] = word_safe(blend_words(s, ladb[i], t))
    return svf, lada, ladb


def tables_v3():
    if TOP_MODE == 'boundary':
        global top_safe
        guard = lambda w, i: word_safe(w)
    else:
        guard = top_safe
    return _tables_v3(guard)


def _tables_v3(top_safe):
    svf, lada, ladb = [], [], []
    for i in range(STEPS):
        q = q_of_step(i)
        Q = svf_Q(q)
        # 2-pole: natural frequency on the display
        lo = svf_poles(D_LO / math.sqrt(KL), Q)[0]
        hi = svf_poles(D_HI / math.sqrt(KL), Q)[0]
        svf.append(top_safe(word_cal(lo, hi), i))
        # ladder: per-row frequency correction
        k = max(KMIN, ladder_k(q))
        sc = ladder_scale(k)
        lo, hi = ladder_poles(D_LO * sc, k), ladder_poles(D_HI * sc, k)
        lada.append(top_safe(word_cal(lo[0], hi[0]), i))
        ladb.append(top_safe(word_cal(lo[1], hi[1]), i))
    return svf, lada, ladb


def tables():
    """32-entry tables: SVF (2-pole), LADA, LADB (4-pole pairs)."""
    if VERSION == 3:
        return tables_v3()
    if VERSION == '3c':
        return tables_v3c()
    svf, lada, ladb = [], [], []
    for i in range(STEPS):
        q = q_of_step(i)
        Q = svf_Q(q)
        svf.append(clamp_high(word(svf_poles(WS_LO, Q)[0], svf_poles(WS_HI, Q)[0]), i))
        k = ladder_k(q)
        lo, hi = ladder_poles(WS_LO, k), ladder_poles(WS_HI, k)
        lada.append(clamp_high(word(lo[0], hi[0]), i))
        ladb.append(clamp_high(word(lo[1], hi[1]), i))
    return svf, lada, ladb


def ladb16(ladb):
    """16-step ladder pair B (index i>>1), sampled at the odd 32-step entries."""
    return [ladb[2 * j + 1] for j in range(16)]


def lp6_index(i):
    """6-pole table index for 32-step index i: same tables, top steps capped (stock also tames the 6-pole)."""
    return min(i, LP6_CAP)


def blocks(q):
    svf, lada, ladb = tables()
    lb = ladb16(ladb)
    i = (q >> 2) & 31
    j = lp6_index(i)
    return {
        2: ef.blk(w0=svf[i]),
        4: ef.blk(w0=lada[i], w4=lb[i >> 1]),
        6: ef.blk(w0=lada[j], w4=lb[j >> 1], w8=svf[j]),
    }


def analog_db(f, ws, poles, q):
    p = 2j * np.pi * f / (2 * math.pi * ws * 2 * math.pi / (2 * math.pi))  # s/ws (ws in Hz)
    p = 1j * f / ws
    h2 = KL / (p * p + (math.sqrt(KL) / svf_Q(q)) * p + KL)
    h4 = 1 / ((1 + p) ** 4 + ladder_k(q))
    h4 = h4 * (1 + ladder_k(q))          # DC-normalised (passband loss not reproduced)
    if poles == 2:
        h = h2
    elif poles == 4:
        h = h4
    else:
        q6 = q_of_step(lp6_index(q >> 2))
        h = (1 + ladder_k(q6)) / ((1 + p) ** 4 + ladder_k(q6)) * \
            KL / (p * p + (math.sqrt(KL) / svf_Q(q6)) * p + KL)
    return 20 * np.log10(np.abs(h))


def peak(block, m):
    f, db = ef.response(block, m)
    return db.max() - db[0]


def stock_block(poles, q):
    if poles == 6:
        q = q - (q >> 2)
    return ef.lp(poles, q)


def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    print('peak above passband at max resonance (model), morph 0.25 / 0.75:')
    for poles in (2, 4, 6):
        s = [peak(stock_block(poles, 127), m) for m in (.25, .75)]
        n = [peak(blocks(127)[poles], m) for m in (.25, .75)]
        print(f'  LP{poles}: stock {s[0]:5.1f} / {s[1]:5.1f} dB   OB-Xa {n[0]:5.1f} / {n[1]:5.1f} dB')
    svf, lada, ladb = tables()
    for name, t in (('SVF', svf), ('LADA', lada), ('LADB', ladb)):
        print(f'{name}: ' + ' '.join(f'{w:08X}' for w in t))

    fig, axes = plt.subplots(3, 3, figsize=(15, 11))
    for col, poles in enumerate((2, 4, 6)):
        for row, q in enumerate((0, 64, 127)):
            ax = axes[row][col]
            for m, c in zip((0.0, 0.3, 0.6, 0.9), plt.cm.viridis(np.linspace(0, .9, 4))):
                Fm = F_LO + (F_HI - F_LO) * m
                ws = f_of(Fm) / math.sqrt(KL)
                f, db = ef.response(blocks(q)[poles], m)
                ax.semilogx(f, db - db[0], color=c, lw=1.6)
                ax.semilogx(f, analog_db(f, ws, poles, q), color=c, lw=.8, ls='--')
                fs_, dbs = ef.response(stock_block(poles, q), m)
                ax.semilogx(fs_, dbs - dbs[0], color=c, lw=.7, ls=':')
            ax.set_title(f'{poles}-pole, resonance {q}', fontsize=9)
            ax.set_ylim(-80, 45 if poles > 2 else 25); ax.set_xlim(20, FS / 2)
            ax.grid(True, which='both', alpha=.3)
    fig.suptitle('OB-Xa CEM3320 on E4 stages — solid: E4 fit, dashed: analog (DC-normalised), dotted: stock E-mu',
                 fontsize=10)
    fig.tight_layout()
    out = sys.argv[1] if len(sys.argv) > 1 else 'obxa_fit.png'
    fig.savefig(out, dpi=100)
    print('wrote', out)


if __name__ == '__main__':
    main()
