#!/usr/bin/env python3
"""LP+Fuzz v4 variants measured with the sine-sweep sample ("EOS 4.71 LPFuzz4 T").

Preset 000 voice 0, key 77 (F4) = 20 s log sweep 20 Hz-20 kHz at -12 dBFS, held until the sample ends.
One sweep per cutoff 96/128/200/255 and Q 0..127 step 16, for the switch value SW (default 15 = FH 0x90, FLO 0x90).
Reference: Swept EQ (menu 8) gain 64 = flat, at the start and the end. Raw takes saved as OUTDIR/<tag>.npy;
runs whose file exists are skipped (resumable). Quantum inputs 19/20 only.

usage: hw_lpfuzz_fr.py OUTDIR [SW | -]      (- = release build: no test switch, parameter 195 not touched)
"""
import json, math, os, sys, time
import numpy as np, mido

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eos_remote as er          # noqa: E402
import hw_burst_test as hb       # noqa: E402
from hw_freqresp import play, FILT_CORD_AMTS, REF_TYPE, REF_Q   # noqa: E402

LPF = 21
CUTS = (96, 128, 200, 255)
QS = (0, 16, 32, 48, 64, 80, 96, 112, 127)


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    dev = hb.device()
    e = er.Eos()
    e.out.send(mido.Message('program_change', channel=0, program=0)); time.sleep(0.5)
    e.set(223, 0); e.set(225, 0)
    for c in FILT_CORD_AMTS:
        e.set(c, 0)
    e.set(41, 0)
    logp = os.path.join(out, 'log.json')
    log = json.load(open(logp)) if os.path.exists(logp) else []

    def run(tag, ft, fv, q, sw=None):
        p = os.path.join(out, f'{tag}.npy')
        if os.path.exists(p):
            return
        if sw is not None:
            e.set(195, sw)
        e.set(82, ft); time.sleep(0.15); e.set(83, fv); e.set(84, q); time.sleep(0.2)
        got = e.get([82, 83, 84] + ([195] if sw is not None else []))
        x = play(e, dev)
        np.save(p, x.astype(np.float32))
        pk = round(20 * math.log10(float(np.abs(x).max()) + 1e-12), 1)
        log.append(dict(tag=tag, type=ft, cut=fv, q=q, sw=sw, params=got, peak_dbfs=pk))
        json.dump(log, open(logp, 'w'), indent=1)
        print(f'{tag:20s} {got}  peak {pk} dBFS', flush=True)

    run('ref_start', REF_TYPE, 128, REF_Q)
    arg = sys.argv[2] if len(sys.argv) > 2 else '15'
    sw = None if arg == '-' else int(arg)
    for cut in CUTS:
        for q in QS:
            run(f'{"rel" if sw is None else f"sw{sw}"}_c{cut}_q{q}', LPF, cut, q, sw)
    run('ref_end', REF_TYPE, 128, REF_Q)
    if sw is not None:
        e.set(195, 0)
    e.set(84, 0); e.set(83, 255); e.set(82, 1)
    e.close()


if __name__ == '__main__':
    main()
