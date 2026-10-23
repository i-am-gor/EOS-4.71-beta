#!/usr/bin/env python3
"""Stock EOS 4.70 filters against EOS 4.71-beta2.

Inputs: simulated grids (sim_filters.py: recordings/sim_stock.json, sim_beta2.json), the beta2 hardware grid
(filter_fr_merge.py: recordings/fr_beta2_merged/bands.json) and the stock hardware takes
(recordings/stock_measured_bands.json: cutoffs 48/96/144/192/240/255, Q 0/127, tags like 2pole_q0_f48).

Per filter type:
  OUT/<type>_stock_vs_beta2.png  beta2 measured (solid) and stock simulated (dashed), cutoffs 16/64/128/192,
                                 Q 0/48/96/127, passband-aligned (the simulation has no absolute level)
  report: simulated (like for like) resonance peak above the passband at Q 127, peak frequency vs the displayed
  cutoff, largest single step in peak height between neighbouring Q values; measured stock vs measured beta2 at
  the shared settings: passband, peak, max THD where the response is within 30 dB of its peak, max output peak.

usage: stock_vs_beta2.py OUTDIR
"""
import json, math, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hw_freqresp import disp_hz      # noqa: E402
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt       # noqa: E402

TYPES = ['2pole', '4pole', '6pole', 'hp2', 'hp4', 'bp2', 'bp4', 'cbp']
QS = list(range(0, 113, 8)) + [127]
CUTS = list(range(0, 241, 16))
LOWPASS = {'2pole', '4pole', '6pole'}


def lv(b):
    return {x['f']: x['level'] for x in b}


def align(t, s, ref_f):
    """Shift s so its median over the reference band matches."""
    fs = [f for f in s if f in ref_f]
    return np.median([ref_f[f] - s[f] for f in fs])


def features(typ, b):
    f = np.array(sorted(b)); v = np.array([b[x] for x in f])
    if typ in LOWPASS:
        base = float(np.median(v[f <= 80]))
    elif typ in ('hp2', 'hp4'):
        base = float(np.median(v[f >= 6000]))
    else:
        base = None
    i = int(np.argmax(v))
    return dict(peak=float(v[i]), f_peak=int(f[i]), rise=None if base is None else float(v[i] - base))


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    ss = json.load(open('recordings/sim_stock.json'))['bands']
    sb = json.load(open('recordings/sim_beta2.json'))['bands']
    mb = json.load(open('recordings/fr_beta2_merged/bands.json'))
    ms = json.load(open('recordings/stock_measured_bands.json'))
    lines = []
    for typ in TYPES:
        have_meas = any(t.startswith(typ + '_c') for t in mb)
        # ---- simulated, like for like ----
        rows = []
        for c in (16, 64, 128, 192):
            r = {}
            for name, src in (('stock', ss), ('beta2', sb)):
                fe = features(typ, lv(src[f'{typ}_c{c}_q127']))
                steps = [features(typ, lv(src[f'{typ}_c{c}_q{q}']))['peak'] for q in QS]
                r[name] = (fe, max(abs(a - b_) for a, b_ in zip(steps[1:], steps[:-1])))
            rows.append((c, r))
        lines.append(f'## {typ}  (simulated, Q 127; displayed cutoff in Hz)')
        for c, r in rows:
            st, bt = r['stock'], r['beta2']
            rs = '' if st[0]['rise'] is None else f"resonance {st[0]['rise']:+.1f} -> {bt[0]['rise']:+.1f} dB, "
            lines.append(f"  cut {c:3d} ({disp_hz(c):5d} Hz): {rs}peak at {st[0]['f_peak']} -> {bt[0]['f_peak']} Hz, "
                         f"largest Q step {st[1]:.1f} -> {bt[1]:.1f} dB")
        # ---- measured stock vs measured beta2 ----
        if have_meas:
            lines.append('  measured (stock -> beta2): cut, Q: passband/peak dB, max THD dB, max output peak dBFS')
            for c in (48, 96, 144, 192, 240):
                for q in (0, 127):
                    ts, tb = f'{typ}_q{q}_f{c}', f'{typ}_c{c}_q{q}'
                    if ts not in ms or tb not in mb:
                        continue
                    a, b_ = ms[ts], mb[tb]
                    va, vb = lv(a), lv(b_)

                    def thd(bs, v):
                        mx = max(v.values())
                        x = [z['thd'] for z in bs if v[z['f']] > mx - 30 and 60 <= z['f'] <= 8000]
                        return max(x) if x else float('nan')
                    lines.append(f"    {c:3d} q{q:<3d}: peak {max(va.values()):+.1f} -> {max(vb.values()):+.1f} dB, "
                                 f"THD {thd(a, va):.0f} -> {thd(b_, vb):.0f} dB, "
                                 f"out peak {max(z['peak'] for z in a):.1f} -> {max(z['peak'] for z in b_):.1f}")
        # ---- plot ----
        fig, axs = plt.subplots(1, 4, figsize=(18, 4.2), sharey=True)
        cmap = plt.get_cmap('viridis')
        for k, c in enumerate((16, 64, 128, 192)):
            ax = axs[k]
            for j, q in enumerate((0, 48, 96, 127)):
                col = cmap(j / 3)
                s = lv(ss[f'{typ}_c{c}_q{q}'])
                tb = f'{typ}_c{c}_q{q}'
                if tb in mb:
                    m = lv(mb[tb]); off = align(tb, s, m)
                    ax.semilogx(sorted(m), [m[f] for f in sorted(m)], '-', color=col, lw=1.4, label=f'beta2 meas Q {q}')
                else:
                    off = 0.0
                ax.semilogx(sorted(s), [s[f] + off for f in sorted(s)], '--', color=col, lw=1.1, label=f'stock sim Q {q}')
            ax.set_title(f'cutoff {c} ({disp_hz(c)} Hz)', fontsize=9); ax.grid(True, which='both', alpha=0.3)
            ax.set_xlim(40, 12000); ax.set_ylim(-60, 50); ax.set_xlabel('Hz')
        axs[0].set_ylabel('dB'); axs[0].legend(fontsize=6.5, ncol=2)
        fig.suptitle(f'{typ}: EOS 4.71-beta2 measured (solid) vs stock EOS 4.70 simulated (dashed, passband-aligned)')
        fig.tight_layout(); fig.savefig(os.path.join(out, f'{typ}_stock_vs_beta2.png'), dpi=105); plt.close(fig)
    open(os.path.join(out, 'stock_vs_beta2.txt'), 'w').write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
