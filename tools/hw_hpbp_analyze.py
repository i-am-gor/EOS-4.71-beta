#!/usr/bin/env python3
"""Analyse high-pass / band-pass sweep grids recorded by hw_freqresp.py (types 3-6).

usage: hw_hpbp_analyze.py OUTDIR LABEL
HP: passband = median 6-12 kHz; -3 dB corner searched downward; slope 2-4 octaves below the corner.
BP: centre = peak; -3 dB bandwidth; slopes one-to-two octaves either side of the centre.
Display Hz per class: HP 18000*(1003/1024)^(255-v), BP 10000*(1005/1024)^(255-v) (stock formatParam).
"""
import json, math, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hw_freqresp as fr          # noqa: E402


def disp(start, ratio, v):
    d, p = 255 - v, start
    if d > 0:
        if d & 1:
            p, d = (p * ratio) // 0x400, d - 1
        for _ in range(d // 2):
            p = (p * ratio) // 0x400
            p = (p * ratio) // 0x400
    return p


def disp_hp(v):
    return disp(0x4650, 0x3EB, v)


def disp_bp(v):
    return disp(0x2710, 0x3ED, v)


def main():
    out, label = sys.argv[1:3]
    log = json.load(open(os.path.join(out, f'{label}_log.json')))
    ld = lambda t: np.load(os.path.join(out, f'{label}_{t}.npy'))
    ref = ld('ref_start')
    f, drift = fr.response(ld('ref_end'), ref)
    print(f'reference drift start->end: max |dB| {np.abs(drift[(f > 40) & (f < 16000)]).max():.2f}')
    rows, curves = [], {}
    band = (f > 30) & (f < 16000)
    for r in log:
        if r['tag'].startswith('ref'):
            continue
        _, H = fr.response(ld(r['tag']), ref)
        curves[r['tag']] = H
        kind = r['tag'][:2]
        pk = int(np.argmax(np.where(band, H, -999)))
        row = dict(tag=r['tag'], type=r['type'], freq=r['freq'], q=r['q'], peak_hz=round(float(f[pk])),
                   peak_db=round(float(H[pk]), 1))
        if kind == 'hp':
            ref_db = float(np.median(H[(f > 6000) & (f < 12000)]))
            idx = np.where(band & (H < ref_db - 3) & (f < 6000))[0]
            fc = float(f[idx[-1]]) if len(idx) else float('nan')
            slope = float('nan')
            if not math.isnan(fc) and fc / 16 > 25:
                i1, i2 = np.argmin(abs(f - fc / 4)), np.argmin(abs(f - fc / 16))
                slope = (H[i1] - H[i2]) / 2.0
            row.update(display_hz=disp_hp(r['freq']), passband_db=round(ref_db, 1),
                       corner_hz=None if math.isnan(fc) else round(fc), peak_over_pass_db=round(float(H[pk] - ref_db), 1),
                       slope_db_oct=None if math.isnan(slope) else round(slope, 1))
        else:
            lo = np.where(band & (np.arange(len(f)) < pk) & (H < H[pk] - 3))[0]
            hi = np.where(band & (np.arange(len(f)) > pk) & (H < H[pk] - 3))[0]
            f1 = float(f[lo[-1]]) if len(lo) else float('nan')
            f2 = float(f[hi[0]]) if len(hi) else float('nan')
            def sl(a, b):
                ia, ib = np.argmin(abs(f - a)), np.argmin(abs(f - b))
                return (H[ia] - H[ib])
            fc = float(f[pk])
            s_lo = sl(fc / 2, fc / 4) if fc / 4 > 25 else float('nan')
            s_hi = sl(fc * 2, fc * 4) if fc * 4 < 16000 else float('nan')
            row.update(display_hz=disp_bp(r['freq']), bw_oct=None if math.isnan(f1) or math.isnan(f2) else round(math.log2(f2 / f1), 2),
                       slope_lo_db_oct=None if math.isnan(s_lo) else round(s_lo, 1),
                       slope_hi_db_oct=None if math.isnan(s_hi) else round(s_hi, 1))
        rows.append(row)
    json.dump(dict(f=list(map(float, f)), curves={k: list(map(float, v)) for k, v in curves.items()}),
              open(os.path.join(out, f'{label}_curves.json'), 'w'))
    json.dump(rows, open(os.path.join(out, f'{label}_summary.json'), 'w'), indent=1)
    for r in rows:
        if r['tag'].startswith('hp'):
            print(f"{r['tag']:16s} disp {r['display_hz']:6d}  corner {str(r['corner_hz']):>6s}  pass {r['passband_db']:6.1f}  "
                  f"peak {r['peak_hz']:6d} Hz {r['peak_over_pass_db']:+5.1f} dB  slope {r['slope_db_oct']}")
        else:
            print(f"{r['tag']:16s} disp {r['display_hz']:6d}  centre {r['peak_hz']:6d}  level {r['peak_db']:6.1f}  "
                  f"bw {r['bw_oct']} oct  slopes {r['slope_lo_db_oct']} / {r['slope_hi_db_oct']} dB/oct")
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    kinds = sorted({k.split('_')[0] for k in curves})
    fig, axes = plt.subplots(len(kinds), 2, figsize=(14, 3.6 * len(kinds)), sharex=True, squeeze=False)
    for i, kd in enumerate(kinds):
        for j, q in enumerate(sorted({int(k.split('_q')[1].split('_')[0]) for k in curves})[:2]):
            ax = axes[i][j]
            for k, H in curves.items():
                if k.startswith(f'{kd}_q{q}_'):
                    ax.semilogx(f, H, lw=1, label=k.split('_')[-1])
            ax.set_title(f'{label}: {kd} Q {q}', fontsize=9); ax.grid(True, which='both', alpha=.3)
            ax.set_ylim(-80, 30); ax.legend(fontsize=7, ncol=3)
    fig.tight_layout(); fig.savefig(os.path.join(out, f'{label}_responses.png'), dpi=85)


if __name__ == '__main__':
    main()
