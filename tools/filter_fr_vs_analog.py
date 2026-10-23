#!/usr/bin/env python3
"""Measured E4 filter responses (hw_filter_fr.py + filter_fr_report.py bands.json) against analog OB-Xa circuit
models, since no measured response of a real OB-Xa has been published.

Models (normalised frequency x = f / fc):
  4 Pole Lowpass (menu 1): the OB-Xa's CEM3320 4-pole cascade with resonance feedback k (0..4, oscillation at 4):
      H = 1 / ((1 + jx)^4 + k)  -> 24 dB/oct, peak at fc, passband (bass) level 1 / (1 + k)
  2 Pole Lowpass (menu 0): the OB-Xa's 2-pole state-variable lowpass with quality factor Qa:
      H = 1 / (1 - x^2 + jx / Qa)  -> 12 dB/oct, passband 0 dB, peak about Qa
Each measured curve is fitted (fc, resonance, overall gain) by least squares over bands within 45 dB of its maximum
(40 Hz .. 10 kHz). Writes OUTDIR/<type>_vs_analog.png and OUTDIR/vs_analog.json: fitted values, RMS misfit,
measured slope one to two octaves above the cutoff, and passband (bass) change versus Q 0.

usage: filter_fr_vs_analog.py OUTDIR
"""
import json, math, os, sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt   # noqa: E402


def h4(x, k):
    return 20 * np.log10(np.abs(1 / ((1 + 1j * x) ** 4 + k)))


def h2(x, qa):
    return 20 * np.log10(np.abs(1 / (1 - x ** 2 + 1j * x / qa)))


MODELS = {'4pole': ('CEM3320 4-pole cascade, feedback k', h4, np.linspace(0, 3.95, 80), 'k'),
          '2pole': ('OB-Xa 2-pole SVF, quality Qa', h2, np.geomspace(0.5, 40, 80), 'Qa')}


def fit(f, lv, model):
    _, fn, rgrid, _ = model
    m = (lv > lv.max() - 45) & (f >= 40) & (f <= 10000)
    best = None
    for fc in np.geomspace(20, 20000, 160):
        x = f[m] / fc
        for r in rgrid:
            mod = fn(x, r)
            g = np.mean(lv[m] - mod)
            e = math.sqrt(np.mean((lv[m] - mod - g) ** 2))
            if best is None or e < best[0]:
                best = (e, fc, r, g)
    return best


def slope(f, lv, fc):
    a, b = fc * 2, fc * 4
    if b > 10000:
        return None
    return float(np.interp(b, f, lv) - np.interp(a, f, lv))


def main():
    d = sys.argv[1]
    bands = json.load(open(os.path.join(d, 'bands.json')))
    log = json.load(open(os.path.join(d, 'log.json')))
    ref = {b['f']: b['level'] for b in bands['ref_start']}
    out = {}
    for t, model in MODELS.items():
        rows = [r for r in log if r['tag'].startswith(t + '_c')]
        if not rows:
            continue
        cuts = sorted({r['cut'] for r in rows}); qs = sorted({r['q'] for r in rows})
        fig, axs = plt.subplots(1, len(cuts), figsize=(5.2 * len(cuts), 4.2), sharey=True, squeeze=False)
        cmap = plt.get_cmap('viridis')
        for i, c in enumerate(cuts):
            ax = axs[0][i]
            base = None
            for j, q in enumerate(qs):
                tag = f'{t}_c{c}_q{q}'
                if tag not in bands:
                    continue
                b = bands[tag]
                f = np.array([x['f'] for x in b], float)
                lv = np.array([x['level'] - ref.get(x['f'], 0) for x in b])
                e, fc, r, g = fit(f, lv, model)
                col = cmap(j / max(1, len(qs) - 1))
                ff = np.geomspace(40, 12000, 300)
                ax.semilogx(f, lv, 'o-', color=col, ms=3, lw=1.2, label=f'Q {q}: {model[3]} {r:.2f}, rms {e:.1f} dB')
                ax.semilogx(ff, model[1](ff / fc, r) + g, '--', color=col, lw=0.9, alpha=0.8)
                low = float(np.interp(100, f, lv))
                if base is None:
                    base = low
                out[tag] = dict(fc_fit=round(float(fc)), res_fit=round(float(r), 3), rms_db=round(e, 2),
                                slope_db_per_oct=None if slope(f, lv, fc) is None else round(slope(f, lv, fc), 1),
                                bass_change_db=round(low - base, 1),
                                model_bass_change_db=round(-20 * math.log10(1 + r), 1) if t == '4pole' else 0.0)
            ax.set_title(f'cutoff {c}', fontsize=9); ax.grid(True, which='both', alpha=0.3)
            ax.set_xlim(40, 12000); ax.set_ylim(-60, 45); ax.legend(fontsize=6.5, loc='lower left')
            ax.set_xlabel('Hz')
        axs[0][0].set_ylabel('dB re flat reference')
        fig.suptitle(f'{t}: E4 measurement (solid) vs analog model {model[0]} (dashed, fitted)')
        fig.tight_layout(); fig.savefig(os.path.join(d, f'{t}_vs_analog.png'), dpi=110); plt.close(fig)
    json.dump(out, open(os.path.join(d, 'vs_analog.json'), 'w'), indent=1)
    for k, v in out.items():
        print(k, v)


if __name__ == '__main__':
    main()
