#!/usr/bin/env python3
"""Hardware test of LFO Sync3 (EOS 4.70 v3d+LFO Sync3), LFO measured through Pitch.

Preset 000 voice 0, key 72 = 801 Hz sine; cord 11 = LFO -> Pitch (amount 20); other cords off.
The LFO waveform is the tone's instantaneous frequency (Hilbert phase, 10 ms smoothing).
  I  internal: stock rate 64 (4.12 Hz), 1/4 and 1/8T with no MIDI clock
  M  MIDI clock 60/100/140 BPM: 1/4, 1/8, 1/8T on LFO1, 1/8T on LFO2
  P  phase: Key Sync vs Free Run, 6 notes at random times under 100 BPM clock started with FA
  V  (Sync4 test build) 1/4 under 100 BPM clock with Variation 0 (ports 0+1) and 1..5 (single port 0..4)
  S  clock stop: 1/4 under 100 BPM, clock stops mid-note -> internal tempo
usage: hw_lfosync3_test.py OUTDIR [I M P S]
"""
import json, math, os, sys, threading, time
import numpy as np, soundfile as sf, sounddevice as sd, mido
from scipy.signal import hilbert

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hw_lfosync_test as t      # noqa: E402
import hw_burst_test as hb       # noqa: E402

FS = 48000
PITCH = 48
CLOCKS = {135: 24, 138: 12, 140: 8}


def inst_f(st):
    x = st.mean(axis=1)
    f = np.diff(np.unwrap(np.angle(hilbert(x)))) * FS / 2 / np.pi
    return np.convolve(f, np.ones(480) / 480, 'same')[::48]          # 1 kHz


def rate_of(f, a, b):
    s = f[a:b] - np.median(f[a:b])
    sb = np.signbit(s)
    up = np.where(sb[:-1] & ~sb[1:])[0]
    if len(up) < 3:
        return float('nan')
    tz = up + s[up] / (s[up] - s[up + 1])
    return (len(tz) - 1) / ((tz[-1] - tz[0]) / 1000.0)


def phase_fit(f, t_on, hz, n):
    a, b = t_on + 40, t_on + 40 + n
    tt = (np.arange(a, b) - t_on) / 1000.0
    y = f[a:b] - f[a:b].mean()
    A = np.linalg.lstsq(np.stack([np.sin(2 * np.pi * hz * tt), np.cos(2 * np.pi * hz * tt)], 1), y, rcond=None)[0]
    return (math.atan2(A[1], A[0]) / (2 * math.pi)) % 1.0


def spread_deg(v):
    z = np.exp(2j * np.pi * np.array(v))
    return round(float(np.degrees(np.sqrt(-2 * np.log(abs(z.mean()) + 1e-12)))), 1)


class Clock:
    def __init__(self, out, bpm, start=True):
        self.out, self.bpm, self.stop_ev = out, bpm, threading.Event()
        self.t_start = None
        self.th = threading.Thread(target=self.run, args=(start,), daemon=True)
        self.th.start()

    def run(self, start):
        per = 60.0 / self.bpm / 24
        if start:
            self.out.send(mido.Message('start'))
        self.t_start = nxt = time.perf_counter()
        while not self.stop_ev.is_set():
            self.out.send(mido.Message('clock'))
            nxt += per
            while time.perf_counter() < nxt:
                time.sleep(0.0005)

    def stop(self):
        self.stop_ev.set(); self.th.join()
        self.out.send(mido.Message('stop'))


