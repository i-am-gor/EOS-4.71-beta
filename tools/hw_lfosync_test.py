#!/usr/bin/env python3
"""Hardware test of the LFO tempo-sync build (EOS 4.70 v3d+LFO Sync).

Preset 000 voice 0, key 72 = 801 Hz sine. Filter wide open, one cord LFO -> AmpVol, all other
cord amounts 0. Capture from the Quantum (19/20), envelope demodulated, modulation rate measured.
  A  LFO1 stock rates 32/64/96 (table: 1.488 / 4.120 / 9.155 Hz) and synced divisions (internal clock)
  B  Key Sync vs Free Run phase at note-on (1/4), several notes at random times in one take
  C  LFO2 (cord source 104) at 1/8 and 1/8T
  X  external MIDI clock: we send 0xF8 at BPM (the E4 clock source must be External)
usage: hw_lfosync_test.py OUTDIR [A B C] | hw_lfosync_test.py OUTDIR X BPM
"""
import json, math, os, sys, threading, time
import numpy as np, sounddevice as sd, soundfile as sf, mido
from scipy.signal import hilbert, butter, sosfiltfilt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eos_remote as er          # noqa: E402
import hw_burst_test as hb       # noqa: E402

FS = 48000
KEY = 72
CORD = 10                                    # cord 11: ids 159/160/161
SRC, DST, AMT = 129 + 3 * CORD, 130 + 3 * CORD, 131 + 3 * CORD
LFO1_SRC, LFO2_SRC, AMPVOL = 96, 104, 64
STOCK_HZ = {32: 1.4877, 64: 4.1199, 96: 9.1553}
DIVS = {128: ('4bars', 384), 129: ('2bars', 192), 130: ('1bar', 96), 131: ('1/2.', 72), 132: ('1/2', 48),
        133: ('1/4.', 36), 134: ('1/2T', 32), 135: ('1/4', 24), 136: ('1/8.', 18), 137: ('1/4T', 16),
        138: ('1/8', 12), 139: ('1/16.', 9), 140: ('1/8T', 8), 141: ('1/16', 6), 142: ('1/16T', 4), 143: ('1/32', 3)}


def envelope(st):
    x = st.mean(axis=1).astype(np.float64)
    env = np.abs(hilbert(x))
    env = sosfiltfilt(butter(4, 60, fs=FS, output='sos'), env)
    return env[::48]                         # 1 kHz


def onset(env, thr=0.2):
    return int(np.argmax(env > thr * env.max()))


def mod_rate(env, t0, t1):
    """Modulation frequency from rising zero crossings of the envelope (mean removed)."""
    seg = env[t0:t1] - np.mean(env[t0:t1])
    s = np.signbit(seg)
    up = np.where(s[:-1] & ~s[1:])[0]
    if len(up) < 3:
        return float('nan'), 0.0
    # sub-sample crossing times
    tz = up + seg[up] / (seg[up] - seg[up + 1])
    f = (len(tz) - 1) / ((tz[-1] - tz[0]) / 1000.0)
    depth = 20 * math.log10(np.percentile(env[t0:t1], 98) / max(np.percentile(env[t0:t1], 2), 1e-9))
    return f, depth


def phase_at(env, t_on, f, win=None):
    """Phase (cycles, 0..1) of the envelope modulation at t_on, fitted over 2 cycles after it."""
    n = int(round(2000 / f)) if win is None else win
    a, b = t_on + 30, t_on + 30 + n
    t = (np.arange(a, b) - t_on) / 1000.0
    y = env[a:b] - env[a:b].mean()
    c, s = np.cos(2 * np.pi * f * t), np.sin(2 * np.pi * f * t)
    A = np.linalg.lstsq(np.stack([s, c], 1), y, rcond=None)[0]
    return (math.atan2(A[1], A[0]) / (2 * math.pi)) % 1.0


class Rig:
    def __init__(self):
        self.dev = hb.device()
        self.e = er.Eos()
        self.out = self.e.out

    def setup(self):
        e = self.e
        self.out.send(mido.Message('program_change', channel=0, program=0)); time.sleep(0.5)
        e.set(223, 0); e.set(225, 0)
        for c in range(18):
            e.set(131 + 3 * c, 0)
        e.set(82, 0); time.sleep(0.15); e.set(83, 255); e.set(84, 0)
        for base in (105, 110):                  # rate, shape sine, delay 0, variation 0, key sync
            e.set(base + 1, 1); e.set(base + 2, 0); e.set(base + 3, 0); e.set(base + 4, 0)
        e.set(SRC, LFO1_SRC); e.set(DST, AMPVOL); e.set(AMT, 60)
        time.sleep(0.3)

    def take(self, dur, notes=((0.2, None),)):
        hb.wait_silence(self.dev)
        total = dur + 0.8
        rec = sd.rec(int(total * FS), samplerate=FS, channels=hb.nch(), device=self.dev, dtype='float32')
        t0 = time.time()
        for at, length in notes:
            while time.time() - t0 < at:
                time.sleep(0.001)
            self.out.send(mido.Message('note_on', channel=0, note=KEY, velocity=100))
            hold = length if length else dur - at
            time.sleep(hold)
            self.out.send(mido.Message('note_off', channel=0, note=KEY))
        sd.wait()
        return rec[:, hb.CH[0]:hb.CH[1] + 1]


