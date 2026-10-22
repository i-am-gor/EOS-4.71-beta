#!/usr/bin/env python3
"""Analyse hw_lpfuzz_fr.py takes (sine-sweep sample, key 77: 20 s log sweep 20 Hz-20 kHz) per frequency.

Each take is aligned to the ideal log sweep (cross-correlation), then an STFT tracks the instantaneous sweep
frequency f(t): fundamental level (energy within +-1/12 octave of f), harmonics 2..10 (below 22 kHz) -> THD, and the
frame peak (clip ceiling ~ -23.6 dBFS). Reported per 1/3-octave band 40 Hz .. 12.5 kHz. Writes OUTDIR/analysis.json
and OUTDIR/analysis.png.

usage: lpfuzz_fr_analyze.py OUTDIR
"""
import json, math, os, sys
import numpy as np

FS, T, F1, F2 = 48000, 20.0, 20.0, 20000.0
K = math.log(F2 / F1)
BANDS = [40 * 2 ** (i / 3) for i in range(26) if 40 * 2 ** (i / 3) <= 12600]
NFFT, HOP = 4096, 1024


def ideal():
    t = np.arange(int(T * FS)) / FS
    return np.sin(2 * np.pi * F1 * T / K * (np.exp(t * K / T) - 1))


def onset(x, s):
    n = 1 << int(math.ceil(math.log2(len(x) + len(s))))
    c = np.fft.irfft(np.fft.rfft(x, n) * np.conj(np.fft.rfft(s, n)), n)
    return int(np.argmax(np.abs(c[:len(x)])))


def analyse(x, s):
    t0 = onset(x, s)
    win = np.hanning(NFFT)
    fb = np.fft.rfftfreq(NFFT, 1 / FS)
    rows = []
    for st in range(t0, t0 + int(T * FS) - NFFT, HOP):
        tc = (st - t0 + NFFT / 2) / FS
        f = F1 * math.exp(tc * K / T)
        seg = x[st:st + NFFT]
        if len(seg) < NFFT:
            break
        S = np.abs(np.fft.rfft(seg * win)) ** 2

        def band(fc):
            m = (fb > fc * 2 ** (-1 / 12)) & (fb < fc * 2 ** (1 / 12))
            return S[m].sum()
        fund = band(f)
        harm = sum(band(f * k) for k in range(2, 11) if f * k < 22000)
        rows.append((f, 10 * math.log10(fund + 1e-20), 10 * math.log10(harm / (fund + 1e-20) + 1e-12),
                     20 * math.log10(float(np.abs(seg).max()) + 1e-12)))
    a = np.array(rows)
    out = []
    for fc in BANDS:
        m = (a[:, 0] >= fc * 2 ** (-1 / 6)) & (a[:, 0] < fc * 2 ** (1 / 6))
        if m.any():
            out.append(dict(f=round(fc), level=round(float(np.mean(a[m, 1])), 1),
                            thd=round(float(np.median(a[m, 2])), 1), peak=round(float(a[m, 3].max()), 1)))
    return out


def main():
    d = sys.argv[1]
    s = ideal()
    log = json.load(open(os.path.join(d, 'log.json')))
    res = {}
    for r in log:
        x = np.load(os.path.join(d, r['tag'] + '.npy'))
        res[r['tag']] = analyse(x, s)
    json.dump(res, open(os.path.join(d, 'analysis.json'), 'w'), indent=1)
    show = [b for b in (63, 125, 250, 500, 1000, 2000, 4000, 8000)]
    print('per tag: THD dB (peak dBFS) at ' + ' / '.join(f'{b}Hz' for b in show))
    for tag, bands in res.items():
        pick = {min(bands, key=lambda b: abs(b['f'] - x))['f']: None for x in show}
        cells = []
        for x in show:
            b = min(bands, key=lambda bb: abs(bb['f'] - x))
            cells.append(f'{b["thd"]:6.1f}({b["peak"]:5.1f})')
        print(f'{tag:16s} ' + ' '.join(cells))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    tags = [t for t in res if not t.startswith('ref')]
    cuts = sorted({int(t.split('_c')[1].split('_')[0]) for t in tags})
    fig, axes = plt.subplots(2, len(cuts), figsize=(4.2 * len(cuts), 8), sharex=True)
    for j, c in enumerate(cuts):
        for t in tags:
            if f'_c{c}_' not in t:
                continue
            b = res[t]
            fs = [x['f'] for x in b]
            axes[0][j].semilogx(fs, [x['level'] for x in b], lw=1, label=t.split('_')[-1])
            axes[1][j].semilogx(fs, [x['thd'] for x in b], lw=1, label=t.split('_')[-1])
        axes[0][j].set_title(f'cutoff {c}: fundamental level (dB)', fontsize=9)
        axes[1][j].set_title(f'cutoff {c}: THD (dB)', fontsize=9)
        for ax in (axes[0][j], axes[1][j]):
            ax.grid(True, which='both', alpha=.3)
        axes[1][j].set_ylim(-80, 5); axes[1][j].set_xlabel('Hz')
    axes[0][-1].legend(fontsize=7, ncol=2)
    fig.tight_layout(); fig.savefig(os.path.join(d, 'analysis.png'), dpi=85)


if __name__ == '__main__':
    main()
