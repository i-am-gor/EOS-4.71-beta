#!/usr/bin/env python3
"""A/B: the 6 s sweep (key 81) against the 20 s sweep (key 77) on the same filter settings.

Both takes are analysed with lpfuzz_fr_analyze.analyse (T = 6 or 20), relative to their own flat Swept-EQ
reference. Per setting: largest level difference over 1/3-octave bands 50 Hz .. 10 kHz (bands within 40 dB of
the response peak), peak height and frequency, THD difference where the fundamental is within 30 dB of the peak,
and the maximum frame peak (clipping). Writes OUT.png with both responses per setting.

usage: ab_sweep_compare.py FASTDIR SLOWDIR OUT.png
"""
import json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lpfuzz_fr_analyze as A     # noqa: E402
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt   # noqa: E402


def bands(d, T):
    A.T = T
    s = A.ideal()
    log = json.load(open(os.path.join(d, 'log.json')))
    return {r['tag']: {b['f']: b for b in A.analyse(np.load(os.path.join(d, r['tag'] + '.npy')), s)} for r in log}


def main():
    fd, sd_, png = sys.argv[1:4]
    F, S = bands(fd, 6.0), bands(sd_, 20.0)
    rf, rs = F['ref_end'], S['ref_end']          # ref_start can be low: first take after setup
    tags = [t for t in S if not t.startswith('ref') and t in F]
    fig, axs = plt.subplots(2, (len(tags) + 1) // 2, figsize=(4 * ((len(tags) + 1) // 2), 7), squeeze=False)
    worst = []
    for i, t in enumerate(tags):
        fs = sorted(S[t])
        ls = np.array([S[t][f]['level'] - rs[f]['level'] for f in fs])
        lf = np.array([F[t][f]['level'] - rf[f]['level'] for f in fs])
        m = np.array([50 <= f <= 10000 for f in fs]) & (ls > ls.max() - 40)
        dmax = float(np.abs(lf - ls)[m].max())
        thd = [abs(F[t][f]['thd'] - S[t][f]['thd']) for f, ok in zip(fs, m) if ok and (ls[fs.index(f)] > ls.max() - 30)]
        pk_s, pk_f = float(ls.max()), float(lf.max())
        cs = max(S[t][f]['peak'] for f in fs); cf = max(F[t][f]['peak'] for f in fs)
        line = (f'{t:18s} level diff max {dmax:5.2f} dB | peak {pk_s:6.1f} @ {fs[int(np.argmax(ls))]:>5} Hz (20 s) vs '
                f'{pk_f:6.1f} @ {fs[int(np.argmax(lf))]:>5} Hz (6 s) | THD diff median {np.median(thd) if thd else 0:4.1f}, '
                f'max {max(thd) if thd else 0:4.1f} dB | clip peak {cs:6.1f} vs {cf:6.1f} dBFS')
        print(line); worst.append((dmax, t))
        ax = axs[i % 2][i // 2]
        ax.semilogx(fs, ls, 'k-', lw=1.5, label='20 s sweep'); ax.semilogx(fs, lf, 'r--', lw=1.2, label='6 s sweep')
        ax.set_title(t, fontsize=9); ax.grid(True, which='both', alpha=0.3); ax.set_xlim(40, 12000)
    axs[0][0].legend(fontsize=8)
    fig.suptitle('A/B: 6 s sweep vs 20 s sweep, same filter settings (dB re flat reference)')
    fig.tight_layout(); fig.savefig(png, dpi=105)
    print('worst:', max(worst))


if __name__ == '__main__':
    main()
