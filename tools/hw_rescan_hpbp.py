#!/usr/bin/env python3
"""Clipping / noise-burst scan for the high-pass and band-pass filters (menu 3-6) on preset 001.

Same method as hw_rescan.py: preset 001 voice 0, key 62, velocity 127, 3 s takes from the Quantum (19/20).
  types 3 (2nd HP), 4 (4th HP), 5 (2nd BP), 6 (4th BP); Q 96 / 127; filter-env cord 0 / 26;
  cutoff 48, 96, 128, 160, 176, 192, 208, 224, 240, 255. LFO cord 0.
Per take: peak dBFS (clip = peak > -0.5 dBFS), HF rise and click windows (hw_p001_test.hf_events).

usage: hw_rescan_hpbp.py OUTDIR LABEL
"""
import csv, os, sys, time
import mido

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eos_remote as er          # noqa: E402
import hw_burst_test as hb       # noqa: E402
import hw_rescan as rs           # noqa: E402

NAMES = {3: 'hp2', 4: 'hp4', 5: 'bp2', 6: 'bp4'}
FREQS = (48, 96, 128, 160, 176, 192, 208, 224, 240, 255)


def main():
    out, label = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    dev = hb.device()
    e = er.Eos()
    e.out.send(mido.Message('program_change', channel=0, program=1)); time.sleep(0.5)
    e.set(223, 1); e.set(225, 0)
    e.set(137, 0)
    rows = []
    for ft, name in NAMES.items():
        e.set(82, ft); time.sleep(0.15)
        for q in (96, 127):
            e.set(84, q)
            for env in (0, 26):
                e.set(140, env)
                for fv in FREQS:
                    e.set(83, fv); time.sleep(0.15)
                    pk, rise, nev = rs.take(e, dev, out, f'{name}_q{q}_env{env}_f{fv}')
                    rows.append(dict(build=label, filter=name, q=q, freq=fv, env=env, peak_dbfs=round(pk, 1),
                                     hf_rise_db=round(rise, 1), click_windows=nev, clip=int(pk > -0.5)))
                    print(f'{name} q{q:3d} env{env:2d} f{fv:3d}: peak {pk:6.1f} dBFS  clicks {nev}'
                          f'{"  <-- CLIP" if pk > -0.5 else ""}', flush=True)
    e.close()
    with open(os.path.join(out, f'{label}_rescan.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print(f'clips: {sum(r["clip"] for r in rows)} / {len(rows)} takes; takes with click windows: '
          f'{sum(1 for r in rows if r["click_windows"])}')


if __name__ == '__main__':
    main()
