#!/usr/bin/env python3
"""Differential test: stock vs OB-Xa lowpass methods, run in Unicorn (ColdFire V4e core).

usage: emu_obxa.py STOCK.bin PATCHED.bin
Methods are reached through each image's own vtables (so the vtable repointing is tested).
FUN_0010D3B0 (writes chip registers) is replaced by a hook that records its arguments and returns.
Checks for every filter (2/4/6), q = 0..255 (computeFrames) and 0..127 (packQ):
  same return value, same gain word 9, same words 1/5, same SETMODE args, same untouched words;
  pole words 0/4/8 equal tools/obxa.py's expected blocks.
"""
import os, struct, sys
from unicorn import Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE
from unicorn.m68k_const import UC_M68K_REG_A7, UC_M68K_REG_D0, UC_M68K_REG_D1, UC_M68K_REG_A0, UC_M68K_REG_A1, UC_CPU_M68K_CFV4E

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import obxa  # noqa: E402

BASE, RET, SETMODE = 0x20000, 0x1000, 0x10D3B0
RAM, STACK, BLK, GAINBASE = 0x10000000, 0x10080000, 0x10008000, 0x10004D7C
STRUCT, LBUF, VBUF = 0x10009000, 0x1000A000, 0x1000A100
VT = {2: 0x68878, 4: 0x688A4, 6: 0x688D0}
FILL = 0xA5A5A5A5


class Emu:
    def __init__(self, img):
        self.img = img
        self.mu = mu = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
        mu.ctl_set_cpu_model(UC_CPU_M68K_CFV4E)
        mu.mem_map(0, 0x220000)
        mu.mem_write(BASE, img)
        mu.mem_write(RET, b'\x4e\x71')
        mu.mem_write(SETMODE, b'\x4e\x75')          # rts; arguments captured by hook
        mu.mem_map(RAM, 0x80000 + 0x1000)
        mu.mem_write(GAINBASE, struct.pack('>I', 0x00400000))
        self.calls = []
        mu.hook_add(UC_HOOK_CODE, self._hook, begin=SETMODE, end=SETMODE)

    def _hook(self, mu, addr, size, _):
        sp = mu.reg_read(UC_M68K_REG_A7)
        self.calls.append(struct.unpack('>III', mu.mem_read(sp + 4, 12)))
        # SETMODE is C code: d0/d1/a0/a1 are scratch. Trash them like a real call would.
        for r, v in ((UC_M68K_REG_D0, 0xDEAD0000), (UC_M68K_REG_D1, 0x7FFF1234), (UC_M68K_REG_A0, 0x0BADBAD0), (UC_M68K_REG_A1, 0x0BADBAD4)):
            mu.reg_write(r, v)

    def slot(self, P, off):
        o = VT[P] + off - BASE
        return struct.unpack('>I', self.img[o:o + 4])[0]

    def set_drive(self, d):
        self.mu.mem_write(STRUCT, bytes([0, 0, 0, 0, 0, 0, d & 0xff, 0]) + bytes(8))

    def cstr(self, a):
        b = bytes(self.mu.mem_read(a, 64))
        return b.split(b'\0')[0].decode('latin1')

    def call(self, fn, args, blk_init=FILL):
        mu = self.mu
        mu.mem_write(BLK, struct.pack('>I', blk_init) * 16)
        sp = STACK - 0x200
        mu.mem_write(sp, struct.pack('>' + 'I' * (len(args) + 1), RET, *args))
        mu.reg_write(UC_M68K_REG_A7, sp)
        self.calls = []
        mu.emu_start(fn, RET, count=10000)
        ret = mu.reg_read(UC_M68K_REG_D0) & 0xffffffff
        blk = struct.unpack('>16I', mu.mem_read(BLK, 64))
        return ret, blk, list(self.calls)


