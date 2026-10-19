#!/usr/bin/env python3
"""Measure E4 voice-filter frequency responses on hardware with the sine-sweep sample.

Preset 000 (test suite), voice 0; key 77 = 20 s log sweep 20 Hz-20 kHz at -12 dBFS.
Reference: Swept EQ 1 octave (menu 8) at gain 64 (0 dB): pole word == zero word -> exactly flat.
Response = FFT(filtered) / FFT(reference) after alignment, smoothed to 1/24 octave.

usage: hw_freqresp.py OUTDIR LABEL [--types 0,1,2] [--qs 0,127] [--freqs 48,96,144,192,240,255]
       hw_freqresp.py --analyze OUTDIR LABEL
"""
import argparse, json, math, os, sys, time
import numpy as np, sounddevice as sd, soundfile as sf, mido

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eos_remote as er          # noqa: E402
import hw_burst_test as hb       # noqa: E402

FS = 48000
KEY, DUR = 77, 20.5
REF_TYPE, REF_Q = 8, 64
FILT_CORD_AMTS = (137, 140, 143, 146, 149, 152, 155)   # cords 3..9 amounts (zeroed)
NAMES = {0: '2pole', 1: '4pole', 2: '6pole', 3: 'hp2', 4: 'hp4', 5: 'bp2', 6: 'bp4', 7: 'cbp'}


