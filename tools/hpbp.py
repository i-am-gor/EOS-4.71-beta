#!/usr/bin/env python3
"""OB-Xa high-pass / band-pass tables for EOS 4.70 (replacing 2nd/4th Order High-pass and Band-pass).

Same pole pairs as the OB-Xa lowpasses (tools/obxa.py, v3c): CEM3320 SVF for the 2nd-order filters,
ladder pairs A (resonant) / B (damped) for the 4th-order ones, each calibrated to its own display:
  HP display 18000*(1003/1024)^(255-v)  (FilterShared_formatParam_66178)
  BP display 10000*(1005/1024)^(255-v)  (Filter_ContraryBP_formatParam 0x667A8)
Everything else (zero words, chip mode, gain word, return values) stays stock; the chip's BP mode turns
the pole pairs into band-pass sections, the HP zeros near DC make them high-pass.

Tables per kind: SVF (32 steps, q>>2), LADA (32 steps, q>>2), LADB (HP 8 steps q>>4; BP 16 steps q>>3).
At low resonance the ladder rows blend toward stock RES16 sections re-aimed at the kind's display
(the v3c fix for heavily damped poles), then every half is kept on the X + 1.5F <= 568 boundary.
"""
import math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import obxa              # noqa: E402
import eos_filter as ef  # noqa: E402

NEUTRAL = 0xFFCFFFCF
HP_ZERO = 0x80048004
BP_W01 = 0xFF68FFCF
BP_ZERO = 0xFF04FF90
CBP_ZERO = 0xFFD0FF20
BP4_BOOST = 11          # HPBP6: 4th BP return -(q>>2) + (q*q*11 >> 14): +0 Q0, +2 Q64, +10 Q127 (~1 dB/unit)


