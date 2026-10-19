#!/usr/bin/env python3
"""Emulator test of the CPU-load probe (patches/probe/probe.s) in a built image.
usage: emu_probe.py PROBE.bin"""
import struct, sys
from unicorn.m68k_const import UC_M68K_REG_A4, UC_M68K_REG_A5, UC_M68K_REG_A7, UC_M68K_REG_D0, UC_M68K_REG_D6
import emu_cost as ec

VARS, NOWMS = 0x10000200, 0x10000450


def main():
    img = open(sys.argv[1], 'rb').read()
    E = ec.Emu(img)
    B = 0x20000
    jsr = lambda a: struct.unpack('>I', img[a - B + 2:a - B + 6])[0]
    fails, n = [], 0
    get, put = struct.unpack('>II', img[0x25AF4 + 0x1A - B:0x25AF4 + 0x22 - B])
    tick, loop = jsr(0x60E90), jsr(0x321DE)
    # readout: set(v) latches var v, three gets return 11-bit pieces
    vals = [0x12345678, 0x0BADF00D, 37, 0x7FFFFFFF]
    E.w(VARS, 'IIII', *vals)
    for v, want in enumerate(vals):
        E.call(put, 0x25AF4, v)
        got = 0
        for k in range(3):
            E.call(get, 0x25AF4)
            got |= (E.mu.reg_read(UC_M68K_REG_D0) & 0x7FF) << (11 * k)
        n += 1
        if got != want & 0x1FFFFFFFF:
            fails.append(f'readout var {v}: {got:#x} != {want:#x}')
    E.call(put, 0x25AF4, 15)
    n += 1
    if struct.unpack('>IIII', E.mu.mem_read(VARS, 16)) != (vals[0], vals[1], 0, vals[3]):
        fails.append(f'set(15) did not clear only LATEMAX: {struct.unpack(">IIII", E.mu.mem_read(VARS, 16))}')
    # voice tick hook: d6 = NOWMS (as stock), TICKS+1, lateness = now - deadline
    E.w(VARS, 'IIII', 0, 0, 0, 0)
    V = 0x10100000
    for now, dl in ((5000, 5000), (5010, 5007), (5020, 5019), (5030, 5030)):
        E.w(NOWMS, 'I', now); E.w(V + 0x1E, 'I', dl)
        E.mu.reg_write(UC_M68K_REG_A4, V)
        E.call(tick)
        n += 1
        if E.mu.reg_read(UC_M68K_REG_D6) != now:
            fails.append(f'tick hook: d6 {E.mu.reg_read(UC_M68K_REG_D6)} != {now}')
    n += 1
    if struct.unpack('>IIII', E.mu.mem_read(VARS, 16)) != (0, 4, 3, 4):
        fails.append(f'tick counters {struct.unpack(">IIII", E.mu.mem_read(VARS, 16))} != (0, 4, 3, 4)')
    # main loop hook: pushes a5+0x184 like the replaced lea/move, counts a pass, returns to the caller
    E.mu.reg_write(UC_M68K_REG_A5, 0x1029E470)
    sp = 0x10080000 - 0x400
    E.w(sp, 'I', ec.RET); E.mu.reg_write(UC_M68K_REG_A7, sp)
    E.mu.emu_start(loop, ec.RET, count=100)
    n += 1
    top = struct.unpack('>I', E.mu.mem_read(E.mu.reg_read(UC_M68K_REG_A7), 4))[0]
    if top != 0x1029E470 + 0x184 or E.mu.reg_read(UC_M68K_REG_A7) != sp or struct.unpack('>I', E.mu.mem_read(VARS, 4))[0] != 1:
        fails.append(f'loop hook: stack top {top:#x}, sp {E.mu.reg_read(UC_M68K_REG_A7):#x}')
    print(f'{n} checks; {len(fails)} failures')
    for f in fails:
        print('  ' + f)
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