def main():
    out = sys.argv[1]
    tests = sys.argv[2:] or ['I', 'M', 'P', 'S']
    os.makedirs(out, exist_ok=True)
    rig = t.Rig(); e = rig.e
    rig.setup()
    e.set(t.AMT, 0); e.set(t.DST, PITCH); e.set(t.AMT, 20); time.sleep(0.2)
    rows = []

    def take(tag, dur, notes=((0.2, None),)):
        st = rig.take(dur, notes)
        sf.write(os.path.join(out, tag + '.wav'), st, FS)
        f = inst_f(st)
        return st, f, t.onset(t.envelope(st))

    def meas(tag, lfo, rate, expect, dur=6.0):
        e.set(105 if lfo == 1 else 110, rate); time.sleep(0.25)
        st, f, on = take(tag, dur)
        hz = rate_of(f, on + 200, on + int(dur * 1000) - 300)
        err = 100 * (hz / expect - 1) if expect else float('nan')
        rows.append(dict(tag=tag, lfo=lfo, rate=rate, hz=round(hz, 4), expect=round(expect, 4), err_pct=round(err, 2)))
        print(f'{tag:22s} LFO{lfo} rate {rate}: {hz:7.4f} Hz  expected {expect:7.4f}  error {err:+6.2f}%', flush=True)

    if 'I' in tests:
        meas('I_stock64', 1, 64, 4.1199)
        meas('I_1_4', 1, 135, 2.0)
        meas('I_1_8T', 1, 140, 6.0)

    if 'M' in tests:
        for bpm in (60, 100, 140):
            ck = Clock(rig.out, bpm); time.sleep(1.5)
            for rate, k in CLOCKS.items():
                meas(f'M{bpm}_lfo1_{rate}', 1, rate, bpm / 60 * 24 / k)
            e.set(t.SRC, t.LFO2_SRC); e.set(110, 140); time.sleep(0.2)
            meas(f'M{bpm}_lfo2_140', 2, 140, bpm / 60 * 3)
            e.set(t.SRC, t.LFO1_SRC); e.set(110, 64)
            ck.stop(); time.sleep(0.5)

    if 'P' in tests:
        e.set(105, 135)
        rng = np.random.default_rng(11)
        hz = 100 / 60
        for sync, label in ((0, 'keysync'), (1, 'freerun')):
            e.set(109, sync); time.sleep(0.2)
            ck = Clock(rig.out, 100); time.sleep(1.0)
            notes, tt = [], 0.3
            for _ in range(6):
                notes.append((tt, 1.6)); tt += 1.6 + float(rng.uniform(0.3, 0.9))
            hb.wait_silence(rig.dev)
            rec = sd.rec(int((tt + 1.0) * FS), samplerate=FS, channels=hb.nch(), device=rig.dev, dtype='float32')
            t_rec = time.perf_counter()
            for at, length in notes:
                while time.perf_counter() - t_rec < at:
                    time.sleep(0.001)
                rig.out.send(mido.Message('note_on', channel=0, note=t.KEY, velocity=100))
                time.sleep(length)
                rig.out.send(mido.Message('note_off', channel=0, note=t.KEY))
            sd.wait()
            ck.stop()
            st = rec[:, hb.CH[0]:hb.CH[1] + 1]
            sf.write(os.path.join(out, f'P_{label}.wav'), st, FS)
            f, env = inst_f(st), t.envelope(st)
            on0 = t.onset(env)                      # first note; the rest from the schedule
            ons = [on0 + int(round((at - notes[0][0]) * 1000)) for at, _ in notes]
            ph = [phase_fit(f, o, hz, 1200) for o in ons]
            grid = [(p - hz * ((o / 1000.0) + (t_rec - ck.t_start))) % 1.0 for p, o in zip(ph, ons)]
            r = dict(tag=f'P_{label}', onsets=len(ons), phase_at_onset=[round(p, 3) for p in ph],
                     grid_phase=[round(g, 3) for g in grid],
                     onset_spread_deg=spread_deg(ph), grid_spread_deg=spread_deg(grid))
            rows.append(r)
            print(f'P {label}: {len(ons)} notes; LFO phase at note-on {r["phase_at_onset"]} '
                  f'(spread {r["onset_spread_deg"]} deg); vs MIDI Start grid {r["grid_phase"]} '
                  f'(spread {r["grid_spread_deg"]} deg)', flush=True)
        e.set(109, 0)

    if 'V' in tests:
        ck = Clock(rig.out, 100); time.sleep(1.5)
        for var in range(6):
            e.set(108, var); time.sleep(0.2)
            meas(f'V100_var{var}', 1, 135, 100 / 60, dur=5.0)
        ck.stop(); e.set(108, 0)
        for var in (0, 3):
            e.set(108, var); time.sleep(0.2)
            meas(f'Vnoclk_var{var}', 1, 135, 2.0, dur=5.0)
        e.set(108, 0)

    if 'S' in tests:
        e.set(105, 135); time.sleep(0.2)
        ck = Clock(rig.out, 100); time.sleep(1.5)
        hb.wait_silence(rig.dev)
        rec = sd.rec(int(9.0 * FS), samplerate=FS, channels=hb.nch(), device=rig.dev, dtype='float32')
        time.sleep(0.2)
        rig.out.send(mido.Message('note_on', channel=0, note=t.KEY, velocity=100))
        time.sleep(4.0)
        ck.stop()                                  # clock stops 4 s into the note
        time.sleep(4.0)
        rig.out.send(mido.Message('note_off', channel=0, note=t.KEY)); sd.wait()
        st = rec[:, hb.CH[0]:hb.CH[1] + 1]
        sf.write(os.path.join(out, 'S_stop.wav'), st, FS)
        f = inst_f(st); on = t.onset(t.envelope(st))
        a, b = rate_of(f, on + 300, on + 3900), rate_of(f, on + 4600, on + 7900)
        rows.append(dict(tag='S_stop', hz_clock=round(a, 4), hz_after_stop=round(b, 4)))
        print(f'S clock stop: {a:.4f} Hz with 100 BPM clock (expect 1.6667), {b:.4f} Hz after stop '
              f'(internal tempo; 2.0 at 120 BPM)', flush=True)

    e.set(t.AMT, 0); e.set(t.DST, t.AMPVOL); e.set(105, 64); e.set(110, 64); e.set(109, 0)
    e.close()
    json.dump(rows, open(os.path.join(out, 'sync3_' + ''.join(tests) + '.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
