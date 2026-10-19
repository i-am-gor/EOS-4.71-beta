#!/usr/bin/env python3
"""Find random digital noise in gapless chunk recordings of a repeating sequence.

usage: noise_hunt.py DIR [--period SECONDS]
Per 5 ms window: HF (>8 kHz) level per channel. The sequence repeats every bar, so each window is
compared with the median of the same bar phase across all bars ("expected"); windows more than
THRESH dB above expected are anomalies. Also: single-sample spikes vs a 7-tap median.
Writes DIR/events.csv and zoom PNGs for the strongest events.
"""
import argparse, csv, glob, os, datetime
import numpy as np, soundfile as sf
from scipy.signal import butter, sosfilt, medfilt

FS = 48000
WIN = 240                    # 5 ms
THRESH = 12.0
SOS = butter(8, 8000, 'hp', fs=FS, output='sos')


def load(d):
    idx = {int(r[0]): r for r in csv.reader(open(os.path.join(d, 'index.csv')))}
    parts, starts = [], []
    for f in sorted(glob.glob(os.path.join(d, 'chunk_*.wav'))):
        n = int(os.path.basename(f).split('_')[1])
        if n not in idx:          # chunk still being written
            continue
        x, fs = sf.read(f)
        parts.append(x); starts.append(datetime.datetime.strptime(idx[n][1], '%Y-%m-%d %H:%M:%S.%f'))
    return np.concatenate(parts), starts[0]


def hf_env(x):
    h = sosfilt(SOS, x)
    n = len(h) // WIN
    return 20 * np.log10(np.sqrt((h[:n * WIN] ** 2).reshape(n, WIN).mean(axis=1)) + 1e-12)


def lvl_env(x):
    n = len(x) // WIN
    return 20 * np.log10(np.sqrt((x[:n * WIN] ** 2).reshape(n, WIN).mean(axis=1)) + 1e-12)


def period_estimate(env):
    e = env - env.mean()
    ac = np.correlate(e[:20000], e[:20000], 'full')[19999:]
    lo, hi = int(0.5 * FS / WIN), int(8 * FS / WIN)
    lag = lo + int(np.argmax(ac[lo:hi]))
    return lag                                  # in windows


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('dir'); ap.add_argument('--period', type=float)
    a = ap.parse_args()
    x, t0 = load(a.dir)
    L, R = x[:, 0], x[:, 1]
    hl, hr = hf_env(L), hf_env(R)
    lv = lvl_env(x.mean(axis=1))
    P = int(round(a.period * FS / WIN)) if a.period else period_estimate(lv)
    # refine period by maximising fold consistency around the estimate
    best = None
    for p in range(P - 3, P + 4):
        nb = len(lv) // p
        if nb < 3:
            continue
        s = np.median(np.abs(lv[:nb * p].reshape(nb, p) - np.median(lv[:nb * p].reshape(nb, p), axis=0)))
        if best is None or s < best[0]:
            best = (s, p)
    P = best[1]
    nb = len(hl) // P
    print(f'recording {len(x)/FS/60:.1f} min, bar period {P*WIN/FS:.4f} s, {nb} bars')
    events = []
    for name, h in (('L', hl), ('R', hr)):
        fold = h[:nb * P].reshape(nb, P)
        exp = np.median(fold, axis=0)
        excess = fold - exp
        floor = np.percentile(h, 10)
        for b, ph in zip(*np.where((excess > THRESH) & (fold > floor + 10))):
            i = b * P + ph
            events.append(dict(chan=name, t=i * WIN / FS, excess_db=round(float(excess[b, ph]), 1),
                               hf_dbfs=round(float(h[i]), 1), level_dbfs=round(float(lv[i]), 1)))
    # merge L/R events in the same window
    merged = {}
    for ev in events:
        k = int(ev['t'] * FS / WIN)
        m = merged.setdefault(k, dict(t=ev['t'], chans='', excess_db=0, hf_dbfs=-200, level_dbfs=ev['level_dbfs']))
        m['chans'] += ev['chan']; m['excess_db'] = max(m['excess_db'], ev['excess_db']); m['hf_dbfs'] = max(m['hf_dbfs'], ev['hf_dbfs'])
    # spikes
    spikes = []
    for name, c in (('L', L), ('R', R)):
        r = c - medfilt(c, 7)
        s = 1.4826 * np.median(np.abs(r)) + 1e-9
        idx = np.where(np.abs(r) > max(40 * s, 0.01))[0]
        for i in idx:
            spikes.append((i / FS, name, float(r[i])))
    rows = []
    for k in sorted(merged):
        m = merged[k]
        wall = t0 + datetime.timedelta(seconds=m['t'])
        rows.append(dict(time_s=round(m['t'], 3), wall=f'{wall:%H:%M:%S.%f}'[:-3], chans=m['chans'],
                         excess_db=m['excess_db'], hf_dbfs=m['hf_dbfs'], level_dbfs=m['level_dbfs']))
    with open(os.path.join(a.dir, 'events.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['time_s', 'wall', 'chans', 'excess_db', 'hf_dbfs', 'level_dbfs'])
        w.writeheader(); w.writerows(rows)
    print(f'anomalous HF windows: {len(rows)}   single-sample spikes: {len(spikes)}')
    for r in sorted(rows, key=lambda r: -r['excess_db'])[:25]:
        print('  ', r)
    for s in spikes[:20]:
        print('   spike', round(s[0], 4), s[1], round(s[2], 4))
    # zoom plots of the strongest events
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    for j, r in enumerate(sorted(rows, key=lambda r: -r['excess_db'])[:6]):
        c = int(r['time_s'] * FS)
        s0, s1 = max(0, c - int(0.05 * FS)), min(len(x), c + int(0.05 * FS))
        fig, ax = plt.subplots(3, 1, figsize=(12, 8))
        ax[0].plot(np.arange(s0, s1) / FS, L[s0:s1], lw=.5, label='L'); ax[0].plot(np.arange(s0, s1) / FS, R[s0:s1], lw=.5, label='R'); ax[0].legend()
        ax[0].set_title(f'event {j}: t={r["time_s"]} s ({r["wall"]}) excess {r["excess_db"]} dB chans {r["chans"]}')
        ax[1].specgram(x[s0:s1].mean(axis=1), NFFT=256, Fs=FS, noverlap=224, cmap='magma', vmin=-160, vmax=-40); ax[1].set_ylim(0, 24000)
        # same bar phase one bar earlier for comparison
        pc = c - P * WIN
        if pc - int(0.05 * FS) > 0:
            ax[2].plot(np.arange(-int(0.05 * FS), int(0.05 * FS)) / FS, x[pc - int(0.05 * FS):pc + int(0.05 * FS)].mean(axis=1), lw=.5, color='g')
            ax[2].set_title('same position one bar earlier (reference)')
        fig.tight_layout(); fig.savefig(os.path.join(a.dir, f'event_{j}.png'), dpi=75); plt.close(fig)


if __name__ == '__main__':
    main()
