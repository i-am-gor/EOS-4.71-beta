#!/usr/bin/env python3
"""Re-run the preset 001 clipping scans (same settings as the v1 runs) and write a CSV.

  A static scan:   type 0/1/2, Q 127, freq 160..255, filter env amount 0 / 26, LFO cord 0
  B boundary:      4-pole, Q 48/80/104/127, freq 184..255, env 0, LFO 0
  C 6-pole 3208 Hz: freq 171, Q 64/127, LFO cord 0 / -28, env 26, keys 62/74/86, velocity 127

usage: hw_rescan.py OUTDIR LABEL
"""
import csv, math, os, sys, time
import numpy as np, sounddevice as sd, soundfile as sf, mido

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eos_remote as er          # noqa: E402
import hw_burst_test as hb       # noqa: E402
import hw_p001_test as hp        # noqa: E402

FS = 48000
FILTERS = {0: '2pole', 1: '4pole', 2: '6pole'}


def take(e, dev, out, tag, key=62, vel=127, dur=3.0):
    hb.wait_silence(dev)
    rec = sd.rec(int((dur + 1.0) * FS), samplerate=FS, channels=hb.nch(), device=dev, dtype='float32')
    time.sleep(0.2)
    e.out.send(mido.Message('note_on', channel=0, note=key, velocity=vel)); time.sleep(dur)
    e.out.send(mido.Message('note_off', channel=0, note=key)); sd.wait()
    st = rec[:, hb.CH[0]:hb.CH[1] + 1]
    sf.write(os.path.join(out, tag + '.wav'), st, FS)
    rise, nev, _ = hp.hf_events(st.mean(axis=1))
    return 20 * math.log10(float(np.abs(st).max()) + 1e-12), rise, nev


def main():
    out, label = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    dev = hb.device()
    e = er.Eos()
    e.out.send(mido.Message('program_change', channel=0, program=1)); time.sleep(0.5)
    e.set(223, 1); e.set(225, 0)
    rows = []

    def log(test, ft, q, fv, env, lfo, key, res):
        pk, rise, nev = res
        rows.append(dict(build=label, test=test, filter=FILTERS[ft], q=q, freq=fv, env=env, lfo=lfo, key=key,
                         peak_dbfs=round(pk, 1), hf_rise_db=round(rise, 1), click_windows=nev,
                         clip=int(pk > -0.5)))
        print(f'{test} {FILTERS[ft]} q{q:3d} f{fv:3d} env{env:2d} lfo{lfo:3d} k{key}: peak {pk:6.1f} dBFS'
              f'{"  <-- CLIP" if pk > -0.5 else ""}', flush=True)

    # A static scan
    for ft in (0, 1, 2):
        e.set(82, ft); time.sleep(0.1); e.set(84, 127); e.set(137, 0)
        for env in (0, 26):
            e.set(140, env)
            for fv in (160, 164, 168, 171, 176, 184, 192, 208, 224, 240, 255):
                e.set(83, fv); time.sleep(0.15)
                log('A', ft, 127, fv, env, 0, 62, take(e, dev, out, f'A_{FILTERS[ft]}_env{env}_f{fv}'))
    # B boundary (4-pole)
    e.set(82, 1); time.sleep(0.1); e.set(137, 0); e.set(140, 0)
    for q in (48, 80, 104, 127):
        e.set(84, q)
        for fv in (184, 192, 200, 208, 216, 224, 232, 240, 248, 255):
            e.set(83, fv); time.sleep(0.15)
            log('B', 1, q, fv, 0, 0, 62, take(e, dev, out, f'B_4pole_q{q}_f{fv}', dur=2.5))
    # C 6-pole at 3208 Hz with the user's LFO
    e.set(82, 2); time.sleep(0.1); e.set(83, 171); e.set(140, 26)
    for q in (64, 127):
        e.set(84, q)
        for lfo in (0, -28):
            e.set(137, lfo); time.sleep(0.15)
            for key in (62, 74, 86):
                log('C', 2, q, 171, 26, lfo, key, take(e, dev, out, f'C_6pole_q{q}_lfo{lfo}_k{key}', key=key, dur=3.5))
    e.close()
    with open(os.path.join(out, f'{label}_rescan.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print(f'clips: {sum(r["clip"] for r in rows)} / {len(rows)} takes')


if __name__ == '__main__':
    main()
