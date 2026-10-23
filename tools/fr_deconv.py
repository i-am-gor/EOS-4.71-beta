#!/usr/bin/env python3
"""Swept-sine (Farina) analysis of sine-sweep takes: exact linear response and harmonic distortion per order,
independent of the sweep length.

The take is convolved with the inverse of the ideal exponential sweep (time-reversed, with a 6 dB/octave
amplitude correction). The linear impulse response lands at t = 0; harmonic k lands T * ln(k) / ln(F2 / F1)
earlier. Each is windowed (linear: up to half the gap to harmonic 2) and transformed to a frequency response.
Results per 1/3 octave 40 Hz .. 12.5 kHz: level (dB), THD (harmonics 2..5, dB re fundamental at the same input
frequency) and the frame peak, in the same format as lpfuzz_fr_analyze.analyse.

usage: fr_deconv.py TAKE.npy T_SECONDS             (prints the bands; import analyse() for use in reports)
"""
import math, sys
import numpy as np

FS, F1, F2 = 48000, 20.0, 20000.0
BANDS = [40 * 2 ** (i / 3) for i in range(26) if 40 * 2 ** (i / 3) <= 12600]


def sweep(T, rho=1.0):
    """The ideal sweep as played at rate rho (the E4 plays the sample slightly off its nominal rate)."""
    K = math.log(F2 / F1)
    t = np.arange(int(T / rho * FS)) / FS
    return np.sin(2 * np.pi * F1 * T / K * (np.exp(rho * t * K / T) - 1)), K


def inverse(T, rho=1.0):
    s, K = sweep(T, rho)
    t = np.arange(len(s)) / FS
    return s[::-1] * np.exp(-rho * t * K / T), K   # amplitude falls 6 dB/oct along the reversed sweep


def playback_rate(x, T):
    """Playback rate from the sweep's instantaneous frequency (zero crossings, 200 Hz .. 8 kHz):
    ln f(t) = ln(F1 rho) + rho K t / T, so the slope of ln f against t gives rho."""
    K = math.log(F2 / F1)
    zc = np.nonzero((x[:-1] < 0) & (x[1:] >= 0))[0] + 0.0
    if len(zc) < 1000:
        return 1.0
    t = zc[1:]; f = FS / np.diff(zc)
    tt, ff = [], []
    for i in range(0, len(t) - 64, 32):            # average over 64 periods
        fr = 64 / ((zc[i + 65] - zc[i + 1]) / FS)
        if 200 < fr < 8000:
            tt.append(t[i + 32] / FS); ff.append(math.log(fr))
    if len(tt) < 20:
        return 1.0
    slope = np.polyfit(tt, ff, 1)[0]
    return float(slope * T / K)


def analyse(x, T, harmonics=5, rho=None):
    if rho is None:
        rho = playback_rate(x, T)
    s, K = sweep(T, rho)
    inv, _ = inverse(T, rho)
    n = 1 << int(math.ceil(math.log2(len(x) + len(inv))))
    h = np.fft.irfft(np.fft.rfft(x, n) * np.fft.rfft(inv, n), n)
    # normalise with the sweep itself (so a pass-through gives 0 dB at every frequency)
    href = np.fft.irfft(np.fft.rfft(s, n) * np.fft.rfft(inv, n), n)
    z0 = int(np.argmax(np.abs(href)))
    # the take starts at an unknown delay: find the linear IR peak region by cross-correlation with the sweep
    c = np.fft.irfft(np.fft.rfft(x, n) * np.conj(np.fft.rfft(s, n)), n)
    lag = int(np.argmax(np.abs(c[:len(x)])))
    zl = z0 + lag
    gap2 = int(T / rho * math.log(2) / K * FS)
    pre = int(0.005 * FS)

    def response(z, L):
        seg = h[z - pre: z - pre + L].copy()
        w = np.ones(L); r = int(0.1 * L); w[-r:] = 0.5 + 0.5 * np.cos(np.linspace(0, np.pi, r))
        H = np.fft.rfft(seg * w, 1 << 18)
        R = np.fft.rfft(href[z0 - pre: z0 - pre + L] * w, 1 << 18)
        return np.fft.rfftfreq(1 << 18, 1 / FS), H / (R + 1e-30 * np.abs(R).max())
    L1 = gap2 // 2 + pre
    f, H1 = response(zl, L1)
    harm = []
    for k in range(2, harmonics + 2):
        zk = zl - int(T / rho * math.log(k) / K * FS)
        gk = int(T / rho * (math.log(k + 1) - math.log(k)) / K * FS)
        Lk = min(L1, gk // 2 + pre)
        if zk - pre < 0:
            break
        _, Hk = response(zk, Lk)
        harm.append((k, Hk))
    out = []
    for fc in BANDS:
        m = (f >= fc * 2 ** (-1 / 6)) & (f < fc * 2 ** (1 / 6))
        p1 = float(np.mean(np.abs(H1[m]) ** 2))
        ph = 0.0
        for k, Hk in harm:                         # harmonic k response is indexed by the input frequency
            if fc * k < 22000:
                ph += float(np.mean(np.abs(Hk[m]) ** 2))
        lvl = 10 * math.log10(p1 + 1e-30)
        out.append(dict(f=round(fc), level=round(lvl, 2), thd=round(10 * math.log10(ph / (p1 + 1e-30) + 1e-12), 1)))
    # frame peak per band from the take itself (where the sweep passes each band)
    t0 = lag
    for b in out:
        tc = T / rho * math.log(b['f'] / F1) / K
        a, z = int(t0 + (tc - 0.05) * FS), int(t0 + (tc + 0.05) * FS)
        seg = x[max(0, a):max(1, z)]
        b['peak'] = round(20 * math.log10(float(np.abs(seg).max()) + 1e-12), 1) if len(seg) else None
    return out


if __name__ == '__main__':
    x = np.load(sys.argv[1]); T = float(sys.argv[2])
    for b in analyse(x, T):
        print(b)
