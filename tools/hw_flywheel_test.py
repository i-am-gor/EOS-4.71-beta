#!/usr/bin/env python3
"""Hardware test of the Sync7 LFO tempo flywheel (MIDI clock stop / resume / dropouts).

Preset 000 voice 0, key 72 = 801 Hz sine, LFO1 sine 1/4 Free Run -> Pitch (amount 20); measured as the
tone's instantaneous frequency. E4 Clock Source must be External. 100 BPM MIDI clock from the 828.
  S  Start + clock 4 s, Stop (FC) 4 s, Continue (FB) + clock 4 s, one held note
     expected: 1.667 Hz throughout; while stopped the phase runs on (one clock behind);
     after Continue the phase is back on the clock grid (count continues from the stop)
  C  CkQtr (cord source 147) -> Pitch instead of the LFO, same Start / Stop / Continue plan as S
     (Sync8 master clock flywheel): expected 1.667 Hz throughout, a ~2-clock pause at the stop, no jump
     on Continue (Ck sources count from note-on, not from the song position)
  D  Start + clock 10 s with dropouts of 4 clocks (100 ms) at 4 s and 8 clocks (200 ms) at 7 s
     expected: rate and grid phase unchanged across the dropouts (catch-up)
Per 1 s window: LFO rate (zero crossings) and phase offset against the clock grid (degrees, relative to
the first window). Grid = clocks the sender has counted (S: frozen while stopped) at 24 per cycle.
usage: hw_flywheel_test.py OUTDIR [S C D]
"""
import json, math, os, sys, threading, time
import numpy as np, soundfile as sf, sounddevice as sd, mido

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hw_lfosync_test as t      # noqa: E402
import hw_burst_test as hb       # noqa: E402
from hw_lfosync3_test import inst_f, rate_of, FS, PITCH   # noqa: E402

BPM = 100
HZ = BPM / 60.0                  # 1/4 = one cycle per quarter
PER = 60.0 / BPM / 24


def run_take(rig, out, tag, dur, plan):
    """plan(t) -> list of (time from recording start, msg) for the sender; returns st, clock log."""
    events = plan()
    hb.wait_silence(rig.dev)
    log = []
    pre = 1.0                     # clock runs 1 s before the recording
    t0 = time.perf_counter() + 0.2
    rec_holder = {}

    def sender():
        for at, msg in events:
            tgt = t0 + pre + at
            while True:
                d = tgt - time.perf_counter()
                if d <= 0:
                    break
                time.sleep(min(d, 0.0005) if d < 0.003 else d - 0.002)
            if msg == 'REC':
                rec_holder['rec'] = sd.rec(int(dur * FS), samplerate=FS, channels=hb.nch(), device=rig.dev,
                                           dtype='float32')
                rec_holder['t'] = time.perf_counter()
                continue
            rig.out.send(mido.Message(msg, channel=0, note=t.KEY, velocity=100) if msg in ('note_on', 'note_off')
                         else mido.Message(msg))
            log.append((time.perf_counter(), msg))

    th = threading.Thread(target=sender); th.start(); th.join()
    sd.wait()
    st = rec_holder['rec'][:, hb.CH[0]:hb.CH[1] + 1]
    sf.write(os.path.join(out, tag + '.wav'), st, FS)
    return st, log, rec_holder['t']


def clocks(a, b):
    n0 = math.ceil(a / PER)
    return [(k * PER, 'clock') for k in range(n0, int(b / PER) + 1) if a <= k * PER < b]


def analyse(st, log, t_rec, grid_counts, label):
    """grid_counts: True = grid follows clocks the sender counted (frozen while stopped),
    False = wall-clock grid from Start (dropouts: the sender kept playing)."""
    f = inst_f(st)
    t_start = next(tt for tt, m in log if m == 'start')
    ck = np.array([tt for tt, m in log if m == 'clock'])

    def grid(tabs):               # cycles at absolute time tabs
        if not grid_counts:
            return HZ * (tabs - t_start)
        n = np.searchsorted(ck, tabs)               # clocks sent before tabs
        last = ck[n - 1] if n else t_start
        frac = min(1.0, (tabs - last) / PER) if n and (tabs - last) < 2.5 * PER else 0.0
        return (n + frac) / 24.0

    on = t.onset(t.envelope(st))
    rows, ref = [], None
    for w0 in range(on + 300, len(f) - 1000, 1000):
        a, b = w0, w0 + 1000
        hz = rate_of(f, max(0, a - 1000), b + 1000)         # 3 s around the window (1.67 Hz needs >= 3 crossings)
        tt = np.arange(a, b) / 1000.0
        y = f[a:b] - f[a:b].mean()
        A = np.linalg.lstsq(np.stack([np.sin(2 * np.pi * HZ * tt), np.cos(2 * np.pi * HZ * tt)], 1), y,
                            rcond=None)[0]
        ph0 = math.atan2(A[1], A[0]) / (2 * math.pi)           # LFO phase at recording time 0 (fit at HZ)
        tm = (a + b) / 2000.0
        ph = ph0 + HZ * tm                                      # LFO cycles at window centre
        off = (ph - grid(t_rec + tm)) % 1.0
        if ref is None:
            ref = off
        d = ((off - ref + 0.5) % 1.0 - 0.5) * 360
        rows.append(dict(t=round(tm, 2), hz=round(hz, 4), grid_off_deg=round(d, 1)))
        print(f'{label} t {tm:5.2f} s: {hz:7.4f} Hz  phase vs grid {d:+7.1f} deg', flush=True)
    return rows


