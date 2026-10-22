#!/usr/bin/env python3
"""SLoop + Gain4X depth experiment on the test wavetable (P001 voice 0 edit buffer; restored afterwards).

usage: hw_sloop_gain_exp.py OUTDIR CONFIG [CONFIG ...]
CONFIG = "g:m[:amt]": g = 0 (ModWl -> SLoop directly) or 1 (ModWl -> Gain4X +100, then Gain4X -> SLoop),
         m = number of SLoop cords (amount amt, default +100).
Each config: cords 4..18 cleared, the config's cords written from cord 4, key 60 held, Mod Wheel (CC 1) stepped
0..127; per step the frame position is the energy-weighted harmonic number of the test table (frame n = harmonic n
of the frame-1 fundamental measured at CC 0); shift = (frame - 1) * 256 samples.
"""
import json, math, os, sys, time
import numpy as np, sounddevice as sd, soundfile as sf, mido

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eos_remote as er          # noqa: E402
import hw_burst_test as hb       # noqa: E402

FS, KEY, P = 48000, 89, 1
MODWL, GAIN4X, SLOOP = 17, 167, 53
CCS = [0, 4, 8, 16, 24, 32, 48, 64, 80, 96, 112, 127]
DWELL = 0.5
CORDS = range(4, 19)


def ids_of(cs):
    return [129 + 3 * (c - 1) + k for c in cs for k in range(3)]


def setcord(e, c, s, d, a):
    b = 129 + 3 * (c - 1)
    e.set(b, s); e.set(b + 1, d); e.set(b + 2, a & 0x3FFF)


def run(e, dev, g, m, amt):
    for c in CORDS:
        setcord(e, c, 0, 0, 0)
    c = 4
    if g:
        setcord(e, c, MODWL, GAIN4X, 100); c += 1
    for _ in range(m):
        setcord(e, c, GAIN4X if g else MODWL, SLOOP, amt); c += 1
    e.out.send(mido.Message('control_change', channel=0, control=1, value=0)); time.sleep(0.3)
    hb.wait_silence(dev, limit=10.0)
    n = len(CCS)
    rec = sd.rec(int((n * DWELL + 1.0) * FS), samplerate=FS, channels=hb.nch(), device=dev, dtype='float32')
    time.sleep(0.2)
    e.out.send(mido.Message('note_on', channel=0, note=KEY, velocity=100)); time.sleep(0.4)
    marks = []
    t0 = time.time()
    for v in CCS:
        e.out.send(mido.Message('control_change', channel=0, control=1, value=v))
        marks.append(time.time() - t0)
        time.sleep(DWELL)
    e.out.send(mido.Message('note_off', channel=0, note=KEY)); sd.wait()
    e.out.send(mido.Message('control_change', channel=0, control=1, value=0))
    return rec[:, hb.CH[0]:hb.CH[1] + 1].mean(axis=1), marks


TABLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'testsignals', 'wavetable',
                     'wt32x256_harmonics_pad2.wav')
_REF = None


def ref_table():
    """Harmonic magnitudes (1..32) of the 256-sample loop window at every shift 0..7936 of the test table."""
    global _REF
    if _REF is None:
        t, _ = sf.read(TABLE)
        t = t if t.ndim == 1 else t.mean(axis=1)
        shifts = np.arange(0, len(t) - 2 - 256 + 1)
        W = np.stack([t[2 + s:2 + s + 256] for s in shifts])
        H = np.abs(np.fft.rfft(W, axis=1))[:, 1:33]
        _REF = (shifts, H / (np.linalg.norm(H, axis=1, keepdims=True) + 1e-12))
    return _REF


def analyse(x, marks):
    on = int(np.argmax(np.abs(x) > 0.05 * np.abs(x).max()))
    base = on + int(0.4 * FS)                            # first CC sent 0.4 s after the note
    out = []
    f1 = None
    for i, mk in enumerate(marks):
        a = base + int((mk + 0.15) * FS)
        seg = x[a:a + int(0.3 * FS)]
        S = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2
        f = np.fft.rfftfreq(len(seg), 1 / FS)
        if f1 is None:
            f1 = f[np.argmax(np.where(f > 30, S, 0))]
        E = []
        for h in range(1, 33):
            band = (f > f1 * h * 0.97) & (f < f1 * h * 1.03)
            E.append(S[band].sum() if band.any() else 0.0)
        E = np.array(E)
        pos = float((np.arange(1, 33) * E).sum() / (E.sum() + 1e-20))
        shifts, H = ref_table()
        m = np.sqrt(E); m = m / (np.linalg.norm(m) + 1e-12)
        best = int(shifts[np.argmax(H @ m)])                # loop shift (samples) whose window matches best
        top = int(np.argmax(E)) + 1
        purity = float(E.max() / (E.sum() + 1e-20))
        out.append(dict(cc=CCS[i], frame=round(pos, 2), top=top, purity=round(purity, 2),
                        shift=best, level=round(10 * math.log10(S.sum() + 1e-20), 1)))
    return round(float(f1), 1), out


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    cfgs = []
    for a in sys.argv[2:]:
        p = [int(v) for v in a.split(':')]
        cfgs.append((p[0], p[1], p[2] if len(p) > 2 else 100))
    dev = hb.device()
    e = er.Eos()
    e.out.send(mido.Message('program_change', channel=0, program=P)); time.sleep(0.5)
    e.set(223, P); e.set(225, 0); time.sleep(0.2)
    keep = e.get(ids_of(CORDS))
    res = []
    try:
        for g, m, amt in cfgs:
            x, marks = run(e, dev, g, m, amt)
            tag = f'g{g}_m{m}_a{amt}'
            sf.write(os.path.join(out, tag + '.wav'), x, FS)
            f1, steps = analyse(x, marks)
            res.append(dict(gain=g, cords=m, amount=amt, f1=f1, steps=steps))
            print(f'{tag}: f1 {f1} Hz | shift by CC ' + '  '.join(f'{s["cc"]}:{s["shift"]}' for s in steps), flush=True)
            json.dump(res, open(os.path.join(out, 'exp.json'), 'w'), indent=1)
    finally:
        e.set(223, P); e.set(225, 0)
        b0 = 129 + 3 * (CORDS[0] - 1)
        for c in CORDS:
            b = 129 + 3 * (c - 1)
            setcord(e, c, keep[b], keep[b + 1], keep[b + 2])
        back = e.get(ids_of(CORDS))
        print('P001 cords 4-18 restored:', back == keep, flush=True)
        e.set(223, 0); e.set(225, 0)
        e.close()


if __name__ == '__main__':
    main()
