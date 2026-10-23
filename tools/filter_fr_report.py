#!/usr/bin/env python3
"""Plots and anomaly checks for hw_filter_fr.py takes (sine-sweep sample on the E4).

Each take is analysed per 1/3 octave with lpfuzz_fr_analyze.analyse (fundamental level, THD of harmonics 2..10,
frame peak). Responses are shown relative to the flat Swept-EQ reference (ref_start). Per filter type:
  <type>_response.png  one panel per cutoff, a curve per Q (level re reference, dB)
  <type>_thd.png       THD (dB re fundamental) per cutoff x Q at 125 Hz / 500 Hz / 2 kHz / 8 kHz, and peak dBFS
Checks (printed and saved in report.json):
  - reference drift (ref_start vs ref_end)
  - THD above -30 dB where the filter should be clean (LP+Fuzz Q 0; other types any Q)
  - spikes: a band more than 6 dB above both neighbours where the response should be smooth
  - Q steps: the response at a fixed cutoff must change monotonically in peak height as Q rises

usage: filter_fr_report.py OUTDIR [OUTDIR ...]
"""
import json, math, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lpfuzz_fr_analyze as A     # noqa: E402

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt   # noqa: E402

TITLES = {'2pole': '2 Pole Lowpass (OB-Xa SVF)', '4pole': '4 Pole Lowpass (OB-Xa ladder)',
          '6pole': '6 Pole Lowpass', 'hp2': '2nd Order High-pass', 'hp4': '4th Order High-pass',
          'bp2': '2nd Order Band-pass', 'bp4': '4th Order Band-pass', 'cbp': 'Contrary Band-pass',
          'lpfuzz': '4 Pole LP+Fuzz'}


def load(d):
    log = json.load(open(os.path.join(d, 'log.json')))
    cache = os.path.join(d, 'bands.json')
    have = json.load(open(cache)) if os.path.exists(cache) else {}
    s = A.ideal()
    for r in log:
        if r['tag'] not in have:
            have[r['tag']] = A.analyse(np.load(os.path.join(d, r['tag'] + '.npy')), s)
    json.dump(have, open(cache, 'w'))
    return log, have


def main():
    for d in sys.argv[1:]:
        log, bands = load(d)
        ref = {b['f']: b['level'] for b in bands['ref_start']}
        issues = []
        if 'ref_end' in bands:
            drift = max(abs(a['level'] - b['level']) for a, b in zip(bands['ref_start'], bands['ref_end'])
                        if 100 <= a['f'] <= 8000)
            issues.append(f'reference drift start->end: {drift:.2f} dB (100 Hz-8 kHz)')
        types = sorted({r['tag'].rsplit('_c', 1)[0] for r in log if '_c' in r['tag']})
        summary = {}
        for t in types:
            rows = [r for r in log if r['tag'].startswith(t + '_c')]
            cuts = sorted({r['cut'] for r in rows}); qs = sorted({r['q'] for r in rows})
            fig, axs = plt.subplots(int(math.ceil(len(cuts) / 3)), 3, figsize=(15, 3.4 * math.ceil(len(cuts) / 3)),
                                    sharey=True, squeeze=False)
            cmap = plt.get_cmap('viridis')
            for i, c in enumerate(cuts):
                ax = axs[i // 3][i % 3]
                prev_pk = None
                for j, q in enumerate(qs):
                    tag = f'{t}_c{c}_q{q}'
                    if tag not in bands:
                        continue
                    b = bands[tag]
                    f = np.array([x['f'] for x in b]); lv = np.array([x['level'] - ref.get(x['f'], 0) for x in b])
                    ax.semilogx(f, lv, color=cmap(j / max(1, len(qs) - 1)), lw=1.2, label=f'Q {q}')
                    clean = not (t == 'lpfuzz' and q > 0)
                    for x in b:
                        if clean and x['thd'] > -30 and 60 <= x['f'] <= 6000 and x['level'] - ref.get(x['f'], 0) > -30:
                            issues.append(f'{tag}: THD {x["thd"]} dB at {x["f"]} Hz (expected clean)')
                    for k in range(1, len(lv) - 1):
                        if lv[k] - max(lv[k - 1], lv[k + 1]) > 6 and lv[k] > -40:
                            issues.append(f'{tag}: spike {lv[k] - max(lv[k-1], lv[k+1]):.1f} dB at {f[k]} Hz')
                    pk = float(lv.max())
                    if prev_pk is not None and t != 'lpfuzz' and pk < prev_pk - 1.0:
                        issues.append(f'{t} cut {c}: peak falls {prev_pk:.1f} -> {pk:.1f} dB from Q {qs[j-1]} to Q {q}')
                    prev_pk = pk
                    summary[tag] = dict(peak_db=round(pk, 1), f_peak=int(f[int(np.argmax(lv))]),
                                        thd_max=max(x['thd'] for x in b if x['level'] - ref.get(x['f'], 0) > -30) if
                                        any(x['level'] - ref.get(x['f'], 0) > -30 for x in b) else None)
                ax.set_title(f'cutoff {c}', fontsize=9); ax.grid(True, which='both', alpha=0.3)
                ax.set_xlim(40, 13000); ax.set_ylim(-60, 45)
            for k in range(len(cuts), axs.size):
                axs.flat[k].axis('off')
            axs[0][0].legend(fontsize=7, ncol=2)
            for ax in axs[-1]:
                ax.set_xlabel('Hz')
            for ax in axs[:, 0]:
                ax.set_ylabel('dB re flat reference')
            fig.suptitle(f'{TITLES.get(t, t)}: measured on the E4 (EOS 4.71-beta2), sine-sweep sample')
            fig.tight_layout(); fig.savefig(os.path.join(d, f'{t}_response.png'), dpi=110); plt.close(fig)
            # THD map
            fs_ = (125, 500, 2000, 8000)
            fig, axs = plt.subplots(1, len(fs_) + 1, figsize=(18, 3.6))
            for k, fx in enumerate(fs_ + ('peak',)):
                M = np.full((len(qs), len(cuts)), np.nan)
                for a_, q in enumerate(qs):
                    for b_, c in enumerate(cuts):
                        tag = f'{t}_c{c}_q{q}'
                        if tag in bands:
                            x = min(bands[tag], key=lambda z: abs(z['f'] - (fx if fx != 'peak' else 1000)))
                            M[a_, b_] = x['thd'] if fx != 'peak' else max(z['peak'] for z in bands[tag])
                im = axs[k].imshow(M, origin='lower', aspect='auto', cmap='magma',
                                   vmin=(-60 if fx != 'peak' else -60), vmax=(0 if fx != 'peak' else -20))
                axs[k].set_xticks(range(len(cuts)), cuts, fontsize=7); axs[k].set_yticks(range(len(qs)), qs, fontsize=7)
                axs[k].set_xlabel('cutoff'); axs[k].set_title(f'THD dB at {fx} Hz' if fx != 'peak' else 'max frame peak dBFS', fontsize=9)
                plt.colorbar(im, ax=axs[k])
            axs[0].set_ylabel('Q')
            fig.suptitle(f'{TITLES.get(t, t)}: distortion (harmonics 2-10 re fundamental) and peak level')
            fig.tight_layout(); fig.savefig(os.path.join(d, f'{t}_thd.png'), dpi=110); plt.close(fig)
        json.dump(dict(issues=issues, summary=summary), open(os.path.join(d, 'report.json'), 'w'), indent=1)
        print(f'{d}: {len(summary)} takes, {len(issues)} findings')
        for s in issues[:60]:
            print('  ' + s)


if __name__ == '__main__':
    main()
