#!/usr/bin/env python3
"""Fit the stage-word -> pole mapping to hardware frequency-response measurements.

Uses the measured curves (recordings/fr_<build>/<build>_curves.json) and the actual coefficient blocks
each build produces (computeFrames run in Unicorn on each image), for the 2/4/6-pole at Q 0 and 127.
Model per half-word: r = 1 - 2^((X - XR)/SX) ; f = F_REF_HZ * 2^((F - 215)/FPO) ; theta = 2*pi*f/FS
Pole sections DC-normalised, zero sections monic (as eos_filter). Morph m = freq/255, linear in X and F.
Fitted: XR, SX, FPO, FMIN (minimum angle for F near 0, Hz).
"""
import json, math, os, sys
import numpy as np
from scipy.optimize import minimize

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eos_filter as ef      # noqa: E402
import emu_obxa as emu       # noqa: E402
import sweep_test as sw      # noqa: E402

FS = 48000.0
BUILDS = {'stock': 'bin/eos470_flash_0x20000.bin', 'v2': 'build/eos470_obxa_v2.bin', 'v3b': 'build/eos470_obxa_v3b.bin'}
VT = {'2pole': 0x68878, '4pole': 0x688A4, '6pole': 0x688D0}


def blocks():
    out = {}
    for b, path in BUILDS.items():
        E = emu.Emu(open(path, 'rb').read())
        for name, vt in VT.items():
            for q in (0, 127):
                out[(b, name, q)] = sw.block_for(E, vt, q)
    return out


def model_db(blk, flags, m, f, p):
    XR, SX, FPO, FMIN = p
    z = np.exp(-1j * 2 * np.pi * f / FS)
    H = np.ones_like(f, dtype=complex)
    for t, w in sw.stages(blk, flags):
        x0, f0 = ef.half(w, True); x1, f1 = ef.half(w, False)
        X, F = x0 + (x1 - x0) * m, f0 + (f1 - f0) * m
        r = max(0.0, 1 - 2.0 ** ((X - XR) / SX))
        hz = max(FMIN, ef.F_REF_HZ * 2.0 ** ((F - 215) / FPO))
        th = min(np.pi, 2 * np.pi * hz / FS)
        a = 1 - 2 * r * np.cos(th) * z + r * r * z * z
        if t == 'P':
            H *= (1 - 2 * r * np.cos(th) + r * r) / a
        else:
            H *= a
    return 20 * np.log10(np.abs(H) + 1e-12)


def main():
    B = blocks()
    data = []
    for b in BUILDS:
        cv = json.load(open(f'recordings/fr_{b}/{b}_curves.json'))
        f = np.array(cv['f'])
        for name in VT:
            for q in (0, 127):
                for fv in (48, 96, 144, 192, 240):
                    meas = np.array(cv['curves'][f'{name}_q{q}_f{fv}'])
                    ref = np.median(meas[(f > 30) & (f < 50)])
                    m = (f > 30) & (f < 14000) & (meas - ref > -45)
                    data.append((b, name, q, fv, f[m], meas[m] - ref))

    def cost(p, subset=None):
        e = []
        for b, name, q, fv, f, y in data:
            if subset and b not in subset:
                continue
            blk, fl = B[(b, name, q)]
            mod = model_db(blk, fl, fv / 255, f, p)
            mod -= np.median(mod[f < 50])
            e.append(np.mean((mod - y) ** 2))
        return float(np.mean(e))

    p0 = [255.0, 16.0, 30.7, 90.0]
    print('initial model cost (dB^2):', round(cost(p0), 2), ' per build:', {b: round(cost(p0, {b}), 1) for b in BUILDS})
    r = minimize(cost, p0, method='Nelder-Mead', options=dict(maxiter=600, xatol=0.05, fatol=0.01))
    print('fitted XR, SX, FPO, FMIN:', np.round(r.x, 3), ' cost', round(r.fun, 2),
          ' per build:', {b: round(cost(r.x, {b}), 1) for b in BUILDS})
    json.dump(dict(XR=r.x[0], SX=r.x[1], FPO=r.x[2], FMIN=r.x[3]), open('notes/chip_model_fit.json', 'w'), indent=1)
    # per-run residuals for q0 4-pole
    for b, name, q, fv, f, y in data:
        if name != '2pole' and q == 0 and fv in (96, 144, 192):
            blk, fl = B[(b, name, q)]
            mod = model_db(blk, fl, fv / 255, f, r.x); mod -= np.median(mod[f < 50])
            i3m = f[np.argmax(y < -3)] if (y < -3).any() else float('nan')
            i3p = f[np.argmax(mod < -3)] if (mod < -3).any() else float('nan')
            print(f'  {b:5s} {name} q0 f{fv}: measured -3dB {i3m:7.0f} Hz, fitted model {i3p:7.0f} Hz')


if __name__ == '__main__':
    main()
