#!/usr/bin/env python3
"""Unicorn: Lfo1Ck / Lfo2Ck on the EOS 4.71-beta2 image (patches/lfock/lfock.s, build_beta2.py).

usage: emu_lfock.py BASE.bin       (BASE = build/eos471_beta.bin)

Builds the release (--nocord) and the LfoCk image, then:
gap clear: init and ticks match the release (Rate 0..143).
A negative gap sum scales onto the 16 lengths (full scale 4032 = 1/32). Zero or positive matches the release.
d2 and d3 survive every tick.
"""
from __future__ import annotations

import os
import random
import struct
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_beta2  # noqa: E402

from unicorn import Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN
from unicorn.m68k_const import UC_M68K_REG_A7, UC_M68K_REG_D2, UC_M68K_REG_D3, UC_CPU_M68K_CFV4E

BASE, RET = 0x20000, 0x1000
RAM, STACK = 0x10000000, 0x10080000
VOICE, PARAMS = 0x10010000, 0x10011000
LFO1, LFO2 = VOICE + 0x188, VOICE + 0x1A8
GAP1, GAP2 = VOICE + 0x1A4, VOICE + 0x1A6
INIT1, INIT2, TICK1, TICK2 = 0x61A50, 0x61CDC, 0x61BC0, 0x61D5C
SEED, TICK, TPC, CLKMODE, CLKRATE = (
    0x1000229C, 0x10000428, 0x10000420, 0x1000042C, 0x10000434)
CLKUS, PPQ, ARPTEMPO, NOWMS = 0x1000043C, 0x1000041E, 0x1000719C, 0x10000450
CNT = 0x100003F0
DEST = 0x6344C
KTAB = (384, 192, 96, 72, 48, 36, 32, 24, 18, 16, 12, 9, 8, 6, 4, 3)
FULL = 4032  # controller CC 127 through panel amount -100 (stored byte -127)


