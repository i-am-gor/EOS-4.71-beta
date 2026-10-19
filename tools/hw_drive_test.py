#!/usr/bin/env python3
"""v3c Drive test: does raising the filter gain word saturate cleanly or wrap?

Preset 000 voice 0, key 72 = 801 Hz sine (-12 dBFS sample). For 2/4/6-pole, filter open (freq 255, Q 0)
and resonant (freq 107, Q 127), Drive 0..127 is set over SysEx and a 3 s take recorded (Quantum 19/20).
Per take: RMS level, THD (harmonics 2-10 of the strongest tone), non-harmonic residual (noise/wrap).
First finds which editor SysEx parameter (85..92) is the filter's 3rd parameter (Drive).

usage: hw_drive_test.py OUTDIR
"""
import json, math, os, sys, time
import numpy as np, sounddevice as sd, soundfile as sf, mido

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eos_remote as er          # noqa: E402
import hw_burst_test as hb       # noqa: E402

FS = 48000
KEY = 72
DRIVES = (0, 16, 32, 48, 64, 80, 96, 112, 127)


def take(e, dev, dur=2.5):
    hb.wait_silence(dev)
    rec = sd.rec(int((dur + 0.8) * FS), samplerate=FS, channels=hb.nch(), device=dev, dtype='float32')
    time.sleep(0.2)
    e.out.send(mido.Message('note_on', channel=0, note=KEY, velocity=100)); time.sleep(dur)
    e.out.send(mido.Message('note_off', channel=0, note=KEY)); sd.wait()
    return rec[:, hb.CH[0]:hb.CH[1] + 1]


def analyse(st):
    x = st.mean(axis=1)
    seg = x[int(0.6 * FS):int(2.4 * FS)]
    n = len(seg)
    S = np.abs(np.fft.rfft(seg * np.blackman(n))) ** 2
    f = np.fft.rfftfreq(n, 1 / FS)
    k0 = int(np.argmax(S[f > 50])) + int(np.argmax(f > 50))
    f0 = f[k0]
    mask = np.zeros_like(S, bool)
    harm = []
    for h in range(1, 11):
        m = np.abs(f - f0 * h) < 15
        mask |= m
        harm.append(S[m].sum())
    tot = S[f > 20].sum()
    thd = 10 * math.log10(sum(harm[1:]) / harm[0] + 1e-15)
    resid = 10 * math.log10(S[(f > 20) & ~mask].sum() / tot + 1e-15)
    rms = 20 * math.log10(math.sqrt(float(np.mean(seg ** 2))) + 1e-12)
    pk = 20 * math.log10(float(np.abs(st).max()) + 1e-12)
    odd = sum(harm[2::2]); even = sum(harm[1::2])
    return dict(f0=round(float(f0), 1), rms_dbfs=round(rms, 1), peak_dbfs=round(pk, 1), thd_db=round(thd, 1),
                noise_db=round(resid, 1), odd_over_even_db=round(10 * math.log10((odd + 1e-20) / (even + 1e-20)), 1))


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    dev = hb.device()
    e = er.Eos()
    e.out.send(mido.Message('program_change', channel=0, program=0)); time.sleep(0.5)
    e.set(223, 0); e.set(225, 0)
    for c in (137, 140, 143, 146, 149, 152, 155):
        e.set(c, 0)
    # find the Drive parameter id: LP2 open; candidate set to 127 should raise the level
    e.set(82, 0); time.sleep(0.15); e.set(83, 255); e.set(84, 0)
    base = analyse(take(e, dev))['rms_dbfs']
    drive_id = None
    for pid in range(85, 93):
        before = e.get([pid]).get(pid)
        e.set(pid, 127); time.sleep(0.2)
        got = e.get([pid]).get(pid)
        lvl = analyse(take(e, dev))['rms_dbfs']
        print(f'param {pid}: read {before} -> {got}, level {base} -> {lvl} dBFS', flush=True)
        e.set(pid, before if before is not None else 0)
        if got == 127 and abs(lvl - base) > 1.0:
            drive_id = pid
            break
    if drive_id is None:
        print('Drive parameter not found over SysEx; set Drive on the front panel instead.')
        e.close(); return
    print(f'Drive = SysEx parameter {drive_id}', flush=True)
    rows = []
    for ft, name in ((0, '2pole'), (1, '4pole'), (2, '6pole')):
        for fv, q, cond in ((255, 0, 'open'), (107, 127, 'res')):
            e.set(82, ft); time.sleep(0.15); e.set(83, fv); e.set(84, q)
            for d in DRIVES:
                e.set(drive_id, d); time.sleep(0.15)
                st = take(e, dev)
                tag = f'{name}_{cond}_drive{d}'
                sf.write(os.path.join(out, tag + '.wav'), st, FS)
                r = dict(tag=tag, filter=name, cond=cond, drive=d, **analyse(st))
                rows.append(r)
                print(f"{tag:22s} rms {r['rms_dbfs']:6.1f}  peak {r['peak_dbfs']:6.1f}  THD {r['thd_db']:6.1f} dB  "
                      f"noise {r['noise_db']:6.1f} dB  odd/even {r['odd_over_even_db']:5.1f}", flush=True)
            e.set(drive_id, 0)
    e.close()
    json.dump(dict(drive_id=drive_id, rows=rows), open(os.path.join(out, 'drive_results.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
