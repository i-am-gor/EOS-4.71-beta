#!/usr/bin/env python3
"""Per-stage voice-tick timing on the E4 with the TIMEPROBE firmware (SysEx param 195).
Program PROG (default 3), N held keys centred on 64; reads all stage accumulators before and after a hold
window. Per stage: us per call, calls per voice tick, us per voice tick, share of the whole tick.
Note: each wrapped call adds the wrapper's own overhead (~40 instructions) to the whole-tick figure only.
usage: hw_timeprobe.py OUTJSON [voices ...]   (default 32 64)
"""
import json, os, sys, time
import mido
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eos_remote as er            # noqa: E402
import hw_load_probe as L          # noqa: E402  (read() with retries, param 195)
from build_timeprobe import NAMES  # noqa: E402

PROG = int(os.environ.get('PROG', '3'))
AB_MODE = os.environ.get('AB_MODE')      # A/B build: switch value (0..3) set before measuring


def snap(e):
    t = time.perf_counter()
    v = [L.read(e, i) for i in range(24)]
    return t, v


def main():
    out = sys.argv[1]
    counts = [int(x) for x in sys.argv[2:]] or [32, 64]
    e = er.Eos(); o = e.out
    o.send(mido.Message('program_change', channel=0, program=PROG)); time.sleep(0.6)
    if AB_MODE is not None:
        e.set(195, 32 + int(AB_MODE)); time.sleep(0.2)
    trr = L.read(e, 24)
    us_per_count = 500.0 / (trr + 1)
    print(f'timer 1: TRR1 = {trr} -> {us_per_count * 1000:.1f} ns per count', flush=True)
    res = []
    for nv in counts:
        keys = list(range(64 - nv // 2, 64 - nv // 2 + nv))
        for ch in range(16):
            o.send(mido.Message('control_change', channel=ch, control=123, value=0))
        time.sleep(1.5)
        for k in keys:
            o.send(mido.Message('note_on', channel=0, note=k, velocity=100))
        time.sleep(1.0)
        ta, a = snap(e)
        time.sleep(4.0)
        tb, b = snap(e)
        for k in keys:
            o.send(mido.Message('note_off', channel=0, note=k))
        d = [(b[i] - a[i]) & 0x1FFFFFFFF for i in range(24)]
        ticks = d[1] or 1
        rows = []
        for k, name in enumerate(NAMES):
            acc, cnt = d[2 * k], d[2 * k + 1]
            rows.append(dict(stage=name, calls=cnt, us_per_call=round(acc * us_per_count / cnt, 2) if cnt else 0,
                             calls_per_tick=round(cnt / ticks, 2), us_per_tick=round(acc * us_per_count / ticks, 2)))
        total = rows[0]['us_per_tick']
        dt = tb - ta
        cpu = d[0] * us_per_count / 1e6 / dt * 100
        print(f'\n{nv} notes: {ticks / dt:.0f} voice ticks/s, whole tick {total:.1f} us -> {cpu:.1f} % CPU in voice ticks')
        print(f'  {"stage":18s} {"us/call":>8s} {"calls/tick":>10s} {"us/tick":>8s} {"share":>6s}')
        for r in rows:
            sh = 100 * r['us_per_tick'] / total if total else 0
            r['share_pct'] = round(sh, 1)
            print(f'  {r["stage"]:18s} {r["us_per_call"]:8.2f} {r["calls_per_tick"]:10.2f} {r["us_per_tick"]:8.2f} {sh:5.1f}%')
        inner = sum(r['us_per_tick'] for r in rows[1:])
        print(f'  {"(tick body + wrappers)":18s} {"":8s} {"":10s} {total - inner:8.2f} {100 * (total - inner) / total:5.1f}%')
        res.append(dict(notes=nv, ticks_s=round(ticks / dt), cpu_pct=round(cpu, 1), trr=trr, stages=rows))
    o.send(mido.Message('program_change', channel=0, program=0))
    e.close()
    json.dump(res, open(out, 'w'), indent=1)


if __name__ == '__main__':
    main()