def continuity(st, segs, label, t_end=9.6):
    """Rate per segment (spectrum peak) and LFO phase vs a fixed 1.667 Hz reference in 0.6 s windows
    (relative to the first): flat = locked at tempo; a step = a jump; a slope = tempo error."""
    f = inst_f(st)

    def peak(x):
        x = x - x.mean(); n = 1 << 17
        F = np.abs(np.fft.rfft(x * np.hanning(len(x)), n)); fr = np.fft.rfftfreq(n, 1 / 1000)
        m = (fr > 0.5) & (fr < 10)
        return float(fr[np.argmax(F * m)])

    rates = [(a, b, round(peak(f[int(a * 1000):int(b * 1000)]), 3)) for a, b in segs]
    ref, ph = None, []
    for a in range(500, int(t_end * 1000), 600):
        tt = np.arange(a, a + 600) / 1000.0
        y = f[a:a + 600] - f[a:a + 600].mean()
        A = np.linalg.lstsq(np.stack([np.sin(2 * np.pi * HZ * tt), np.cos(2 * np.pi * HZ * tt)], 1), y,
                            rcond=None)[0]
        p = math.degrees(math.atan2(A[1], A[0]))
        ref = p if ref is None else ref
        ph.append((a / 1000.0, round((p - ref + 180) % 360 - 180, 1)))
    print(f'{label} rates (segment s, Hz): {rates}')
    print(f'{label} phase vs fixed {HZ:.3f} Hz (t s, deg): {ph}', flush=True)
    return dict(rates=rates, phase_vs_fixed=ph)


def main():
    out = sys.argv[1]
    tests = sys.argv[2:] or ['S', 'D']
    os.makedirs(out, exist_ok=True)
    rig = t.Rig(); e = rig.e
    rig.setup()
    e.set(t.AMT, 0); e.set(t.DST, PITCH); e.set(t.AMT, 20)
    e.set(105, 135); e.set(109, 1); time.sleep(0.3)          # LFO1 1/4, Free Run
    res = {}

    if 'S' in tests:
        def plan():
            ev = [(-1.0, 'start')] + clocks(-1.0, 4.2) + [(0.0, 'REC'), (0.2, 'note_on')]
            ev += [(4.2, 'stop'), (8.2, 'continue')] + clocks(8.2, 12.6) + [(12.6, 'note_off'), (12.61, 'stop')]
            return sorted(ev, key=lambda x: x[0] + (0 if x[1] in ('start', 'continue') else 1e-6))
        st, log, t_rec = run_take(rig, out, 'S_stop_resume', 13.0, plan)
        res['S'] = analyse(st, log, t_rec, True, 'S')
        res['S_cont'] = continuity(st, [(0.5, 4.2), (4.6, 8.2), (8.6, 9.6)], 'S')
        print('S: 0.5-4 s clock running, 4.5-8 s stopped (flywheel; grid frozen, so the phase offset grows '
              f'{HZ * 360:.0f} deg/s), 8.5- s resumed (offset back to ~0)')

    if 'C' in tests:
        e.set(t.AMT, 0); e.set(t.SRC, 147); e.set(t.AMT, 20); time.sleep(0.3)     # CkQtr -> Pitch

        def plan():
            ev = [(-1.0, 'start')] + clocks(-1.0, 4.2) + [(0.0, 'REC'), (0.2, 'note_on')]
            ev += [(4.2, 'stop'), (8.2, 'continue')] + clocks(8.2, 12.6) + [(12.6, 'note_off'), (12.61, 'stop')]
            return sorted(ev, key=lambda x: x[0] + (0 if x[1] in ('start', 'continue') else 1e-6))
        st, log, t_rec = run_take(rig, out, 'C_ckqtr_stop_resume', 13.0, plan)
        res['C_cont'] = continuity(st, [(0.5, 4.2), (4.6, 8.2), (8.6, 9.6)], 'C')
        e.set(t.AMT, 0); e.set(t.SRC, t.LFO1_SRC); e.set(t.AMT, 20)

    if 'D' in tests:
        def plan():
            ev = [(-1.0, 'start')] + clocks(-1.0, 4.0) + clocks(4.0 + 4 * PER, 7.0) + clocks(7.0 + 8 * PER, 10.6)
            ev += [(0.0, 'REC'), (0.2, 'note_on'), (10.6, 'note_off'), (10.61, 'stop')]
            return sorted(ev, key=lambda x: x[0] + (0 if x[1] == 'start' else 1e-6))
        st, log, t_rec = run_take(rig, out, 'D_dropouts', 11.0, plan)
        res['D'] = analyse(st, log, t_rec, False, 'D')
        res['D_cont'] = continuity(st, [(0.5, 4.0), (4.1, 7.0), (7.3, 9.6)], 'D')
        print('D: dropouts at 4.0 s (4 clocks) and 7.0 s (8 clocks); offset should stay ~0 throughout')

    e.set(t.AMT, 0); e.set(t.DST, t.AMPVOL); e.set(105, 64); e.set(109, 0)
    e.close()
    json.dump(res, open(os.path.join(out, 'flywheel.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
