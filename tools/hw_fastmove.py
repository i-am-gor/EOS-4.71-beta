#!/usr/bin/env python3
"""Fast-move noise test: P000 voice 0 (test table, ModWl -> SLpScn), key 89 held, Mod Wheel slammed
0 -> 127 -> 0 -> 64 -> 127 -> 0 (instant jumps, 0.6 s apart). Records Quantum 19/20 and reports, per jump, the
transient energy above 5 kHz (1 ms frames, dB over the median of the take) in the 150 ms after the jump.

usage: hw_fastmove.py OUTDIR TAG [PROGRAM]
"""
import json, math, os, sys, time
import numpy as np, sounddevice as sd, soundfile as sf, mido
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eos_remote as er, hw_burst_test as hb     # noqa: E402

FS, KEY = 48000, 89
SEQ = [0, 127, 0, 64, 127, 0, 127, 0]


def main():
    out, tag = sys.argv[1], sys.argv[2]
    prog = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    os.makedirs(out, exist_ok=True)
    dev = hb.device(); e = er.Eos()
    e.out.send(mido.Message('program_change', channel=0, program=prog)); time.sleep(0.5)
    e.out.send(mido.Message('control_change', channel=0, control=1, value=0)); time.sleep(0.3)
    hb.wait_silence(dev, limit=10.0)
    rec = sd.rec(int((len(SEQ) * 0.6 + 1.5) * FS), samplerate=FS, channels=hb.nch(), device=dev, dtype='float32')
    time.sleep(0.2); t0 = time.time()
    e.out.send(mido.Message('note_on', channel=0, note=KEY, velocity=100)); time.sleep(0.6)
    marks = []
    for v in SEQ[1:]:
        e.out.send(mido.Message('control_change', channel=0, control=1, value=v)); marks.append(time.time() - t0)
        time.sleep(0.6)
    e.out.send(mido.Message('note_off', channel=0, note=KEY)); sd.wait()
    e.out.send(mido.Message('control_change', channel=0, control=1, value=0)); e.close()
    x = rec[:, hb.CH[0]:hb.CH[1] + 1].mean(axis=1)
    sf.write(os.path.join(out, f'{tag}.wav'), x, FS)
    on = int(np.argmax(np.abs(x) > 0.05 * np.abs(x).max())); start = on - int(0.0 * FS)
    X = np.fft.rfft(x); f = np.fft.rfftfreq(len(x), 1 / FS)
    hp = np.fft.irfft(np.where(f > 5000, X, 0), len(x))
    fr = int(0.001 * FS)
    e1 = np.array([np.sum(hp[i:i + fr] ** 2) for i in range(0, len(hp) - fr, fr)])
    held = e1[on // fr + 50: on // fr + int(len(SEQ) * 600)]
    med = np.median(held) + 1e-20
    res = []
    for i, mk in enumerate(marks):
        a = (on + int((mk - 0.6 + 0.6) * FS)) // fr            # jump time relative to note-on
        w = e1[a - 20:a + 150]
        res.append(dict(jump=f'{SEQ[i]}->{SEQ[i + 1]}', peak_db=round(10 * math.log10(w.max() / med), 1),
                        burst_ms=int(np.sum(w > med * 10))))
    print(tag, ' '.join(f'{r["jump"]}:{r["peak_db"]}dB/{r["burst_ms"]}ms' for r in res))
    json.dump(dict(tag=tag, jumps=res), open(os.path.join(out, f'{tag}.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