class Emu:
    def __init__(self, img):
        self.img = img
        self.mu = mu = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
        mu.ctl_set_cpu_model(UC_CPU_M68K_CFV4E)
        mu.mem_map(0, 0x220000)
        mu.mem_write(BASE, img)
        mu.mem_write(RET, b"\x4e\x71")
        mu.mem_map(RAM, 0x81000)

    def w(self, a, fmt, *v):
        self.mu.mem_write(a, struct.pack(">" + fmt, *v))

    def r(self, a, fmt):
        return struct.unpack(">" + fmt, self.mu.mem_read(a, struct.calcsize(">" + fmt)))

    def call(self, fn, *args):
        sp = STACK - 0x200
        self.w(sp, "I" * (len(args) + 1), RET, *args)
        self.mu.reg_write(UC_M68K_REG_A7, sp)
        self.mu.emu_start(fn, RET, count=20000)

    def snap(self):
        return bytes(self.mu.mem_read(VOICE, 0x200)) + bytes(self.mu.mem_read(SEED, 4))

    def setup(self, seed, ms, tick=0, mode=0, tpc=20):
        self.mu.mem_write(VOICE, bytes(0x200))
        self.mu.mem_write(PARAMS, bytes(0x200))
        self.w(SEED, "I", seed)
        self.w(NOWMS, "I", ms)
        self.w(TICK, "I", tick)
        self.w(TPC, "H", tpc)
        self.w(CLKMODE, "I", mode)
        self.w(PPQ, "H", 480)
        self.w(ARPTEMPO, "I", 120)
        self.w(CLKRATE, "I", 0)
        self.w(CLKUS, "I", 0x412)
        self.w(CNT, "III", 0, ms - 100000 if ms > 100000 else 0, 0)

    def lfo(self, n, rate, shape=0, delay=0, var=0, sync=0):
        self.w(PARAMS, "BBBBB", rate, shape, delay, var, sync)
        self.call(INIT1 if n == 1 else INIT2, LFO1 if n == 1 else LFO2, PARAMS)

    def tick(self, n, k=1):
        self.mu.reg_write(UC_M68K_REG_D2, 0x13579BDF)
        self.mu.reg_write(UC_M68K_REG_D3, 0x2468ACE0)
        self.call(TICK1 if n == 1 else TICK2, LFO1 if n == 1 else LFO2, k)
        self.saved = (self.mu.reg_read(UC_M68K_REG_D2), self.mu.reg_read(UC_M68K_REG_D3))

    def regs_ok(self):
        return self.saved == (0x13579BDF, 0x2468ACE0)

    def set_cord(self, n, div):
        """Store the running sum the engine would leave for this division.

        LFO2's gap keeps the stock init value 1, so its word is one higher than the sum.
        """
        lo = 32 if div == 0 else ((div * FULL + 15) // 16) + 1
        hi = (((div + 1) * FULL - 1) // 16) + 1
        mag = (lo + hi) // 2
        word = (-mag + (1 if n == 2 else 0)) & 0xFFFF
        self.w(GAP1 if n == 1 else GAP2, "H", word)
        return mag


def expect(T, T0, d, tpc):
    P = KTAB[d] * tpc
    return ((T - T0) % P) * 65536 // P


def cstr(img, addr):
    o = addr - BASE
    e = img.find(0, o, o + 16)
    return img[o:e].decode() if e > o else None


def main():
    with tempfile.TemporaryDirectory() as td:
        ref, out = os.path.join(td, "ref.bin"), os.path.join(td, "out.bin")
        build_beta2.build(sys.argv[1], ref, cord=False)
        build_beta2.build(sys.argv[1], out, cord=True)
        base_img, cord_img = open(ref, "rb").read(), open(out, "rb").read()
    B, C = Emu(base_img), Emu(cord_img)
    rnd = random.Random(0xB2C0)
    fails, n = [], 0

    n += 1
    if cord_img[0x18:0x30].rstrip() != b"EOS 4.71-beta2 +LfoCk":
        fails.append(f"name {cord_img[0x18:0x30]!r}")
    for code, name, off in ((98, "Lfo1Ck", 0x1A4), (107, "Lfo2Ck", 0x1A6)):
        np, voff, fl = struct.unpack_from(">IHH", cord_img, DEST + 8 * code - BASE)
        n += 1
        if cstr(cord_img, np) != name or voff != off or fl != 0x200:
            fails.append(f"dest {code}: {cstr(cord_img, np)!r} voff={voff:#x} fl={fl:#x}")
    np, voff, fl = struct.unpack_from(">IHH", cord_img, DEST + 8 * 106 - BASE)
    n += 1
    if cstr(cord_img, np) != "Lag0in" or voff != 0x1C4 or fl != 0x200:
        fails.append(f"Lag0in moved: {cstr(cord_img, np)!r} voff={voff:#x} fl={fl:#x}")

    for case in range(80):
        lfo = 1 + case % 2
        rate = rnd.randrange(144)
        shape, sync = rnd.randrange(17), rnd.randrange(2)
        delay, var = rnd.randrange(128), rnd.randrange(128)
        seed, ms, tick0 = rnd.getrandbits(32), rnd.randrange(1, 10**6), rnd.randrange(1 << 16)
        for E in (B, C):
            E.setup(seed, ms, tick=tick0)
            E.w(GAP1, "I", 1)
            E.lfo(lfo, rate, shape, delay, var, sync)
        n += 1
        if B.snap() != C.snap():
            fails.append(f"gap-clear init lfo{lfo} rate {rate}")
            continue
        for step in range(8):
            k = rnd.choice([1, 2, 3])
            for E in (B, C):
                E.tick(lfo, k)
            n += 1
            if B.snap() != C.snap():
                fails.append(f"gap-clear tick lfo{lfo} rate {rate} step {step}")
                break

    for cc in range(128):
        mag = (cc * 127) >> 2
        d = None if mag == 0 else min(15, ((mag - 1) * 16) // FULL)
        for lfo in (1, 2):
            tpc, t0 = 20, 1000
            C.setup(1, 1000, tick=t0, tpc=tpc)
            C.w(VOICE + 0x2E, "I", t0)
            C.lfo(lfo, 40, 0, 0, 0, 1)
            word = (0 if mag == 0 else -mag) + (1 if lfo == 2 else 0)
            C.w(GAP1 if lfo == 1 else GAP2, "H", word & 0xFFFF)
            T = t0 + 500
            C.w(TICK, "I", T)
            C.tick(lfo, 1)
            ph = C.r((LFO1 if lfo == 1 else LFO2) + 0x12, "H")[0]
            n += 1
            if not C.regs_ok():
                fails.append(f"cc {cc} lfo{lfo}: d2/d3 clobbered {tuple(hex(r) for r in C.saved)}")
            if d is None:
                C2 = Emu(base_img)
                C2.setup(1, 1000, tick=t0, tpc=tpc)
                C2.w(VOICE + 0x2E, "I", t0)
                C2.lfo(lfo, 40, 0, 0, 0, 1)
                C2.w(GAP1, "I", 1)
                C2.w(TICK, "I", T)
                C2.tick(lfo, 1)
                if ph != C2.r((LFO1 if lfo == 1 else LFO2) + 0x12, "H")[0]:
                    fails.append(f"cc {cc} lfo{lfo}: idle diverged from beta2")
                continue
            e = expect(T, t0, d, tpc)
            if ph != e:
                fails.append(f"cc {cc} lfo{lfo}: phase {ph} != div {d} ({e})")

    for case in range(80):
        lfo, d = 1 + case % 2, rnd.randrange(16)
        tpc, t0 = 20, rnd.randrange(0, 1 << 20)
        C.setup(rnd.getrandbits(32), 1000, tick=t0, mode=0, tpc=tpc)
        C.w(VOICE + 0x2E, "I", t0)
        C.lfo(lfo, rnd.randrange(128), 0, 0, 0, 1)
        C.set_cord(lfo, d)
        p = LFO1 if lfo == 1 else LFO2
        T = t0
        for step in range(8):
            T += rnd.randrange(0, 4 * tpc)
            C.w(TICK, "I", T)
            C.tick(lfo, 1)
            ph = C.r(p + 0x12, "H")[0]
            e = expect(T, t0, d, tpc)
            n += 1
            if not C.regs_ok():
                fails.append(f"cord lfo{lfo} div {d}: d2/d3 clobbered")
                break
            if ph != e:
                fails.append(f"cord lfo{lfo} div {d} T {T}: phase {ph} != {e}")
                break

    for case in range(80):
        lfo = 1 + case % 2
        d_rate, d_cord = rnd.randrange(16), rnd.randrange(16)
        if d_rate == d_cord:
            d_cord = (d_cord + 1) & 15
        tpc, t0 = 20, rnd.randrange(0, 1 << 16)
        C.setup(1, 2000, tick=t0, tpc=tpc)
        C.w(VOICE + 0x2E, "I", t0)
        C.lfo(lfo, 128 + d_rate, 0, 0, 0, 0)
        C.set_cord(lfo, d_cord)
        p = LFO1 if lfo == 1 else LFO2
        T = t0 + rnd.randrange(1, 4000)
        C.w(TICK, "I", T)
        C.tick(lfo, 1)
        ph = C.r(p + 0x12, "H")[0]
        if not C.regs_ok():
            fails.append(f"override lfo{lfo}: d2/d3 clobbered")
        e_cord = expect(T, t0, d_cord, tpc)
        e_rate = expect(T, t0, d_rate, tpc)
        n += 1
        if ph != e_cord:
            fails.append(f"override lfo{lfo}: phase {ph} != cord {e_cord} (rate would be {e_rate})")

    print(f"{n} checks; {len(fails)} failures")
    for f in fails[:25]:
        print("  " + f)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: emu_lfock.py BASE.bin")
    main()
