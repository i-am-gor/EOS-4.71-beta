#!/usr/bin/env python3
"""Emulator test for the SLoop transwave patch (cord destination SLpScn 58).

usage: emu_sloop.py BASE.bin PATCHED.bin
1. sl_shift (called directly, Unicorn ColdFire V4e) against a Python model: stock expression when the
   new sum is 0 (bit-identical), frame stepping, scan, clamping, loop-type gate, register preservation.
2. sl_mode through the real LFO init (FUN_00061A50 -> lfo_init): voice+0x1E = 1 only with an SLpScn cord,
   LFO1 init only.
3. Hook sites, destination table entries and names.
"""
import random, struct, sys
from unicorn import Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN
from unicorn.m68k_const import (UC_M68K_REG_A7, UC_M68K_REG_A5, UC_M68K_REG_A3, UC_M68K_REG_D7,
                                UC_M68K_REG_D2, UC_M68K_REG_D3, UC_M68K_REG_D4, UC_M68K_REG_D5,
                                UC_M68K_REG_D6, UC_M68K_REG_A0, UC_M68K_REG_A1, UC_M68K_REG_A2,
                                UC_M68K_REG_A4, UC_M68K_REG_A6, UC_CPU_M68K_CFV4E)

BASE, RET = 0x20000, 0x1000
RAM, STACK = 0x10000000, 0x10080000
VOICE, HDRS, PARAMS = 0x10010000, 0x10020000, 0x10011000
P = VOICE + 0x5A
LFO1 = VOICE + 0x188
DEST_TABLE = 0x6344C
FULL = 4032                       # full scale: CC 127 (127 << 5) through a +100 cord (127 << 5), >> 12
SAVED = (UC_M68K_REG_D2, UC_M68K_REG_D3, UC_M68K_REG_D4, UC_M68K_REG_D5, UC_M68K_REG_D6,
         UC_M68K_REG_A0, UC_M68K_REG_A1, UC_M68K_REG_A2, UC_M68K_REG_A3, UC_M68K_REG_A4, UC_M68K_REG_A6)


def s32(v):
    v &= 0xFFFFFFFF
    return v - (1 << 32) if v & 0x80000000 else v


def tdiv(a, b):                       # ColdFire divs/divu: truncate toward zero
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b > 0) else -q


