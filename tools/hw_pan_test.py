#!/usr/bin/env python3
"""Pan law on hardware: preset 000 voice 0 (key 72 sine), cords off, voice Pan (param 90) swept;
left/right RMS from Quantum 19/20. Prints L, R dB and the L-R balance per setting.
usage: hw_pan_test.py OUTDIR [PARAM|cc10] [values...]
  PARAM: SysEx id (40 = voice Pan, 249 = Multimode channel Pan); cc10: MIDI CC10 on channel 1 (0..127)
"""
import json, os, sys, time
import numpy as np, soundfile as sf, mido

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hw_lfosync_test as t      # noqa: E402

FS = 48000


def db(x):
    return 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-12)


def main():
    out = sys.argv[1]
    param = sys.argv[2] if len(sys.argv) > 2 else '40'
    cc = param == 'cc10'
    vals = [int(v) for v in sys.argv[3:]] or ([0, 16, 32, 48, 63, 64, 65, 80, 96, 112, 127] if cc else
                                              [-64, -48, -40, -32, -24, -16, -8, -1, 0, 1, 8, 16, 24, 32, 40, 48, 63])
    param = param if cc else int(param)
    os.makedirs(out, exist_ok=True)
    rig = t.Rig(); e = rig.e
    rig.setup()
    e.set(t.AMT, 0); time.sleep(0.2)
    rows = []
    for v in vals:
        if cc:
            rig.out.send(mido.Message('control_change', channel=0, control=10, value=v))
        else:
            e.set(param, v)
        time.sleep(0.25)
        st = rig.take(1.2)
        sf.write(os.path.join(out, f'p{param}_{v}.wav'), st, FS)
        on = t.onset(t.envelope(st))
        seg = st[on + 300 * 48:on + 1000 * 48]
        l, r = db(seg[:, 0]), db(seg[:, 1])
        rows.append(dict(param=param, value=v, l_db=round(float(l), 2), r_db=round(float(r), 2), bal_db=round(float(l - r), 2)))
        print(f'param {param} = {v:4d}: L {l:7.2f} dB  R {r:7.2f} dB  L-R {l - r:+7.2f} dB', flush=True)
    if cc:
        rig.out.send(mido.Message('control_change', channel=0, control=10, value=64))
    else:
        e.set(param, 0)
    e.set(t.DST, t.AMPVOL)
    e.close()
    json.dump(rows, open(os.path.join(out, f'pan_p{param}.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
