#!/usr/bin/env python3
"""Emulator test of the compact plugin port-map builders (patches/portmap/portmap.s) against stock.

usage: emu_portmap.py STOCK.bin NEW.bin
Runs builder A (member pointer 0x15FAC4) and B (0x15FAD4) of each image with random this / a4 / callee-saved
registers. The callee 0x15D50C is replaced by rts; a hook logs its 19 arguments, returns a counter in d0 and trashes
d1/a0/a1. Required: identical call logs, d0, d2-d7/a2-a6 and sp on return. Then mutation checks: a changed table
byte, count or loop bound must be caught.
"""
import os, random, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import emu_p2k as ep        # noqa: E402
from unicorn import UC_HOOK_CODE   # noqa: E402
from unicorn.m68k_const import *   # noqa: E402,F403

BASE, CALLEE, PA, PB = 0x20000, 0x15D50C, 0x15FAC4, 0x15FAD4
SAVED = [UC_M68K_REG_D2, UC_M68K_REG_D3, UC_M68K_REG_D4, UC_M68K_REG_D5, UC_M68K_REG_D6, UC_M68K_REG_D7,
         UC_M68K_REG_A2, UC_M68K_REG_A3, UC_M68K_REG_A4, UC_M68K_REG_A5, UC_M68K_REG_A6]


def rig(img):
    E = ep.Emu(img)
    E.mu.mem_write(CALLEE, b'\x4e\x75')
    E.log = []

    def hook(mu, a, s, _):
        sp = mu.reg_read(UC_M68K_REG_A7)
        E.log.append(struct.unpack('>19I', mu.mem_read(sp + 4, 76)))
        mu.reg_write(UC_M68K_REG_D0, 0x1000 + 7 * len(E.log))
        for r in (UC_M68K_REG_D1, UC_M68K_REG_A0, UC_M68K_REG_A1):
            mu.reg_write(r, 0xDEADBEEF)
    E.mu.hook_add(UC_HOOK_CODE, hook, begin=CALLEE, end=CALLEE)
    return E


def run(E, fn, this, a4, regs):
    E.log = []
    d0 = E.call(fn, [this, a4], regs)
    out = [E.mu.reg_read(r) & 0xffffffff for r in SAVED] + [E.mu.reg_read(UC_M68K_REG_A7)]
    return E.log, d0, out


def compare(simg, nimg, trials=200, seed=3):
    S, N = rig(simg), rig(nimg)
    r = random.Random(seed)
    fails = 0
    for which in (PA, PB):
        fs = struct.unpack('>I', simg[which - BASE:which - BASE + 4])[0]
        fn = struct.unpack('>I', nimg[which - BASE:which - BASE + 4])[0]
        for t in range(trials):
            this, a4 = r.getrandbits(32), r.getrandbits(32)
            regs = {k: r.getrandbits(32) for k in SAVED if k not in (UC_M68K_REG_A4, UC_M68K_REG_A5)}
            regs[UC_M68K_REG_A4], regs[UC_M68K_REG_A5] = r.getrandbits(32), r.getrandbits(32)
            a = run(S, fs, this, a4, regs)
            b = run(N, fn, this, a4, regs)
            if a != b:
                fails += 1
    return fails, len(a[0]) if trials else 0


def main():
    simg, nimg = open(sys.argv[1], 'rb').read(), open(sys.argv[2], 'rb').read()
    fails, _ = compare(simg, nimg)
    S = rig(simg)
    na = len(run(S, PA_fn(simg, PA), 1, 2, {})[0])
    nb = len(run(S, PA_fn(simg, PB), 1, 2, {})[0])
    print(f'A: {na} calls, B: {nb} calls per run; 400 runs compared; {fails} failures')
    # mutations of the new image's code/table must be caught
    syms = __import__('json').load(open(sys.argv[2] + '.syms.json'))
    lo, hi = syms['pm_A'], syms['pm_end']
    r = random.Random(11)
    caught = 0
    sites = r.sample(range(lo, hi), 24)
    for a in sites:
        m = bytearray(nimg)
        m[a - BASE] ^= 1 << r.randrange(8)
        try:
            f, _ = compare(simg, bytes(m), trials=6, seed=5)
        except Exception:
            f = 1
        caught += f > 0
    print(f'mutations: {caught}/{len(sites)} caught (a flip in padding or an unused opcode bit can be harmless)')
    sys.exit(1 if fails or caught < len(sites) - 2 else 0)


def PA_fn(img, ptr):
    return struct.unpack('>I', img[ptr - BASE:ptr - BASE + 4])[0]


if __name__ == '__main__':
    main()
