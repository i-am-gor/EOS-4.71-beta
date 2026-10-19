#!/usr/bin/env python3
"""Preset 001 filter test on hardware: the user's sample at its root note through 2/4/6-pole LP.

Selects preset 001 voice 0 for editing (SysEx 223/225), keeps the user's modulation
(cord 3 Lfo1~ -> FilFreq -28, cord 4 FEnv+ -> FilFreq +26), varies filter type / freq / Q and LFO,
plays the root key and records MOTU 17/18.
Clipping/overload metric: energy above 10 kHz in 5 ms windows vs the end-of-take floor
(cutoffs here are low, so the sample's own HF is removed; clicks and saturation show up as HF).

usage: hw_p001_test.py OUTDIR [--label obxa]
"""
import argparse, json, math, os, sys, time
import numpy as np, sounddevice as sd, soundfile as sf, mido
from scipy.signal import butter, sosfilt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eos_remote as er          # noqa: E402
import hw_burst_test as hb       # noqa: E402

FS = 48000
ROOT = 62
CORD3_AMT, CORD4_AMT = 137, 140
SOS = butter(8, 10000, 'hp', fs=FS, output='sos')


def hf_events(x):
    h = sosfilt(SOS, x)
    n = 240
    fr = 20 * np.log10(np.sqrt(np.convolve(h * h, np.ones(n) / n, 'valid'))[::n] + 1e-12)
    floor = float(np.median(fr[-40:]))
    return float(fr.max() - floor), int((fr > floor + 15).sum()), fr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('outdir'); ap.add_argument('--label', default='obxa')
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    dev = hb.device()
    e = er.Eos(); e.set(223, 1); e.set(225, 0)
    runs = [(18, 34, 51, 'user')]                       # user's own filter as reference
    for ft in (0, 1, 2):
        for fv, q in ((34, 51), (hb.freq_value(hb.BURST_HZ[ft]), 127)):
            runs.append((ft, fv, q, None))
    results = []
    for ft, fv, q, note in runs:
        for lfo in (0, -28):
            e.set(82, ft); time.sleep(0.1); e.set(83, fv); e.set(84, q)
            e.set(CORD3_AMT, lfo); e.set(CORD4_AMT, 26); time.sleep(0.2)
            got = e.get([82, 83, 84, CORD3_AMT, CORD4_AMT])
            hb.wait_silence(dev)
            rec = sd.rec(int(5.0 * FS), samplerate=FS, channels=hb.nch(), device=dev, dtype='float32')
            time.sleep(0.2)
            e.out.send(mido.Message('note_on', channel=0, note=ROOT, velocity=100)); time.sleep(4.0)
            e.out.send(mido.Message('note_off', channel=0, note=ROOT)); sd.wait()
            st = rec[:, hb.CH[0]:hb.CH[1] + 1]; x = st.mean(axis=1)
            tag = f'{a.label}_type{ft}_f{fv}_q{q}_lfo{lfo}'
            sf.write(os.path.join(a.outdir, tag + '.wav'), st, FS)
            rise, nev, fr = hf_events(x)
            peak = 20 * math.log10(float(np.abs(st).max()) + 1e-12)
            tr = hb.residual_track(x)
            hb.spectrogram_png(x, tr, os.path.join(a.outdir, tag + '.png'), f'{tag} {got} peak {peak:.1f} dBFS')
            r = dict(tag=tag, type=ft, freq=fv, q=q, lfo=lfo, params=got, peak_dbfs=round(peak, 1),
                     hf_rise_db=round(rise, 1), hf_event_windows=nev)
            results.append(r)
            print(f'{tag:30s} peak {peak:6.1f} dBFS   HF>10k rise {rise:5.1f} dB   click windows {nev:4d}', flush=True)
    e.close()
    json.dump(results, open(os.path.join(a.outdir, f'{a.label}_results.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
