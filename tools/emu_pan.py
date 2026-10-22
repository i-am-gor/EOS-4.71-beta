#!/usr/bin/env python3
"""Emulator test of the centre-pan fix (build_beta2.py PAN_FIX) against stock EOS 4.70.

usage: emu_pan.py STOCK.bin BETA2.bin
Runs the real chip pan writer FUN_00060784(chan, level, pan, 0, 0) in both images for every pan -64..+63 and
levels 0..255; it writes the two side gains to chan+113 / chan+115. Required: pan 0 and -1 balanced (equal gains)
in BETA2, every other pan identical to stock, and stock's centre 1 step right-heavy (the bug being fixed).
"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import emu_p2k as ep        # noqa: E402

CH = 0x10050000


def gains(E, level, pan):
    E.mu.mem_write(CH, bytes(0x100))
    E.call(0x60784, [CH, level & 0xffff, pan & 0xffff, 0, 0])
    a, b = E.rd(CH + 113, 1)[0], E.rd(CH + 115, 1)[0]
    return a, b


def main():
    S, N = ep.Emu(open(sys.argv[1], 'rb').read()), ep.Emu(open(sys.argv[2], 'rb').read())
    fails, n = [], 0
    for level in (0, 20, 64, 128, 200, 255):
        for pan in range(-64, 64):
            s, b = gains(S, level, pan), gains(N, level, pan)
            n += 1
            if pan in (0, -1):
                if b[0] != b[1]:
                    fails.append(f'level {level} pan {pan}: beta2 {b} not balanced')
                if pan == 0 and level >= 32 and s[0] != s[1] + 1:
                    fails.append(f'level {level} pan 0: stock {s} not 1 step right-heavy')
            elif s != b:
                fails.append(f'level {level} pan {pan}: stock {s} beta2 {b}')
    print(f'{n} checks; {len(fails)} failures   (stock centre {gains(S, 128, 0)}, beta2 centre {gains(N, 128, 0)})')
    for f in fails[:10]:
        print('  ' + f)
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
