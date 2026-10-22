#!/usr/bin/env python3
"""A/B of loop-scan noise: old SLoop + Gain4X chain (P001) vs SLpScn (P000), recorded on Quantum 19/20.

usage: hw_slpscn_ab.py OUTDIR [KEY]
All takes on P001 voice 0 (same sample, filter, envelopes; key KEY, velocity 100, held 2.5 s, 4.5 s recorded):
  A  as stored (AEnv+ -> Gain4X +100, Gain4X -> SLoop +100 x4)
  B  cords 5-8 muted, cord 11 = Gain4X -> SLpScn +6 (same chain, about the same ~500-sample travel)
  C  cord 4 muted, cord 11 = AEnv+ -> SLpScn +100 (P000-style)
P001's cords 4-8 and 11 are restored afterwards (edit buffer only).
Click metric: energy above 5 kHz in 1 ms frames relative to the median (transient peaks), and the 5 kHz+ share
of the total energy, over the held part of the note.
"""
import json, math, os, sys, time
import numpy as np, sounddevice as sd, soundfile as sf, mido

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eos_remote as er          # noqa: E402
import hw_burst_test as hb       # noqa: E402

FS = 48000
AENV, GAIN4X, SLPSCN = 88, 167, 58


def cord(e, c, src=None, dst=None, amt=None):
    base = 129 + 3 * (c - 1)
    if src is not None:
        e.set(base, src)
    if dst is not None:
        e.set(base + 1, dst)
    if amt is not None:
        e.set(base + 2, amt & 0x3FFF)


def take(e, dev, prog, key):
    e.out.send(mido.Message('program_change', channel=0, program=prog)); time.sleep(0.6)
    hb.wait_silence(dev, limit=10.0)
    rec = sd.rec(int(4.5 * FS), samplerate=FS, channels=hb.nch(), device=dev, dtype='float32')
    time.sleep(0.2)
    e.out.send(mido.Message('note_on', channel=0, note=key, velocity=100)); time.sleep(2.5)
    e.out.send(mido.Message('note_off', channel=0, note=key)); sd.wait()
    return rec[:, hb.CH[0]:hb.CH[1] + 1].mean(axis=1)


def metric(x):
    on = int(np.argmax(np.abs(x) > 0.02 * np.abs(x).max()))
    seg = x[on:on + int(2.4 * FS)]
    X = np.fft.rfft(seg)
    f = np.fft.rfftfreq(len(seg), 1 / FS)
    hp = np.fft.irfft(np.where(f > 5000, X, 0), len(seg))
    fr = int(0.001 * FS)
    e = np.array([np.sum(hp[i:i + fr] ** 2) for i in range(0, len(hp) - fr, fr)])
    med = np.median(e) + 1e-20
    tot = np.sum(seg ** 2) + 1e-20
    return dict(peak_db=round(10 * math.log10(e.max() / med), 1),
                p99_db=round(10 * math.log10(np.percentile(e, 99) / med), 1),
                hf_share_db=round(10 * math.log10(np.sum(hp ** 2) / tot), 1),
                level_dbfs=round(20 * math.log10(np.sqrt(np.mean(seg ** 2)) + 1e-12), 1),
                onset_s=round(on / FS, 3))


def main():
    out = sys.argv[1]
    key = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    os.makedirs(out, exist_ok=True)
    dev = hb.device()
    e = er.Eos()
    P = 1                                   # every take on P001 voice 0: same sample, filter, envelopes
    ids = [129 + 3 * (c - 1) + k for c in (4, 5, 6, 7, 8, 11) for k in range(3)]
    e.set(223, P); e.set(225, 0); time.sleep(0.2)
    keep = e.get(ids)
    res = {}
    try:
        res['A'] = take(e, dev, P, key)                    # as stored: AEnv+ -> Gain4X -> SLoop x4
        e.set(223, P); e.set(225, 0)
        for c in (5, 6, 7, 8):
            cord(e, c, amt=0)
        cord(e, 11, GAIN4X, SLPSCN, 6)                     # same chain into SLpScn, ~same travel
        res['B'] = take(e, dev, P, key)
        e.set(223, P); e.set(225, 0)
        cord(e, 4, amt=0)
        cord(e, 11, AENV, SLPSCN, 100)                     # P000-style: AEnv+ -> SLpScn +100
        res['C'] = take(e, dev, P, key)
    finally:
        e.set(223, P); e.set(225, 0)
        for c in (4, 5, 6, 7, 8, 11):
            b = 129 + 3 * (c - 1)
            cord(e, c, keep[b], keep[b + 1], keep[b + 2])
        back = e.get(ids)
        e.set(223, 0); e.set(225, 0)
        e.close()
    summary = {}
    for t, x in res.items():
        sf.write(os.path.join(out, f'take_{t}.wav'), x, FS)
        summary[t] = metric(x)
        print(t, summary[t], flush=True)
    print('P001 cords restored:', back == keep)
    json.dump(dict(key=key, summary=summary, restored=back == keep), open(os.path.join(out, 'ab.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
