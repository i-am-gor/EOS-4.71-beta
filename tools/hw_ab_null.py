#!/usr/bin/env python3
"""In-session A/B null test with the A/B firmware (EOS470_AB_switch.syx): patches switched at runtime.

usage: hw_ab_null.py OUTDIR [rounds]
Switch via SysEx parameter 195 = 32 + bits (bit 0 cord patch, bit 1 RFX skip). For each scenario of
hw_rfx_null (steady, trem, pan, send) the modes off(0), cords(1), rfx(2), both(3) are recorded in turn, for
ROUNDS rounds, each take a fresh note after the switch is set. Analysis per scenario and mode: median steady
level per channel, worst 10 ms envelope difference and aligned residual against the OFF takes, compared with
the spread between OFF takes themselves.
"""
import json, os, sys, time
import numpy as np, soundfile as sf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hw_lfosync_test as t     # noqa: E402
import hw_rfx_null as rn        # noqa: E402

FS = 48000
MODES = {0: 'off', 1: 'cords', 2: 'rfx', 3: 'both'}


def level(st):
    on = t.onset(t.envelope(st))
    x = st[on * 48 + int(0.2 * FS):on * 48 + int(2.6 * FS)]
    m = len(x) // 480
    r = 20 * np.log10(np.sqrt(np.mean(x[:m * 480].reshape(m, 480, 2) ** 2, axis=1)) + 1e-9)
    return [float(np.median(r[:, 0])), float(np.median(r[:, 1]))]


def main():
    out = sys.argv[1]
    rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    os.makedirs(out, exist_ok=True)
    rig = t.Rig(); e = rig.e
    rig.setup()
    takes = {}
    for name, sets in rn.SCEN.items():
        e.set(t.AMT, 0); e.set(t.AMT + 3, 0); e.set(t.DST, t.AMPVOL); e.set(105, 64)
        for p, v in sets:
            e.set(p, v)
        time.sleep(0.3)
        for r in range(rounds):
            for mode, mname in MODES.items():
                e.set(195, 32 + mode); time.sleep(0.15)
                for attempt in range(4):
                    st = rig.take(3.0)
                    if 20 * np.log10(np.abs(st).max() + 1e-12) > -60:
                        break
                    time.sleep(1.0)
                else:
                    raise SystemExit('no signal')
                fn = os.path.join(out, f'{name}_{mname}_{r}.wav')
                sf.write(fn, st, FS)
                takes.setdefault((name, mode), []).append(st)
                lv = level(st)
                print(f'{name:7s} round {r} {mname:5s}: L {lv[0]:7.2f} R {lv[1]:7.2f} dB', flush=True)
    e.set(195, 32)                                   # leave both patches off
    e.set(t.AMT, 0); e.set(t.AMT + 3, 0); e.set(t.DST, t.AMPVOL)
    e.close()
    res = []
    for name in rn.SCEN:
        offs = takes[(name, 0)]
        base = [rn.metrics(offs[i], offs[j]) for i in range(len(offs)) for j in range(i + 1, len(offs))]
        print(f'\n{name}: OFF vs OFF: residual worst {max(b[0] for b in base):6.1f} dB, envelope diff worst '
              f'{max(b[1] for b in base):.2f} dB; OFF level L/R {np.mean([level(x)[0] for x in offs]):.2f} / '
              f'{np.mean([level(x)[1] for x in offs]):.2f}')
        for mode in (1, 2, 3):
            ms = [rn.metrics(o, x) for o in offs for x in takes[(name, mode)]]
            lv = np.mean([level(x) for x in takes[(name, mode)]], axis=0)
            lo = np.mean([level(x) for x in offs], axis=0)
            r = dict(scenario=name, mode=MODES[mode], residual_worst=round(max(m[0] for m in ms), 1),
                     env_worst_db=round(max(m[1] for m in ms), 2), level_diff_l=round(float(lv[0] - lo[0]), 3),
                     level_diff_r=round(float(lv[1] - lo[1]), 3),
                     off_residual_worst=round(max(b[0] for b in base), 1), off_env_worst=round(max(b[1] for b in base), 2))
            res.append(r)
            print(f'  {MODES[mode]:5s} vs OFF: residual worst {r["residual_worst"]:6.1f} dB, envelope diff worst '
                  f'{r["env_worst_db"]:.2f} dB, mean level diff L {r["level_diff_l"]:+.3f} R {r["level_diff_r"]:+.3f} dB')
    json.dump(res, open(os.path.join(out, 'ab_null.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