def disp(start, ratio, v):
    d, p = 255 - v, start
    if d > 0:
        if d & 1:
            p, d = (p * ratio) // 0x400, d - 1
        for _ in range(d // 2):
            p = (p * ratio) // 0x400
            p = (p * ratio) // 0x400
    return float(p)


DISPLAY = {'HP': (0x4650, 0x3EB), 'BP': (0x2710, 0x3ED)}


def display_range(kind):
    s, r = DISPLAY[kind]
    return disp(s, r, 0), disp(s, r, 255)


def shift_word(w, dlo, dhi):
    xl, fl, xh, fh = (w >> 24) & 255, (w >> 16) & 255, (w >> 8) & 255, w & 255
    fl = min(255, max(0, fl + dlo))
    fh = min(255, max(0, fh + dhi))
    return obxa.word_safe((xl << 24) | (fl << 16) | (xh << 8) | fh)


def stock_bp_word(q):
    """Stock 2nd/4th Order Band-pass pole section at resonance q (Filter_BP4_computeFrames)."""
    h = q >> 1
    return (((0x88 - h) & 255) << 24) | (0x08 << 16) | (((0xF8 - h) & 255) << 8) | 0xC8


def tables(kind):
    """(svf32, lada32, ladb8) for 'HP' or 'BP'."""
    lo, hi = display_range(kind)
    saved = obxa.D_LO, obxa.D_HI
    try:
        obxa.D_LO, obxa.D_HI = lo, hi
        svf, lada, ladb = obxa.tables_v3()
    finally:
        obxa.D_LO, obxa.D_HI = saved
    dlo = round(obxa.F_cal(lo) - obxa.F_cal(saved[0]))
    dhi = round(obxa.F_cal(hi) - obxa.F_cal(saved[1]))
    blo, bhi = obxa.BLEND_Q
    for i in range(obxa.STEPS):
        q = obxa.q_of_step(i)
        t = min(1.0, max(0.0, (q - blo) / (bhi - blo)))
        # low-resonance target: HP -> stock lowpass section re-aimed at the HP display;
        # BP -> E-mu's own band-pass section (measured ~0 dB, centre on the display)
        s = stock_bp_word(q) if kind == 'BP' else shift_word(ef.RES16[min(15, i >> 1)], dlo, dhi)
        lada[i] = obxa.word_safe(obxa.blend_words(s, lada[i], t))
        ladb[i] = obxa.word_safe(obxa.blend_words(s, ladb[i], t))
    svf = [obxa.word_safe(w) for w in svf]
    if kind == 'BP' and os.environ.get('HPBP_DIAG_STOCK_BP4'):
        # diagnostic: 4th BP ladder tables = byte-exact stock BP4 words (exact at q = 0, 64, 127, ...)
        lada = [stock_bp_word(127 if j == 31 else 4 * j) for j in range(32)]
        return svf, lada, [stock_bp_word(127 if k == 15 else 8 * k) for k in range(16)]
    if kind == 'BP':      # BP level is very sensitive to X: 16 steps sampled at the low end of each step
        return svf, lada, [ladb[2 * j] for j in range(16)]
    return svf, lada, [ladb[4 * j + 2] for j in range(8)]


def cbp_table():
    """HPBP6 Contrary BP: OB-Xa SVF F bytes (centre on the BP display) with the stock contrary X law
    (0x88-q low frame, 0xD0-q high frame) for stock-like resonance level (its return is a constant 0)."""
    svf = tables('BP')[0]
    out = []
    for j, w in enumerate(svf):
        q = 127 if j == 31 else 4 * j
        out.append(obxa.word_safe((((0x88 - q) & 255) << 24) | (w & 0x00FF0000) | (((0xD0 - q) & 255) << 8) | (w & 255)))
    return out


def expected_return(kind, poles, q, stock_ret):
    """HPBP6 return value for q (0..255) given stock's."""
    if kind == 'BP' and poles == 4:
        return (stock_ret + ((q * q * BP4_BOOST) >> 14)) & 0xffffffff
    return stock_ret


def expected_block(kind, poles, q):
    """Pole/zero words 0,1,4,5,8 written by the OB-Xa HP/BP computeFrames for resonance q (0..127)."""
    svf, lada, ladb = tables('BP' if kind == 'CBP' else kind)
    a32, b8 = (q >> 2) & 31, ((q >> 3) & 15) if kind == 'BP' else ((q >> 4) & 7)
    if kind == 'HP' and poles == 2:
        return {0: NEUTRAL, 1: HP_ZERO, 4: svf[a32], 5: NEUTRAL, 8: NEUTRAL}
    if kind == 'HP':
        return {0: NEUTRAL, 1: HP_ZERO, 4: lada[a32], 5: HP_ZERO, 8: ladb[b8]}
    if kind == 'CBP':
        return {0: cbp_table()[a32], 1: NEUTRAL, 4: NEUTRAL, 5: CBP_ZERO, 8: NEUTRAL}
    if poles == 2:
        return {0: BP_W01, 1: BP_W01, 4: NEUTRAL, 5: BP_ZERO, 8: svf[a32]}
    return {0: lada[a32], 1: BP_ZERO, 4: NEUTRAL, 5: BP_ZERO, 8: ladb[b8]}


def check():
    for kind in ('HP', 'BP'):
        lo, hi = display_range(kind)
        svf, lada, ladb = tables(kind)
        bad = [(n, i) for n, t in (('svf', svf), ('lada', lada), ('ladb', ladb)) for i, w in enumerate(t)
               for x, f in (((w >> 24) & 255, (w >> 16) & 255), ((w >> 8) & 255, w & 255)) if x + 1.5 * f > obxa.SAFE_SUM]
        print(f'{kind}: display {lo:.0f}-{hi:.0f} Hz; svf[0] {svf[0]:08X} svf[31] {svf[31]:08X} '
              f'lada[0] {lada[0]:08X} lada[31] {lada[31]:08X} ladb {ladb[0]:08X}..{ladb[7]:08X}; boundary violations {bad}')


if __name__ == '__main__':
    check()
