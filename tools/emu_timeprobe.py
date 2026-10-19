#!/usr/bin/env python3
"""Emulator test of the voice-tick timing probe (patches/timeprobe/timeprobe.s).
usage: emu_timeprobe.py STOCK.bin PROBE.bin"""
import struct, sys
from unicorn import UC_HOOK_MEM_READ
from unicorn.m68k_const import UC_M68K_REG_A7, UC_M68K_REG_D0
import emu_cost as ec
import build_timeprobe as bt

B, VARS, TCN1, TRR1 = 0x20000, 0x10000300, 0x2000010C, 0x20000104


def main():
    stock, probe = (open(p, 'rb').read() for p in sys.argv[1:3])
    S, P = ec.Emu(stock), ec.Emu(probe)
    fails, n = [], 0
    # 1. sites point to the right stubs, stubs to the right functions
    for a, (k, kind, tgt) in bt.SITES.items():
        o = a - B
        dest = a + 2 + struct.unpack('>h', probe[o + 2:o + 4])[0] if kind == 'bsr' else struct.unpack('>I', probe[o + 2:o + 6])[0]
        so = dest - B
        fn = struct.unpack('>I', probe[so + 2:so + 6])[0]
        n += 1
        if probe[so:so + 2] != b'\x43\xf9' or fn != tgt or probe[so + 6] != 0x72 or probe[so + 7] != 8 * k:
            fails.append(f'site {a:#x}: stub {dest:#x} -> {fn:#x} k {probe[so + 7] // 8}, expected {tgt:#x} k {k}')
    # 2. stage through its stub == direct stock call (result, memory, stack); timer arithmetic
    seq = {'v': []}

    def tcn(mu, access, addr, size, value, ud):
        if seq['v']:
            mu.mem_write(TCN1, struct.pack('>H', seq['v'].pop(0)))
    P.mu.hook_add(UC_HOOK_MEM_READ, tcn, begin=TCN1, end=TCN1 + 1)
    P.w(TRR1, 'H', 1999)
    stubs = {k: a + 2 + struct.unpack('>h', probe[a - B + 2:a - B + 4])[0] if kind == 'bsr' else
             struct.unpack('>I', probe[a - B + 2:a - B + 6])[0] for a, (k, kind, _) in bt.SITES.items()}
    V = 0x10100000
    cases = [(7, 0x62798, (V,)), (1, 0x5F89C, (V,)), (6, 0x62544, (V, 1)), (2, 0x62208, (V, 1))]
    for k, fn, args in cases:
        for trial, (t0, t1, want) in enumerate(((100, 107, 7), (1995, 3, 8))):
            init = bytearray(0x400)
            if k == 7:                                        # key/vel window: value inside the fade range
                struct.pack_into('>8h', init, 0, 0x700 + 64 * trial, 0, 0x400, 0xC00, 0x800, 0xA00, 1, 1)
            if k == 6:
                struct.pack_into('>8h', init, 0, 5, -300, 77, 12, 0x345, 9, 0, 0)
            for E in (S, P):
                E.mu.mem_write(V, bytes(init))
                if k == 1:                                    # cord slots: enabled flags off, safe pointers
                    for c in range(24):
                        e = V + 0x208 + 16 * c
                        E.w(e, 'II', V + 0x380, V + 0x3C0); E.mu.mem_write(e + 12, b'\x00')
                if k == 2:
                    E.mu.mem_write(V + 0x22, b'\x00')           # envelope: no segment stepping
            P.w(VARS, '24I', *([0] * 24))
            seq['v'] = [t0, t1]
            S.call(fn, *args); d_s = S.mu.reg_read(UC_M68K_REG_D0)
            sp0 = 0x10080000 - 0x400
            P.call(stubs[k], *args); d_p = P.mu.reg_read(UC_M68K_REG_D0)
            n += 1
            if bytes(S.mu.mem_read(V, 0x400)) != bytes(P.mu.mem_read(V, 0x400)):
                fails.append(f'stage {k} {fn:#x}: memory differs from the direct call')
            if (d_s & 0xFFFF) != (d_p & 0xFFFF) and k not in (1, 7):   # void stages: callers never read d0
                fails.append(f'stage {k}: d0 {d_p:#x} != {d_s:#x}')
            if P.mu.reg_read(UC_M68K_REG_A7) != sp0 + 4:
                fails.append(f'stage {k}: stack not balanced ({P.mu.reg_read(UC_M68K_REG_A7):#x})')
            acc, cnt = struct.unpack('>II', P.mu.mem_read(VARS + 8 * k, 8))
            if (acc, cnt) != (want, 1):
                fails.append(f'stage {k} trial {trial}: acc {acc} cnt {cnt}, expected {want} 1')
    # 3. readout
    get, put = struct.unpack('>II', probe[0x25AF4 + 0x1A - B:0x25AF4 + 0x22 - B])
    P.w(VARS, '24I', *range(1000, 1024))
    for v, want in ((0, 1000), (5, 1005), (23, 1023), (24, 1999)):
        P.call(put, 0x25AF4, v)
        got = 0
        for i in range(3):
            P.call(get, 0x25AF4); got |= (P.mu.reg_read(UC_M68K_REG_D0) & 0x7FF) << (11 * i)
        n += 1
        if got != want:
            fails.append(f'readout {v}: {got} != {want}')
    print(f'{n} checks; {len(fails)} failures')
    for f in fails:
        print('  ' + f)
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
