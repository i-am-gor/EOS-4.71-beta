#!/usr/bin/env python3
"""CPU-load measurement on the E4 with the LOADPROBE firmware (patches/probe/probe.s, SysEx param 195).

Scenarios: idle, then N held notes on preset 001 (one voice per key over the whole keyboard; preset 000
in the test bank only answers key 72), keys 64-N/2 .. 64+N/2-1 on MIDI channel 1.
Per scenario: main-loop passes/s (fewer = less CPU left for the UI/tasks; load = 1 - passes/idle),
voice ticks/s (about 100 per sounding voice when on time), mean and worst voice-tick lateness (ms).
usage: hw_load_probe.py OUTJSON [voices ...]   (default 0 8 16 32 48 64 96 128 0)
"""
import json, sys, time
import mido
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import eos_remote as er          # noqa: E402

P = 195
PROG = int(__import__('os').environ.get('PROG', '3'))


def read(e, v, tries=5):
    """Latch var v and read its three 11-bit pieces; retry the whole read if any reply is missing."""
    for _ in range(tries):
        e.set(P, v); time.sleep(0.03)
        parts = []
        for k in range(3):
            g = e.get([P], timeout=0.5)
            if P not in g:
                break
            parts.append(g[P] & 0x7FF)
        if len(parts) == 3:
            return parts[0] | parts[1] << 11 | parts[2] << 22
    raise RuntimeError(f'probe var {v}: no reply after {tries} tries')


def snap(e):
    return dict(t=time.perf_counter(), passes=read(e, 0), ticks=read(e, 1), latesum=read(e, 3))


def main():
    out = sys.argv[1]
    counts = [int(v) for v in sys.argv[2:]] or [0, 8, 16, 32, 48, 64, 96, 128, 0]
    e = er.Eos()
    o = e.out
    o.send(mido.Message('program_change', channel=0, program=PROG)); time.sleep(0.5)
    rows = []
    for nv in counts:
        notes = [(0, k) for k in range(64 - nv // 2, 64 - nv // 2 + nv)]
        for ch in range(16):
            o.send(mido.Message('control_change', channel=ch, control=123, value=0))
        time.sleep(1.5)
        e.set(P, 15)                               # clear worst lateness
        for ch, k in notes:
            o.send(mido.Message('note_on', channel=ch, note=k, velocity=100))
        time.sleep(1.0)
        a = snap(e)
        time.sleep(4.0)
        b = snap(e)
        late_max = read(e, 2)
        for ch, k in notes:
            o.send(mido.Message('note_off', channel=ch, note=k))
        dt = b['t'] - a['t']
        dp, dtk = (b['passes'] - a['passes']) & 0x1FFFFFFFF, (b['ticks'] - a['ticks']) & 0x1FFFFFFFF
        dl = (b['latesum'] - a['latesum']) & 0x1FFFFFFFF
        r = dict(notes=nv, passes_s=round(dp / dt), voices=round(dtk / dt / 100, 1),
                 late_mean_ms=round(dl / dtk, 3) if dtk else 0, late_max_ms=late_max)
        rows.append(r)
        print(f'{nv:3d} notes: main-loop passes/s {r["passes_s"]:8d}  voices {r["voices"]:6.1f}  '
              f'tick lateness mean {r["late_mean_ms"]:.3f} ms, worst {late_max} ms (incl. note-on burst)', flush=True)
    idle = rows[0]['passes_s'] if rows and rows[0]['notes'] == 0 else None
    if idle:
        for r in rows:
            r['load_vs_idle_pct'] = round(100 * (1 - r['passes_s'] / idle), 1)
            print(f'  {r["notes"]:3d} notes: {r["load_vs_idle_pct"]:5.1f} % of the idle main-loop throughput lost')
    o.send(mido.Message('program_change', channel=0, program=0))
    e.close()
    json.dump(rows, open(out, 'w'), indent=1)


if __name__ == '__main__':
    main()
