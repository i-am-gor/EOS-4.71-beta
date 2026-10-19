#!/usr/bin/env python3
"""Hardware burst test: drive the E4 over MIDI/SysEx, record its outputs, detect noise bursts.

Preset 001 test bank: tones 801/915/3502 Hz on MIDI 72/74/76, sweeps (-12/-24 dBFS) on 77/79.
For each lowpass (menu index 0/1/2) at max Q, cutoff at the reported burst value, LFO off/on
(cord 9: Lfo1~ -> FilFreq), every key is played and recorded from MOTU inputs 17/18.

Burst metric per 10 ms frame: energy outside +-4 % of the strongest spectral peak and its
first 4 harmonics, relative to total energy ("residual", dB). A clean filtered tone/sweep sits
well below -40 dB; broadband noise bursts push it toward 0 dB.

usage: hw_burst_test.py OUTDIR [--label obxa] [--filters 0,1,2] [--lfo-amount 30]
"""
import argparse, json, math, os, sys, time
import numpy as np
import sounddevice as sd
import soundfile as sf
import mido

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eos_remote as er  # noqa: E402

FS = 48000
CH = (18, 19)                       # Quantum 2626 inputs 19/20 (never open the MOTU audio: it disturbs the ADAT clock)
DEVICE = 'Quantum'
KEYS = {72: ('tone801', 6.0), 74: ('tone915', 6.0), 76: ('tone3502', 6.0),
        77: ('sweep-12', 20.5), 79: ('sweep-24', 20.5)}
BURST_HZ = {0: 3502, 1: 915, 2: 801}
FNAME = {0: '2pole', 1: '4pole', 2: '6pole'}
CORD9 = (153, 154, 155)             # src, dst, amount ids
LFO1_SRC, FILFREQ_DST = 96, 56


def freq_value(hz):
    return int(round(255 - math.log(hz / 20000) / math.log(1002 / 1024)))


def device():
    return [i for i, d in enumerate(sd.query_devices()) if DEVICE in d['name'] and d['max_input_channels'] > 0][0]


def nch():
    return sd.query_devices(device())['max_input_channels']


def level_db(x):
    return 20 * math.log10(math.sqrt(float(np.mean(x * x))) + 1e-12)


def wait_silence(dev, limit=30.0):
    t0 = time.time()
    while time.time() - t0 < limit:
        r = sd.rec(int(0.3 * FS), samplerate=FS, channels=nch(), device=dev, dtype='float32'); sd.wait()
        if level_db(r[:, CH[0]:CH[1] + 1].mean(axis=1)) < -70:
            return True
    return False


def residual_track(x, frame=480, nfft=2048, npeaks=4):
    """Per frame: energy left after removing the npeaks strongest tones (each with harmonics 1..5,
    +-4 %), relative to total. Tones (input, resonance ringing) are excluded; noise is not."""
    win = np.hanning(nfft)
    freqs = np.fft.rfftfreq(nfft, 1 / FS)
    out = []
    for s in range(0, len(x) - nfft, frame):
        seg = x[s:s + nfft] * win
        P = np.abs(np.fft.rfft(seg)) ** 2
        tot = P.sum() + 1e-20
        mask = np.zeros_like(P, bool)
        mask[:4] = True
        Q = P.copy()
        f0 = 0.0
        for k in range(npeaks):
            Q[mask] = 0
            fp = freqs[int(np.argmax(Q))]
            if k == 0:
                f0 = fp
            for h in range(1, 6):
                fh = fp * h
                if fh < FS / 2:
                    mask |= np.abs(freqs - fh) <= max(40.0, 0.04 * fh)
        out.append((s / FS, 10 * math.log10(P[~mask].sum() / tot + 1e-12), level_db(x[s:s + nfft]), f0))
    return np.array(out)


def spectrogram_png(x, tr, path, title):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(2, 1, figsize=(12, 6), sharex=True, gridspec_kw=dict(height_ratios=[3, 1]))
    ax[0].specgram(x, NFFT=2048, Fs=FS, noverlap=1536, cmap='magma', vmin=-160, vmax=-40)
    ax[0].set_ylim(0, 16000); ax[0].set_title(title, fontsize=9)
    if len(tr):
        ax[1].plot(tr[:, 0], tr[:, 1], lw=.7, label='noise residual dB')
        ax[1].plot(tr[:, 0], tr[:, 2], lw=.7, label='level dBFS')
        ax[1].axhline(-20, color='r', lw=.5); ax[1].set_ylim(-90, 5); ax[1].legend(fontsize=7, loc='lower right')
    fig.tight_layout(); fig.savefig(path, dpi=80); plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('outdir'); ap.add_argument('--label', default='obxa')
    ap.add_argument('--filters', default='0,1,2'); ap.add_argument('--lfo-amount', type=int, default=30)
    ap.add_argument('--keys', default='72,74,76,77,79')
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    dev = device()
    e = er.Eos()
    results = []
    e.set(CORD9[0], LFO1_SRC); e.set(CORD9[1], FILFREQ_DST)
    for ft in [int(x) for x in a.filters.split(',')]:
        fv = freq_value(BURST_HZ[ft])
        e.set(82, ft); time.sleep(0.1); e.set(84, 127); e.set(83, fv)
        for lfo in (0, a.lfo_amount):
            e.set(CORD9[2], lfo); time.sleep(0.2)
            got = e.get([82, 83, 84] + list(CORD9))
            for key in [int(k) for k in a.keys.split(',')]:
                name, dur = KEYS[key]
                wait_silence(dev)
                rec = sd.rec(int((dur + 1.0) * FS), samplerate=FS, channels=nch(), device=dev, dtype='float32')
                time.sleep(0.2)
                e.out.send(mido.Message('note_on', channel=0, note=key, velocity=100))
                time.sleep(dur)
                e.out.send(mido.Message('note_off', channel=0, note=key))
                sd.wait()
                st = rec[:, CH[0]:CH[1] + 1]
                tag = f'{a.label}_{FNAME[ft]}_lfo{lfo}_{name}'
                sf.write(os.path.join(a.outdir, tag + '.wav'), st, FS)
                x = st.mean(axis=1)
                tr = residual_track(x)
                live = tr[tr[:, 2] > -75] if len(tr) else tr
                worst = float(live[:, 1].max()) if len(live) else float('nan')
                frac = float((live[:, 1] > -20).mean()) if len(live) else 0.0
                peak = 20 * math.log10(float(np.abs(st).max()) + 1e-12)
                np.save(os.path.join(a.outdir, tag + '_track.npy'), tr)
                spectrogram_png(x, tr, os.path.join(a.outdir, tag + '.png'),
                                f'{tag}  params {got}  peak {20*math.log10(float(np.abs(st).max())+1e-12):.1f} dBFS')
                r = dict(tag=tag, filter=FNAME[ft], lfo=lfo, key=key, signal=name, params=got,
                         peak_dbfs=round(peak, 1), worst_residual_db=round(worst, 1),
                         burst_frames_pct=round(100 * frac, 1))
                results.append(r)
                print(f'{tag:34s} peak {peak:6.1f} dBFS  worst residual {worst:6.1f} dB  '
                      f'frames > -20 dB: {100 * frac:5.1f} %', flush=True)
    e.close()
    with open(os.path.join(a.outdir, f'{a.label}_results.json'), 'w') as f:
        json.dump(results, f, indent=1)


if __name__ == '__main__':
    main()
