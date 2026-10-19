#!/usr/bin/env python3
"""Null test for the RFX amp-path skip: record deterministic takes on one firmware, compare two firmwares.

record: hw_rfx_null.py record OUTDIR LABEL      (2 repetitions of each scenario)
compare: hw_rfx_null.py compare OUTDIR LABEL_A LABEL_B
Preset 000 voice 0 (key 72 sine), rig cords cleared, LFO1 sine, Key Sync (phase fixed to the note-on).
Scenarios: steady (nothing changes: all skips), trem (LFO1 -> AmpVol 50: volume changes every tick),
pan (LFO1 -> AmpPan 60), send (LFO1 -> SndMain 70 and SndAux1 70: the four FX sends change).
compare: per scenario, aligned-waveform residual (dB below the signal) and worst 10 ms envelope difference
(dB, per channel) between the firmwares, against the same numbers between the two takes of one firmware.
"""
import json, os, sys, time
import numpy as np, soundfile as sf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hw_lfosync_test as t   # noqa: E402

FS = 48000
SCEN = {'steady': [], 'trem': [(t.SRC, t.LFO1_SRC), (t.DST, t.AMPVOL), (t.AMT, 50)],
        'pan': [(t.SRC, t.LFO1_SRC), (t.DST, 65), (t.AMT, 60)],
        'send': [(t.SRC, t.LFO1_SRC), (t.DST, 68), (t.AMT, 70), (t.SRC + 3, t.LFO1_SRC), (t.DST + 3, 69), (t.AMT + 3, 70)]}


def record(out, label):
    os.makedirs(out, exist_ok=True)
    rig = t.Rig(); e = rig.e
    rig.setup()
    for name, sets in SCEN.items():
        e.set(t.AMT, 0); e.set(t.AMT + 3, 0); e.set(t.DST, t.AMPVOL)
        e.set(105, 64)                                # LFO1 rate 64 (4.12 Hz), sine, key sync (setup)
        for p, v in sets:
            e.set(p, v)
        time.sleep(0.3)
        for rep in range(2):
            for attempt in range(4):                  # retry takes lost to a capture dropout
                st = rig.take(3.0)
                if 20 * np.log10(np.abs(st).max() + 1e-12) > -60:
                    break
                print(f'  {name} take {rep}: no signal, retrying', flush=True)
                time.sleep(1.0)
            else:
                raise SystemExit('no signal from the E4 on inputs 19/20')
            sf.write(os.path.join(out, f'{label}_{name}_{rep}.wav'), st, FS)
            print(f'{label} {name} take {rep}: peak {20 * np.log10(np.abs(st).max() + 1e-12):.1f} dBFS', flush=True)
    e.set(t.AMT, 0); e.set(t.AMT + 3, 0); e.set(t.DST, t.AMPVOL)
    e.close()


def align(a, b):
    """Integer-sample alignment of b to a (cross-correlation of the first 0.5 s after the onset)."""
    oa, ob = t.onset(t.envelope(a)), t.onset(t.envelope(b))
    sa = a[oa * 48:oa * 48 + FS, 0]; sb = b[ob * 48:ob * 48 + FS, 0]
    best, lag = -1, 0
    for d in range(-200, 201):
        x = sa[400:FS - 400]; y = sb[400 + d:FS - 400 + d]
        c = float(np.dot(x, y))
        if c > best:
            best, lag = c, d
    n = min(len(a) - oa * 48, len(b) - ob * 48 - lag) - 2000
    return a[oa * 48:oa * 48 + n], b[ob * 48 + lag:ob * 48 + lag + n]


def metrics(a, b):
    x, y = align(a, b)
    seg = slice(int(0.2 * FS), int(2.6 * FS))
    res = 10 * np.log10(np.sum((x[seg] - y[seg]) ** 2) / np.sum(x[seg] ** 2))
    w = 480
    def env(z):
        m = len(z) // w
        return 20 * np.log10(np.sqrt(np.mean(z[:m * w].reshape(m, w, 2) ** 2, axis=1)) + 1e-9)
    ex, ey = env(x[seg]), env(y[seg])
    return float(res), float(np.max(np.abs(ex - ey)))


def compare(out, la, lb):
    rows = []
    for name in SCEN:
        A = [sf.read(os.path.join(out, f'{la}_{name}_{r}.wav'))[0] for r in range(2)]
        Bs = [sf.read(os.path.join(out, f'{lb}_{name}_{r}.wav'))[0] for r in range(2)]
        same_a, same_b = metrics(A[0], A[1]), metrics(Bs[0], Bs[1])
        cross = [metrics(A[i], Bs[j]) for i in range(2) for j in range(2)]
        r = dict(scenario=name, residual_same_a=round(same_a[0], 1), residual_same_b=round(same_b[0], 1),
                 residual_cross_max=round(max(c[0] for c in cross), 1),
                 env_same_max_db=round(max(same_a[1], same_b[1]), 2),
                 env_cross_max_db=round(max(c[1] for c in cross), 2))
        rows.append(r)
        print(f'{name:7s}: residual (dB re signal) same-firmware {r["residual_same_a"]:6.1f} / {r["residual_same_b"]:6.1f}, '
              f'across firmwares worst {r["residual_cross_max"]:6.1f}; 10 ms envelope diff worst: same '
              f'{r["env_same_max_db"]:.2f} dB, across {r["env_cross_max_db"]:.2f} dB')
    json.dump(rows, open(os.path.join(out, f'null_{la}_vs_{lb}.json'), 'w'), indent=1)


if __name__ == '__main__':
    if sys.argv[1] == 'record':
        record(sys.argv[2], sys.argv[3])
    else:
        compare(sys.argv[2], sys.argv[3], sys.argv[4])
