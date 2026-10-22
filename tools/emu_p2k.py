#!/usr/bin/env python3
"""Emulator test for the P2K cascade test build (patches/p2k/p2k.s).

usage: emu_p2k.py BASE.bin PATCHED.bin
1. Registry ctor (malloc stubbed with a bump allocator): manager memory, objects and
   return value identical to the stock ctor; null manager returns 0.
2. Switch 0: Bat-Phaser computeFrames (Q 0..127, n 0..4) and packQ through the patched vtable equal stock
   (block words, SETMODE calls, return).
3. Switch 1..7: block words, partner words, mode bytes, SETMODE calls, OWN/PART and return value equal a
   Python model built from patches/p2k/tables.inc; packQ rewrites the stage words without SETMODE.
4. Parameter 195 getter/setter; cutoff hook at 0x60040 (writes, register and flag preservation).
5. Image diff: only the ctor region, two vtable slots, the descriptor 195 getter/setter, the 8 hook bytes and
   the header changed.
"""
import os, re, struct, sys
from unicorn import Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE
from unicorn.m68k_const import *

BASE = 0x20000
RET = 0x1000
RAM, STACK = 0x10000000, 0x10080000
CHIP = 0x08000000
SETMODE, MALLOC = 0x10D3B0, 0x2AFDC
SW, OWN, PART = 0x100003E4, 0x100003E8, 0x100003EC
VT_BP, DESC195 = 0x68AB4, 0x25AF4
N = 0xFFCFFFCF
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Emu:
    def __init__(self, img):
        self.img = img
        mu = self.mu = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
        mu.ctl_set_cpu_model(UC_CPU_M68K_CFV4E) if hasattr(mu, 'ctl_set_cpu_model') else None
        mu.mem_map(0, 0x220000)
        mu.mem_write(BASE, img)
        mu.mem_write(RET, b'\x4e\x71')
        mu.mem_map(RAM, 0x81000)
        mu.mem_map(CHIP, 0x2000)
        mu.mem_write(SETMODE, b'\x4e\x75')
        mu.mem_write(MALLOC, b'\x4e\x75')
        self.calls, self.heap, self.fail_at, self.nalloc = [], 0x10040000, set(), 0
        mu.hook_add(UC_HOOK_CODE, self._setmode, begin=SETMODE, end=SETMODE)
        mu.hook_add(UC_HOOK_CODE, self._malloc, begin=MALLOC, end=MALLOC)

    def _args(self, n):
        sp = self.mu.reg_read(UC_M68K_REG_A7)
        return struct.unpack(f'>{n}I', self.mu.mem_read(sp + 4, 4 * n))

    def _setmode(self, mu, addr, size, _):
        blk, n, fl = self._args(3)
        self.calls.append((blk, n & 0xff, fl & 0xff, bytes(mu.mem_read(blk + 0x3B, 1))[0]))
        for r in (UC_M68K_REG_D0, UC_M68K_REG_D1, UC_M68K_REG_A0, UC_M68K_REG_A1):
            mu.reg_write(r, 0xDEADBEEF)

    def _malloc(self, mu, addr, size, _):
        self.nalloc += 1
        if self.nalloc in self.fail_at:
            mu.reg_write(UC_M68K_REG_D0, 0)
        else:
            sz = self._args(1)[0]
            mu.reg_write(UC_M68K_REG_D0, self.heap)
            self.heap += (sz + 7) & ~7
        for r in (UC_M68K_REG_D1, UC_M68K_REG_A0, UC_M68K_REG_A1):
            mu.reg_write(r, 0xDEADBEEF)

    def call(self, fn, args, regs=None):
        mu = self.mu
        sp = STACK - 0x400
        mu.mem_write(sp, struct.pack('>' + 'I' * (len(args) + 1), RET, *args))
        mu.reg_write(UC_M68K_REG_A7, sp)
        for r, v in (regs or {}).items():
            mu.reg_write(r, v)
        self.calls = []
        mu.emu_start(fn, RET, count=200000)
        return mu.reg_read(UC_M68K_REG_D0) & 0xffffffff

    def rd(self, a, n):
        return bytes(self.mu.mem_read(a, n))

    def w32(self, a, v):
        self.mu.mem_write(a, struct.pack('>I', v & 0xffffffff))

    def r32(self, a):
        return struct.unpack('>I', self.rd(a, 4))[0]

    def slot(self, vt, off):
        return struct.unpack('>I', self.img[vt + off - BASE:vt + off + 4 - BASE])[0]