def disp_hz(v):
    d, p = 255 - v, 0x4E20
    if d > 0:
        if d & 1:
            p, d = 0x4C72, d - 1
        for _ in range(d // 2):
            p = (p * 0x3EA) // 0x400
            p = (p * 0x3EA) // 0x400
    return p


def play(e, dev):
    hb.wait_silence(dev, limit=40)
    rec = sd.rec(int((DUR + 1.5) * FS), samplerate=FS, channels=hb.nch(), device=dev, dtype='float32')
    time.sleep(0.2)
    e.out.send(mido.Message('note_on', channel=0, note=KEY, velocity=100)); time.sleep(DUR)
    e.out.send(mido.Message('note_off', channel=0, note=KEY)); sd.wait()
    return rec[:, hb.CH[0]:hb.CH[1] + 1].mean(axis=1)


def measure(a):
    os.makedirs(a.outdir, exist_ok=True)
    dev = hb.device()
    e = er.Eos()
    e.out.send(mido.Message('program_change', channel=0, program=0)); time.sleep(0.5)
    e.set(223, 0); e.set(225, 0)
    for c in FILT_CORD_AMTS:
        e.set(c, 0)
    e.set(140, 0)
    log = []

    def run(tag, ft, fv, q):
        e.set(82, ft); time.sleep(0.15); e.set(83, fv); e.set(84, q); time.sleep(0.2)
        got = e.get([82, 83, 84])
        x = play(e, dev)
        np.save(os.path.join(a.outdir, f'{a.label}_{tag}.npy'), x.astype(np.float32))
        log.append(dict(tag=tag, type=ft, freq=fv, q=q, params=got,
                        peak_dbfs=round(20 * math.log10(float(np.abs(x).max()) + 1e-12), 1)))
        print(f'{tag:24s} {got}  peak {log[-1]["peak_dbfs"]} dBFS', flush=True)

    run('ref_start', REF_TYPE, 128, REF_Q)
    for ft in [int(t) for t in a.types.split(',')]:
        for q in [int(t) for t in a.qs.split(',')]:
            for fv in [int(t) for t in a.freqs.split(',')]:
                run(f'{NAMES[ft]}_q{q}_f{fv}', ft, fv, q)
    run('ref_end', REF_TYPE, 128, REF_Q)
    e.close()
    json.dump(log, open(os.path.join(a.outdir, f'{a.label}_log.json'), 'w'), indent=1)


def align(y, ref):
    n = 1 << int(math.ceil(math.log2(len(ref) * 2)))
    c = np.fft.irfft(np.fft.rfft(y, n) * np.conj(np.fft.rfft(ref, n)), n)
    lag = int(np.argmax(np.abs(c)))
    if lag > n // 2:
        lag -= n
    return np.roll(y, -lag)


def response(y, ref):
    y = align(y, ref)
    n = len(ref)
    Y, R = np.fft.rfft(y * np.hanning(n)), np.fft.rfft(ref * np.hanning(n))
    f = np.fft.rfftfreq(n, 1 / FS)
    centres = 20 * 2 ** (np.arange(0, 10 * 24 + 1) / 24)
    centres = centres[centres < 20000]
    H = []
    for fc in centres:
        m = (f >= fc * 2 ** (-1 / 48)) & (f < fc * 2 ** (1 / 48))
        H.append(10 * math.log10((np.abs(Y[m]) ** 2).sum() / ((np.abs(R[m]) ** 2).sum() + 1e-30) + 1e-30))
    return centres, np.array(H)


def analyze(a):
    log = json.load(open(os.path.join(a.outdir, f'{a.label}_log.json')))
    ld = lambda t: np.load(os.path.join(a.outdir, f'{a.label}_{t}.npy'))
    ref = ld('ref_start')
    fr, drift = response(ld('ref_end'), ref)
    print(f'reference drift start->end: max |dB| {np.abs(drift[(fr > 40) & (fr < 16000)]).max():.2f}')
    rows, curves = [], {}
    for r in log:
        if r['tag'].startswith('ref'):
            continue
        f, H = response(ld(r['tag']), ref)
        curves[r['tag']] = H
        band = (f > 30) & (f < 16000)
        pass_db = np.median(H[(f > 30) & (f < 60)])
        pk_i = int(np.argmax(np.where(band, H, -999)))
        below = np.where(band & (H < pass_db - 3) & (f > 40))[0]
        fc3 = float(f[below[0]]) if len(below) else float('nan')
        # slope: dB/octave between 2 and 4 octaves above the -3 dB point
        slope = float('nan')
        if not math.isnan(fc3) and fc3 * 16 < 16000:
            i1, i2 = np.argmin(abs(f - fc3 * 4)), np.argmin(abs(f - fc3 * 16))
            slope = (H[i2] - H[i1]) / 2.0
        rows.append(dict(tag=r['tag'], freq=r['freq'], q=r['q'], display_hz=disp_hz(r['freq']),
                         passband_db=round(float(pass_db), 1), f3db_hz=(round(fc3) if not math.isnan(fc3) else None), peak_hz=round(float(f[pk_i])),
                         peak_over_pass_db=round(float(H[pk_i] - pass_db), 1),
                         slope_db_oct=round(slope, 1) if not math.isnan(slope) else None))
    json.dump(dict(f=list(map(float, f)), curves={k: list(map(float, v)) for k, v in curves.items()}),
              open(os.path.join(a.outdir, f'{a.label}_curves.json'), 'w'))
    json.dump(rows, open(os.path.join(a.outdir, f'{a.label}_summary.json'), 'w'), indent=1)
    print(f'{"run":20s} {"disp Hz":>8s} {"-3dB Hz":>8s} {"peak Hz":>8s} {"peak dB":>8s} {"pass dB":>8s} {"slope":>7s}')
    for r in rows:
        print(f'{r["tag"]:20s} {r["display_hz"]:8d} {str(r["f3db_hz"]):>8s} {r["peak_hz"]:8d} {r["peak_over_pass_db"]:8.1f} '
              f'{r["passband_db"]:8.1f} {str(r["slope_db_oct"]):>7s}')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(3, 2, figsize=(14, 11), sharex=True)
    for i, name in enumerate(('2pole', '4pole', '6pole')):
        for j, q in enumerate((0, 127)):
            ax = axes[i][j]
            for k, H in curves.items():
                if k.startswith(f'{name}_q{q}_'):
                    ax.semilogx(f, H, lw=1, label=k.split('_')[-1])
            ax.set_title(f'{a.label}: {name} Q {q}', fontsize=9); ax.grid(True, which='both', alpha=.3)
            ax.set_ylim(-70, 30); ax.legend(fontsize=7, ncol=3)
    axes[-1][0].set_xlabel('Hz'); axes[-1][1].set_xlabel('Hz')
    fig.tight_layout(); fig.savefig(os.path.join(a.outdir, f'{a.label}_responses.png'), dpi=85)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('outdir'); ap.add_argument('label')
    ap.add_argument('--types', default='0,1,2'); ap.add_argument('--qs', default='0,127')
    ap.add_argument('--freqs', default='48,96,144,192,240,255')
    ap.add_argument('--analyze', action='store_true')
    a = ap.parse_args()
    analyze(a) if a.analyze else measure(a)


if __name__ == '__main__':
    main()