def model(base, sloop, acc, mode, ltype, s0, s1, ls, le):
    stock = base + (sloop >> 5)
    if acc == 0 or not (1 <= ltype <= 2):
        return stock
    L = (le - ls) >> 1
    if L <= 0:
        return stock
    lo, hi = (s0 - ls) >> 1, ((s1 - le) >> 1) + 1   # sample end inclusive, loop end exclusive
    R = hi if acc >= 0 else -lo
    sh = acc * (R // FULL) + tdiv(acc * (R % FULL), FULL)
    tot = stock + sh
    tot = max(lo, min(hi, tot))
    return max(-32767, min(32767, tot))


class Emu:
    def __init__(self, img):
        self.img = img
        self.mu = mu = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
        mu.ctl_set_cpu_model(UC_CPU_M68K_CFV4E)
        mu.mem_map(0, 0x220000)
        mu.mem_write(BASE, img)
        mu.mem_write(RET, b'\x4e\x71')
        mu.mem_map(RAM, 0x81000)

    def w(self, a, fmt, *v):
        self.mu.mem_write(a, struct.pack('>' + fmt, *v))

    def r(self, a, fmt):
        return struct.unpack('>' + fmt, self.mu.mem_read(a, struct.calcsize('>' + fmt)))

    def call(self, fn, *args, regs=None):
        sp = STACK - 0x200
        self.w(sp, 'I' * (len(args) + 1), RET, *args)
        self.mu.reg_write(UC_M68K_REG_A7, sp)
        for k, v in (regs or {}).items():
            self.mu.reg_write(k, v)
        self.mu.emu_start(fn, RET, count=20000)
        return sp


def main():
    base_img, img = (open(p, 'rb').read() for p in sys.argv[1:3])
    sym = {}
    for line in open('patches/lfosync/lfosync.elf', 'rb').read().split(b'\0'):
        pass
    import subprocess
    for line in subprocess.run(['/opt/homebrew/bin/m68k-elf-nm', 'patches/lfosync/lfosync.elf'],
                               capture_output=True, text=True, check=True).stdout.splitlines():
        a, _, n = line.split()
        sym[n] = int(a, 16)
    E = Emu(img)
    rnd = random.Random(55)
    fails, n = [], 0

    # 1. sl_shift vs model
    for case in range(6000):
        L = rnd.choice([1, 2, 64, 256, 256, 600, 1024, 4096])
        frames = rnd.choice([1, 2, 8, 32, 32, 200, 5000])
        total = L * frames + rnd.choice([0, 0, 17, 300])
        s0 = rnd.randrange(0, 1 << 20) * 2
        k0 = rnd.randrange(0, frames)
        ls = s0 + 2 * k0 * L
        le = ls + 2 * L
        s1 = s0 + 2 * (total - 1)                       # last sample (inclusive), as EOS stores it
        ltype = rnd.choice([0, 1, 1, 2, 2, 3])
        base = rnd.choice([0, 0, 0, 5, -40])
        sloop = rnd.choice([0, 0, 3200, -3200, 12345, -32768 + 7])
        acc = rnd.choice([0, 4032, -4032, 2016, 4064, 130, -1, 32767, -32768, rnd.randrange(-32768, 32768)])
        mode = rnd.randrange(2)
        hdr = HDRS
        E.mu.mem_write(hdr, bytes(0x40))
        E.w(hdr + 0x14, 'I', s0); E.w(hdr + 0x1C, 'I', s1)
        E.w(hdr + 0x24, 'I', ls); E.w(hdr + 0x2C, 'I', le)
        E.w(hdr + 0x3A, 'B', ltype << 6)
        E.w(P + 0x1C, 'h', base); E.w(P + 0x0A, 'h', sloop); E.w(P + 0x30, 'I', hdr)
        E.w(VOICE + 0x1C, 'h', acc); E.w(VOICE + 0x1E, 'h', mode)
        sentinel = {r: 0x11110000 + i for i, r in enumerate(SAVED)}
        sentinel[UC_M68K_REG_A5] = P
        E.call(sym['sl_shift'], regs=sentinel)
        got = s32(E.mu.reg_read(UC_M68K_REG_D7))
        want = model(base, sloop, acc, mode, ltype, s0, s1, ls, le)
        n += 1
        if got != want:
            fails.append(f'sl_shift L{L} frames{frames} k0 {k0} type{ltype} base{base} sloop{sloop} acc{acc} '
                         f'mode{mode}: {got} != {want}')
        for r_, v_ in sentinel.items():
            if r_ != UC_M68K_REG_A5 and E.mu.reg_read(r_) & 0xFFFFFFFF != v_:
                fails.append(f'sl_shift clobbered a saved register (case {case})'); break
        if acc == 0 and got != base + (sloop >> 5):
            fails.append(f'sl_shift: stock mismatch with no new cords (case {case})')

    # padded test table (8194 samples, loop 2..257): Mod Wheel 0..127 through +100 (sum = CC*32*4064 >> 12)
    E.w(HDRS + 0x14, 'I', 0); E.w(HDRS + 0x1C, 'I', 2 * 8193)
    E.w(HDRS + 0x24, 'I', 2 * 2); E.w(HDRS + 0x2C, 'I', 2 * 258); E.w(HDRS + 0x3A, 'B', 1 << 6)
    E.w(P + 0x1C, 'h', 0); E.w(P + 0x0A, 'h', 0); E.w(P + 0x30, 'I', HDRS)
    shifts = []
    for cc in range(128):
        E.w(VOICE + 0x1C, 'h', (cc * 32 * 4064) >> 12)
        for mode in (0, 1):                               # voice+0x1E is the plain sink again: ignored
            E.w(VOICE + 0x1E, 'h', mode)
            E.call(sym['sl_shift'], regs={UC_M68K_REG_A5: P})
            shifts.append(s32(E.mu.reg_read(UC_M68K_REG_D7)))
    sweep = shifts[::2]
    n += 3
    if shifts[::2] != shifts[1::2]:
        fails.append('scan depends on voice+0x1E')
    if sweep[0] != 0 or sweep[-1] != 7936 or any(b_ < a_ for a_, b_ in zip(sweep, sweep[1:])):
        fails.append(f'scan sweep: start {sweep[0]}, end {sweep[-1]}, monotonic {all(b_ >= a_ for a_, b_ in zip(sweep, sweep[1:]))}')
    steps = sorted(set(b_ - a_ for a_, b_ in zip(sweep, sweep[1:])))
    print(f'  Mod Wheel 0..127 -> loop start shift {sweep[0]}..{sweep[-1]} (last frame start 7936), step sizes {steps[0]}..{steps[-1]} samples')

    # 2. LFO init no longer writes voice+0x1E (no mode flag)
    for dst, lfo in ((58, 1), (55, 1), (58, 2)):
        E.mu.mem_write(VOICE, bytes(0x400)); E.mu.mem_write(PARAMS, bytes(0x100))
        E.w(PARAMS, 'BBBBB', 64, 1, 0, 0, 0)
        E.w(0x1000229C, 'I', 1); E.w(0x10000450, 'I', 1000); E.w(0x10000434, 'I', 960)
        E.w(PARAMS + 0x26 + 4 * 7, 'BBBB', 96, dst, 50, 0)
        E.w(VOICE + 0x1E, 'h', 7)
        if lfo == 1:
            E.call(0x61A50, LFO1, PARAMS)
        else:
            E.call(0x61CDC, VOICE + 0x1A8, PARAMS)
        n += 1
        if E.r(VOICE + 0x1E, 'h')[0] != 7:
            fails.append(f'LFO{lfo} init wrote voice+0x1E (dst {dst})')

    # 3. hooks and destinations
    for a in (0x5FBA6, 0x5FECA):
        n += 1
        if img[a - BASE:a - BASE + 16] != b'\x4e\xb9' + struct.pack('>I', sym['sl_shift']) + b'\x4e\x71' * 5:
            fails.append(f'hook {a:#x} not patched')
        if base_img[a - BASE:a - BASE + 16].hex() != '3e2d001c322d000a48c748c1ea81de81':
            fails.append(f'base image at {a:#x} not stock')
    for code, name, off_want in ((58, 'SLpScn', 0x1C), (55, '', 0x1E)):
        p_, off, fl = struct.unpack('>IHH', img[DEST_TABLE + 8 * code - BASE:DEST_TABLE + 8 * code + 8 - BASE])
        nm = img[p_ - BASE:p_ - BASE + 8].split(b'\0')[0].decode('latin1')
        n += 1
        if (nm, off) != (name, off_want) or img[DEST_TABLE + 8 * code - BASE:DEST_TABLE + 8 * code + 8 - BASE] != (
                base_img[DEST_TABLE + 8 * code - BASE:DEST_TABLE + 8 * code + 8 - BASE] if code == 55 else
                img[DEST_TABLE + 8 * code - BASE:DEST_TABLE + 8 * code + 8 - BASE]):
            fails.append(f'destination {code}: {nm!r} {off:#x} {fl:#x}')
    listed = sum(1 for c in range(0xC0)
                 if struct.unpack('>H', img[DEST_TABLE + 8 * c + 4 - BASE:DEST_TABLE + 8 * c + 6 - BASE])[0] != 0x1E)
    listed0 = sum(1 for c in range(0xC0)
                  if struct.unpack('>H', base_img[DEST_TABLE + 8 * c + 4 - BASE:DEST_TABLE + 8 * c + 6 - BASE])[0] != 0x1E)
    print(f'  destinations listed: {listed0} -> {listed}')
    n += 1
    if listed != listed0 + 1:
        fails.append('destination count did not grow by 1')

    print(f'{n} checks; {len(fails)} failures')
    for f in fails[:20]:
        print('  ' + f)
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