def main():
    stock, new = (Emu(open(p, 'rb').read()) for p in sys.argv[1:3])
    fails, n = [], 0
    for P in (2, 4, 6):
        for off in (0x0C, 0x10):                     # type, getName
            a = stock.call(stock.slot(P, off), [0])[0]
            b = new.call(new.slot(P, off), [0])[0]
            n += 1
            if a != b:
                fails.append(f'LP{P} slot {off:#x}: {a:#x} != {b:#x}')
        stock.set_drive(0); new.set_drive(0)
        for q in range(256):                         # computeFrames(this, blk, mode, q, struct)
            args = [0, BLK, 3, q, STRUCT]
            ra, ba, ca = stock.call(stock.slot(P, 0x14), args)
            rb, bb, cb = new.call(new.slot(P, 0x14), args)
            exp = obxa.blocks(q & 127 if q < 128 else q)[P] if q < 128 else None
            n += 1
            if ra != rb or ca != cb or (ba[1], ba[5], ba[9]) != (bb[1], bb[5], bb[9]) or ba[10:] != bb[10:] \
                    or (ba[2], ba[3], ba[6], ba[7]) != (bb[2], bb[3], bb[6], bb[7]):
                fails.append(f'LP{P} cf q={q}: stock ret {ra:#x} {ca} vs new {rb:#x} {cb}')
            if exp is not None and (bb[0], bb[4], bb[8]) != (exp[0], exp[4], exp[8]):
                fails.append(f'LP{P} cf q={q}: poles {bb[0]:08X} {bb[4]:08X} {bb[8]:08X} != model')
        for q in range(128):                         # packQ(this, blk, q, struct)
            args = [0, BLK, q, STRUCT]
            ra, ba, _ = stock.call(stock.slot(P, 0x18), args)
            rb, bb, _ = new.call(new.slot(P, 0x18), args)
            exp = obxa.blocks(q)[P]
            touched = {2: (0,), 4: (0, 4), 6: (0, 4, 8)}[P]
            n += 1
            if ra != rb:
                fails.append(f'LP{P} pq q={q}: ret {ra:#x} != {rb:#x}')
            for w in range(16):
                if w in touched:
                    if bb[w] != exp[w]:
                        fails.append(f'LP{P} pq q={q}: w{w} {bb[w]:08X} != model {exp[w]:08X}')
                elif ba[w] != bb[w]:
                    fails.append(f'LP{P} pq q={q}: untouched w{w} differs')
        # v3c: Drive (struct+6) adds drive<<14 to the gain word, clamped at 127; nothing else changes
        if new.slot(P, 0x20) != stock.slot(P, 0x20):
            for d, eff in ((64, 64), (127, 127), (200, 127)):
                for q in (0, 64, 127):
                    stock.set_drive(0); new.set_drive(d)
                    ra, ba, ca = stock.call(stock.slot(P, 0x14), [0, BLK, 3, q, STRUCT])
                    rb, bb, cb = new.call(new.slot(P, 0x14), [0, BLK, 3, q, STRUCT])
                    n += 1
                    if (bb[9] - ba[9]) & 0xffffffff != eff << 14 or ra != rb or ca != cb or ba[1] != bb[1]:
                        fails.append(f'LP{P} drive {d} q{q}: gain word {ba[9]:#x}->{bb[9]:#x}, ret {ra:#x}/{rb:#x}')
            new.set_drive(0)
            n += 1
            if new.call(new.slot(P, 0x20), [0])[0] != 3:
                fails.append(f'LP{P} numParams != 3')
            for idx, val in ((0, 128), (1, 64), (2, 77)):
                outs = []
                for E in (stock, new):
                    E.mu.mem_write(LBUF, bytes(64)); E.mu.mem_write(VBUF, bytes(64))
                    E.call(E.slot(P, 0x1C), [0, idx, val, LBUF, VBUF])
                    outs.append((E.cstr(LBUF), E.cstr(VBUF)))
                n += 1
                want = outs[0] if idx < 2 else ('Drive', str(val))
                if outs[1] != want:
                    fails.append(f'LP{P} formatParam idx {idx}: {outs[1]} != {want}')
                elif P == 4:
                    print(f'  formatParam idx {idx}: stock {outs[0]}  v3c {outs[1]}')
    print(f'{n} method calls compared; {len(fails)} failures')
    for f in fails[:20]:
        print('  ' + f)
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
