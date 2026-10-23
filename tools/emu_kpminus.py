#!/usr/bin/env python3
"""Emulator test of the keypad '-' fix (PC-AT keyboard, build_beta2.py KPM_*).

usage: emu_kpminus.py OLD.bin NEW.bin
Runs each image's own keypad handler 0x1431B8 (code, key-table entry, event) for every keypad scan code, with every
combination of Shift / Caps Lock / Num Lock in the modifier byte (0x10005084, bits 0 / 4 / 5), Ctrl / Alt held
(their key-down bytes, scan codes 0x14 / 0x11, which is where 0x143130 reads them) and the key's own key-down
byte, and compares the event it writes and its return value:
  keypad '-' (0x7B) with Num Lock on and no Ctrl/Alt: NEW must give type 1 with step -1 (as Num Lock off does),
      where OLD typed the character '-';
  every other case: identical.
"""
import itertools, struct, sys
from unicorn import Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN
from unicorn.m68k_const import UC_M68K_REG_A7, UC_M68K_REG_D0, UC_CPU_M68K_CFV4E

BASE, RET = 0x20000, 0x1000
HANDLER, TABLE, MODS, KEYS = 0x1431B8, 0x14355C, 0x10005084, 0x102D16C8
STACK, EVENT = 0x10080000, 0x10009000
KEYPAD = (0x69, 0x6B, 0x6C, 0x70, 0x71, 0x72, 0x73, 0x74, 0x75, 0x79, 0x7A, 0x7B, 0x7C, 0x7D)


class Emu:
    def __init__(self, img):
        self.mu = mu = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
        mu.ctl_set_cpu_model(UC_CPU_M68K_CFV4E)
        mu.mem_map(0, 0x220000)
        mu.mem_write(BASE, img)
        mu.mem_write(RET, b'\x4e\x71')
        mu.mem_map(0x10000000, 0x81000)
        mu.mem_map(0x102D1000, 0x1000)
        self.img = img

    def key(self, code, mods, down, ctrl, alt):
        mu = self.mu
        mu.mem_write(MODS, bytes([mods]))
        mu.mem_write(KEYS, bytes(0x84))
        mu.mem_write(KEYS + 0x14, bytes([ctrl]))
        mu.mem_write(KEYS + 0x11, bytes([alt]))
        mu.mem_write(KEYS + code, bytes([down]))
        mu.mem_write(EVENT, b'\xa5' * 8)
        entry = TABLE + code * 0x1C
        sp = STACK - 0x200
        mu.mem_write(sp, struct.pack('>IIII', RET, code, entry, EVENT))
        mu.reg_write(UC_M68K_REG_A7, sp)
        mu.emu_start(HANDLER, RET, count=2000)
        ev = bytes(mu.mem_read(EVENT, 8))
        return mu.reg_read(UC_M68K_REG_D0) & 0xFF, struct.unpack('>I', ev[:4])[0], struct.unpack('>h', ev[4:6])[0], ev[6]


def main():
    O, N = (Emu(open(p, 'rb').read()) for p in sys.argv[1:3])
    fails, n, fixed = [], 0, 0
    for code in KEYPAD:
        for bits in itertools.product((0, 1), repeat=5):
            shift, ctrl, alt, caps, num = bits
            mods = shift | caps << 4 | num << 5
            for down in (0, 0x40, 0x01):
                n += 1
                o, w = O.key(code, mods, down, ctrl, alt), N.key(code, mods, down, ctrl, alt)
                numlock_layer = code == 0x7B and num and not (ctrl or alt) and not down & 0x40
                if numlock_layer and o[0]:
                    fixed += 1
                    ok = o[1] == 3 and o[3] == 0x2D and w[0] == o[0] and w[1] == 1 and w[2] == -1
                else:
                    ok = o == w
                if not ok:
                    fails.append(f'code {code:#x} mods {mods:#04x} down {down:#x}: old {o} new {w}')
    print(f'{n} checks ({fixed} keypad "-" Num Lock cases changed to a step down); {len(fails)} failures')
    for f in fails[:12]:
        print('  ' + f)
    sys.exit(1 if fails or not fixed else 0)


if __name__ == '__main__':
    main()