def main():
    out = sys.argv[1]
    tests = sys.argv[2:] or ['A', 'B', 'C']
    os.makedirs(out, exist_ok=True)
    rig = Rig(); e = rig.e
    rig.setup()
    res = dict(rows=[])

    def measure(tag, rate_id, rate, dur):
        e.set(rate_id, rate); time.sleep(0.2)
        back = e.get([rate_id]).get(rate_id)
        st = rig.take(dur)
        sf.write(os.path.join(out, tag + '.wav'), st, FS)
        env = envelope(st)
        on = onset(env)
        f, depth = mod_rate(env, on + 300, len(env) - 900)
        r = dict(tag=tag, rate=rate, readback=back, hz=round(f, 4), depth_db=round(depth, 1))
        res['rows'].append(r)
        print(f'{tag:14s} rate {rate:3d} (read {back}) -> {f:7.4f} Hz  depth {depth:4.1f} dB', flush=True)
        return f

    if 'A' in tests:
        for rate, hz in STOCK_HZ.items():
            f = measure(f'A_stock_{rate}', 105, rate, 5.0)
            print(f'    stock table {hz:.4f} Hz, error {100 * (f / hz - 1):+.2f}%')
        q = {}
        for rate in (130, 132, 133, 134, 135, 136, 137, 138, 139, 140, 141, 142, 143):
            name, clocks = DIVS[rate]
            dur = 9.0 if clocks >= 48 else 5.0
            f = measure(f'A_{name.replace("/", "_")}', 105, rate, dur)
            q[rate] = f * clocks / 24.0          # quarter notes per second
        bpms = {DIVS[r][0]: round(60 * v, 2) for r, v in q.items()}
        res['bpm_per_division'] = bpms
        print('implied tempo per division (BPM):', bpms, flush=True)

    if 'B' in tests:
        e.set(105, 135)
        rng = np.random.default_rng(7)
        for sync, label in ((0, 'keysync'), (1, 'freerun')):
            e.set(109, sync); time.sleep(0.2)
            notes, t = [], 0.3
            for _ in range(6):
                notes.append((t, 1.3)); t += 1.3 + float(rng.uniform(0.35, 0.95))
            st = rig.take(t + 0.2, notes)
            sf.write(os.path.join(out, f'B_{label}.wav'), st, FS)
            env = envelope(st)
            # onsets
            on, ons, i = env > 0.2 * env.max(), [], 0
            while i < len(on):
                if on[i]:
                    ons.append(i); i += 1000
                else:
                    i += 1
            f = mod_rate(env, ons[0] + 300, ons[0] + 1250)[0]
            ph = [phase_at(env, o, f, win=900) for o in ons]
            grid = [(p - f * o / 1000.0) % 1.0 for p, o in zip(ph, ons)]
            def spread(v):
                z = np.exp(2j * np.pi * np.array(v))
                return round(float(np.degrees(np.sqrt(-2 * np.log(abs(z.mean()) + 1e-12)))), 1)
            r = dict(tag=f'B_{label}', hz=round(f, 4), onsets_ms=ons, phase_at_onset=[round(p, 3) for p in ph],
                     onset_phase_spread_deg=spread(ph), grid_phase_spread_deg=spread(grid))
            res['rows'].append(r)
            print(f'B {label}: f {f:.3f} Hz, phase at note-on {r["phase_at_onset"]}, spread vs note-on '
                  f'{r["onset_phase_spread_deg"]} deg, vs clock grid {r["grid_phase_spread_deg"]} deg', flush=True)
        e.set(109, 0)

    if 'C' in tests:
        e.set(AMT, 0); e.set(105, 64)
        e.set(SRC, LFO2_SRC); e.set(AMT, 60); time.sleep(0.2)
        print('cord source read back:', e.get([SRC]))
        for rate in (138, 140, 64):
            measure(f'C_lfo2_{rate}', 110, rate, 5.0)
        e.set(SRC, LFO1_SRC)

    if 'X' in tests:
        bpm = float(sys.argv[3])
        stop = threading.Event()
        def clock():
            per = 60.0 / bpm / 24
            nxt = time.perf_counter()
            rig.out.send(mido.Message('start'))
            while not stop.is_set():
                rig.out.send(mido.Message('clock'))
                nxt += per
                while time.perf_counter() < nxt:
                    time.sleep(0.0005)
            rig.out.send(mido.Message('stop'))
        th = threading.Thread(target=clock, daemon=True); th.start()
        time.sleep(2.0)                           # let the E4 measure the tempo
        for rate in (135, 138, 140):
            f = measure(f'X_{bpm:g}_{DIVS[rate][0].replace("/", "_")}', 105, rate, 6.0)
            exp = bpm / 60 * 24 / DIVS[rate][1]
            print(f'    expected {exp:.4f} Hz at {bpm:g} BPM, error {100 * (f / exp - 1):+.2f}%')
        stop.set(); th.join()

    e.set(AMT, 0); e.set(105, 64); e.set(110, 64)
    e.close()
    name = 'lfosync_results' + ('_X' if 'X' in tests else '') + '.json'
    json.dump(res, open(os.path.join(out, name), 'w'), indent=1)


if __name__ == '__main__':
    main()
