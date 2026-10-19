#!/usr/bin/env python3
"""Run FUN_00065E18 (LP resonance -> stage word) in Unicorn's ColdFire core for q = 0..127.

usage: emu_fun65e18.py STOCK.bin PATCHED.bin
Checks: stock emulation == decompiled stock formula; prints patched words vs the exact CEM model.
"""
import struct, sys, os
from unicorn import Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN
from unicorn.m68k_const import UC_M68K_REG_A7, UC_M68K_REG_D0, UC_M68K_REG_PC, UC_CPU_M68K_CFV4E

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cem3320  # noqa: E402

BASE, FUNC, RET = 0x20000, 0x65E18, 0x00001000
STACK = 0x10800000


def run(img, q):
    mu = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
    mu.ctl_set_cpu_model(UC_CPU_M68K_CFV4E)
    mu.mem_map(0, 0x200000 + 0x20000)
    mu.mem_write(BASE, img)
    mu.mem_write(RET, b'\x4e\x71')                     # nop at return address
    mu.mem_map(STACK - 0x10000, 0x10000)
    sp = STACK - 0x100
    mu.mem_write(sp, struct.pack('>II', RET, q))       # return addr, arg (long, byte at +7)
    mu.reg_write(UC_M68K_REG_A7, sp)
    mu.emu_start(FUNC, RET)
    return mu.reg_read(UC_M68K_REG_D0) & 0xffffffff


def stock_formula(p):
    u = min(0x7f, ((p * 0x11) >> 4) & 0xff)
    return ((((u >> 2) + 0xcf) | ((((u * -0x2b) >> 7) * 0x100 + 0xff00)) |
             ((((u * -3) >> 7) * 0x10000 + 0x80000)) | ((((u * -0x32) >> 7) * 0x1000000 + 0x84000000)))
            & 0xffffffff)


def fields(w):
    return [(w >> s) & 0xff for s in (24, 16, 8, 0)]


def main():
    stock, patched = (open(p, 'rb').read() for p in sys.argv[1:3])
    bad = [q for q in range(128) if run(stock, q) != stock_formula(q)]
    print('stock emulation vs decompiled formula:', 'OK (128/128)' if not bad else f'MISMATCH at {bad[:8]}')
    worst = [0, 0, 0, 0]
    for q in range(128):
        got = fields(run(patched, q))
        ideal = [v for v in cem3320.stage_word(q)[1]]
        for k in range(4):
            worst[k] = max(worst[k], abs(got[k] - ideal[k]))
        if q % 16 == 0 or q == 127:
            print(f'q={q:3d}  patched {run(patched, q):08X}  exact-model X/F lo {ideal[0]:6.1f}/{ideal[1]:6.1f}'
                  f'  hi {ideal[2]:6.1f}/{ideal[3]:6.1f}')
    print('max |patched - exact model| per field (X_lo, F_lo, X_hi, F_hi):', [round(w, 1) for w in worst])
    import patch_cem3320 as pc
    bad = [q for q in range(128) if run(patched, q) != pc.formula(q)]
    print('patched emulation vs patch_cem3320.formula:', 'OK (128/128)' if not bad else f'MISMATCH at {bad[:8]}')
    tab = [struct.unpack('>I', patched[pc.RES16_ADDR - BASE + 4 * j:][:4])[0] for j in range(16)]
    same = all(tab[j] == run(patched, 8 * j + 4) for j in range(16))
    print('RES16 table == realtime routine at each step:', 'OK' if same else 'MISMATCH')


if __name__ == '__main__':
    main()