def load_table():
    txt = open(os.path.join(ROOT, 'patches', 'p2k', 'tables.inc')).read()
    longs = [int(x, 16) for x in re.findall(r'0x([0-9A-F]{8})', txt)]
    bytes_ = [list(map(lambda t: int(t, 0), l.split(','))) for l in re.findall(r'\.byte\s+(.*)', txt)]
    recs = []
    for k in range(8):
        w = longs[7 * k:7 * k + 7]
        ret = bytes_[k][0] - 256 if bytes_[k][0] > 127 else bytes_[k][0]
        recs.append((w[:6], w[6], ret, bytes_[k][1]))
    return recs


def prevblk(b):
    return b + 0x780 if (b & 0xFFF) == 0 else b - 0x80


def nextblk(b):
    return b - 0x780 if (b & 0x7FF) == 0x780 else b + 0x80


def fill_chip(E, seed):
    E.mu.mem_write(CHIP, bytes((seed * 7 + i * 13) & 0xff for i in range(0x2000)))


def main():
    stock_img, new_img = (open(p, 'rb').read() for p in sys.argv[1:3])
    S, P = Emu(stock_img), Emu(new_img)
    fails, n = [], 0
    T = load_table()

    # 1. registry ctor
    MGR = 0x10030000
    for fail_at in (set(),):            # a failed allocation crashes stock and patched alike (null object in the type loop)
        outs = []
        for E in (S, P):
            E.mu.mem_write(MGR, bytes([0xA5]) * 0x25C)
            E.heap, E.fail_at, E.nalloc = 0x10040000, fail_at, 0
            E.mu.mem_write(0x10040000, bytes(0x400))
            r = E.call(0x67F98, [MGR])
            outs.append((r, E.rd(MGR, 0x25C), E.rd(0x10040000, 0x100), E.nalloc))
        n += 1
        if outs[0] != outs[1]:
            fails.append(f'ctor fail_at {sorted(fail_at)}: differs (count {outs[0][1][0x258:0x25C].hex()} / '
                         f'{outs[1][1][0x258:0x25C].hex()}, allocs {outs[0][3]}/{outs[1][3]})')
    for E in (S, P):
        E.fail_at = set()
    n += 1
    if P.call(0x67F98, [0]) != 0 or S.call(0x67F98, [0]) != 0:
        fails.append('ctor null manager')

    # 2. switch 0: stock path
    blk = CHIP + 0x300
    for E in (S, P):
        E.w32(SW, 0)
    for q in range(128):
        for nn in (0, 3, 4):
            outs = []
            for E, img in ((S, stock_img), (P, new_img)):
                fill_chip(E, q)
                r = E.call(E.slot(VT_BP, 0x14), [0, blk, nn, q, 0])
                outs.append((r, E.rd(CHIP, 0x2000), tuple(E.calls)))
            n += 1
            if outs[0] != outs[1]:
                fails.append(f'switch 0 cf q{q} n{nn}: differs from stock')
        outs = []
        for E in (S, P):
            fill_chip(E, q + 1)
            r = E.call(E.slot(VT_BP, 0x18), [0, blk, q, 0])
            outs.append((r, E.rd(CHIP, 0x2000), tuple(E.calls)))
        n += 1
        if outs[0] != outs[1]:
            fails.append(f'switch 0 pq q{q}: differs from stock')

    # 3. switch 1..7
    for mode in range(1, 8):
        P.w32(SW, mode)
        for b in (CHIP + 0x300, CHIP + 0x780, CHIP + 0x800, CHIP + 0x000, CHIP + 0xF80):
            for q in range(0, 128, 3):
                for nn in (0, 2):
                    for is_pq in (False, True):
                        fill_chip(P, q + mode)
                        P.w32(OWN, 0x11111111); P.w32(PART, 0x22222222)
                        before = bytearray(P.rd(CHIP, 0x2000))
                        if is_pq:
                            r = P.call(P.slot(VT_BP, 0x18), [0, b, q, 0])
                        else:
                            r = P.call(P.slot(VT_BP, 0x14), [0, b, nn, q, 0])
                        poles, gain, ret, fl = T[q >> 4]
                        exp = bytearray(before)
                        calls = []

                        def put(blk_, pw, g=None):
                            o = blk_ - CHIP
                            for i, w in zip((0, 4, 8), pw):
                                exp[o + 4 * i:o + 4 * i + 4] = struct.pack('>I', w)
                            for i in (1, 5, 9):
                                exp[o + 4 * i:o + 4 * i + 4] = struct.pack('>I', N)
                            if g is not None:
                                exp[o + 36:o + 40] = struct.pack('>I', g)
                        own, part = b, None
                        if mode in (1, 7, 6):
                            put(b, poles[3:], gain)
                            if not is_pq:
                                calls.append((b, nn, fl, exp[b - CHIP + 0x3B]))
                                if mode == 6:
                                    exp[b - CHIP + 0x7B] = (exp[b - CHIP + 0x3B] & 0x80) | 0x3F
                        elif mode == 2:
                            put(b, poles[:3], gain)
                            if not is_pq:
                                calls.append((b, nn, 0x40, exp[b - CHIP + 0x3B]))
                        else:
                            A, B_ = (prevblk(b), b) if mode == 4 else (b, nextblk(b))
                            part = A if mode == 4 else B_
                            po = part - CHIP
                            for off in (0x08, 0x0C, 0x18, 0x1C, 0x28, 0x2C):
                                exp[po + off:po + off + 4] = bytes(4)
                            put(A, poles[:3])
                            put(B_, poles[3:], gain)
                            if mode == 5:
                                for k in range(0x40, 0x80):
                                    if k != 0x7B:
                                        exp[B_ - CHIP + k] = exp[b - CHIP + k]
                            exp[po + 0x7C] = exp[b - CHIP + 0x7C]
                            if not is_pq:
                                calls.append((A, nn, fl & 0x80, exp[A - CHIP + 0x3B]))
                                exp[A - CHIP + 0x7B] = (exp[A - CHIP + 0x3B] & 0x80) | 0x3F
                                calls.append((B_, nn, fl, exp[B_ - CHIP + 0x3B]))
                        got = P.rd(CHIP, 0x2000)
                        n += 1
                        tag = f'mode {mode} blk {b - CHIP:#x} q{q} n{nn} {"pq" if is_pq else "cf"}'
                        if got != bytes(exp):
                            d = next(i for i in range(0x2000) if got[i] != exp[i])
                            fails.append(f'{tag}: chip byte {d:#x} {got[d]:02x} != {exp[d]:02x}')
                        if (r if r < 0x80000000 else r - (1 << 32)) != ret:
                            fails.append(f'{tag}: return {r:#x} != {ret}')
                        if tuple(P.calls) != tuple(calls):
                            fails.append(f'{tag}: SETMODE {P.calls} != {calls}')
                        if part is not None and (P.r32(OWN), P.r32(PART)) != (own, part):
                            fails.append(f'{tag}: OWN/PART {P.r32(OWN):#x}/{P.r32(PART):#x}')
                        if part is None and (P.r32(OWN), P.r32(PART)) != (0x11111111, 0x22222222):
                            fails.append(f'{tag}: OWN/PART written')

    # 4. parameter 195
    get, put_ = struct.unpack('>II', new_img[DESC195 + 0x1A - BASE:DESC195 + 0x22 - BASE])
    for v, want in ((-1, 0), (0, 0), (1, 1), (5, 5), (7, 7), (9, 1)):
        P.call(put_, [DESC195, v & 0xffffffff])
        n += 1
        if P.r32(SW) != want or P.call(get, [DESC195]) != want:
            fails.append(f'param 195 set {v}: SW {P.r32(SW)} != {want}')
    # cutoff hook: run the patched 0x60040 jsr directly
    hook = struct.unpack('>I', new_img[0x60042 - BASE:0x60046 - BASE])[0]
    n += 1
    if new_img[0x60040 - BASE:0x60042 - BASE] != b'\x4e\xb9' or new_img[0x60046 - BASE:0x60048 - BASE] != b'\x4e\x71':
        fails.append('0x60040 not jsr hook + nop')
    VOICE = 0x10020000
    for mode in range(0, 8):
        for match in (True, False):
            for t14 in (0, 5):
                P.w32(SW, mode)
                b = CHIP + 0x300
                P.w32(OWN, b if match else b + 0x80); P.w32(PART, CHIP + 0x380)
                fill_chip(P, mode)
                P.w32(VOICE + 0x26 + 0x14, t14)
                before = bytearray(P.rd(CHIP, 0x2000))
                regs = {UC_M68K_REG_D6: 0x1234569A, UC_M68K_REG_A2: b, UC_M68K_REG_A4: VOICE + 0x26,
                        UC_M68K_REG_D0: 0xC0FFEE01, UC_M68K_REG_A0: 0xA0A0A0A0, UC_M68K_REG_D1: 0xD1D1D1D1}
                # return through 'seq d7' so the flags from the hook are evaluated by the CPU
                P.mu.mem_write(0x1100, b'\x57\xc7\x4e\x71')
                sp = STACK - 0x400
                P.mu.mem_write(sp, struct.pack('>I', 0x1100))
                P.mu.reg_write(UC_M68K_REG_A7, sp)
                regs[UC_M68K_REG_D7] = 0x77777700
                for r, v in regs.items():
                    P.mu.reg_write(r, v)
                P.mu.emu_start(hook, 0x1102, count=10000)
                exp = before
                exp[0x300 + 0x7C] = 0x9A
                if 3 <= mode <= 5 and match:
                    exp[0x380 + 0x7C] = 0x9A
                n += 1
                tag = f'hook mode {mode} match {match} t14 {t14}'
                if P.rd(CHIP, 0x2000) != bytes(exp):
                    fails.append(f'{tag}: chip writes')
                for r, v in regs.items():
                    if r != UC_M68K_REG_D7 and P.mu.reg_read(r) & 0xffffffff != v:
                        fails.append(f'{tag}: register {r} changed')
                z = P.mu.reg_read(UC_M68K_REG_D7) & 0xff == 0xff
                if z != (t14 == 0):
                    fails.append(f'{tag}: Z flag {z}')

    # cutoff routine FUN_0005FFD8 end to end (cutoff change only; Q unchanged so FUN_00194E80 is not called)
    for sw in (0, 3):
        for stereo in (0, 1):
            for cut in (0, 37, 128, 255, 300, -5):
                outs = []
                for E in (S, P):
                    E.w32(SW, sw); E.w32(OWN, CHIP + 0x300); E.w32(PART, CHIP + 0x380)
                    fill_chip(E, cut & 0xff)
                    V, PS = 0x10021000, 0x10022000
                    E.mu.mem_write(V, bytes(0x100)); E.mu.mem_write(PS, bytes(0x20))
                    E.w32(V + 0x2A, CHIP + 0x300); E.w32(V + 0x32, CHIP + 0x500); E.w32(V + 0x3A, stereo)
                    E.mu.mem_write(PS, struct.pack('>HHHH', (cut * 16) & 0xffff, 0, 0, 0))
                    E.mu.mem_write(PS + 9, b'\x00')
                    E.mu.mem_write(PS + 12, struct.pack('>h', -1))
                    E.call(0x5FFD8, [PS, V])
                    outs.append((E.rd(CHIP, 0x2000), E.rd(PS, 0x20)))
                n += 1
                sb, pb = outs[0][0], outs[1][0]
                diff = [i for i in range(0x2000) if sb[i] != pb[i]]
                want = [0x3FC] if sw == 3 else []
                if diff != want or outs[0][1] != outs[1][1]:
                    fails.append(f'FUN_0005FFD8 sw {sw} stereo {stereo} cut {cut}: diff {[hex(d) for d in diff]}')
                elif sw == 3 and pb[0x3FC] != pb[0x37C]:
                    fails.append(f'FUN_0005FFD8 sw 3 cut {cut}: partner {pb[0x3FC]:#x} != own {pb[0x37C]:#x}')

    # 5. image diff
    allowed = [(0x18, 0x30), (4, 12), (0x67F98, 0x683F0), (VT_BP + 0x14, VT_BP + 0x1C),
               (DESC195 + 0x1A, DESC195 + 0x22), (0x60040, 0x60048)]
    bad = [i + BASE for i in range(len(stock_img)) if stock_img[i] != new_img[i]
           and not any(lo <= i + BASE < hi or lo <= i < hi for lo, hi in allowed)]
    n += 1
    if bad:
        fails.append(f'unexpected changes at {[hex(a) for a in bad[:8]]} ({len(bad)} bytes)')

    print(f'{n} checks; {len(fails)} failures')
    for f in fails[:25]:
        print('  ' + f)
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
