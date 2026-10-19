#!/usr/bin/env python3
"""Per-stage voice-tick timing probe on stock EOS 4.70 (patches/timeprobe/timeprobe.s). Diagnostic only.

usage: build_timeprobe.py STOCK.bin OUT.bin
Stubs in EXT 0x68BF0 (dormant method tables, unreferenced), wrapper + readout in the vector cave 0x20400.
Call sites in FUN_00060E80 (and the voice-tick call in FUN_000614B8) are redirected to the stubs.
Readout: SysEx parameter 195 (descriptor 0x25AF4).
"""
import os, struct, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import eos_lz   # noqa: E402

PDIR = os.path.join(os.path.dirname(HERE), 'patches', 'timeprobe')
BASE = 0x20000
BIN = '/opt/homebrew/bin/'
NAME = b'EOS 4.70 TIMEPROBE'
import os as _o
NAME = _o.environ.get('TP_NAME', NAME.decode()).encode()
EXT, CAVE = (0x68BF0, 0x68CA0), (0x20400, 0x205F0)
DESC = 0x25AF4
# call site -> (stub index, kind, stock target)
SITES = {0x614C4: (0, 'bsr', 0x60E80), 0x60EF4: (1, 'bsr', 0x5F89C), 0x60F1A: (2, 'jsr', 0x62208),
         0x60F66: (2, 'jsr', 0x62208), 0x60F7C: (2, 'jsr', 0x62208), 0x60F8C: (3, 'bsr', 0x5FD38),
         0x60FA0: (4, 'jsr', 0x61BC0), 0x60FB8: (5, 'jsr', 0x61D5C), 0x60FD0: (6, 'jsr', 0x62544),
         0x60FDE: (7, 'jsr', 0x62798), 0x60FEC: (8, 'bsr', 0x5FFD8), 0x60FF8: (9, 'bsr', 0x60B7C),
         0x61004: (10, 'bsr', 0x5FE4C), 0x60ED6: (11, 'jsr', 0x625F8)}
NAMES = ['voice tick', 'cords', 'envelopes x3', 'pitch env', 'LFO 1', 'LFO 2', 'aux', 'key/vel window',
         'filter', 'amp', 'pitch/loop chip', 'Ck sources']


def run(*cmd):
    subprocess.run(cmd, check=True, cwd=PDIR)


def main():
    src, out = sys.argv[1:3]
    img = bytearray(open(src, 'rb').read())
    run(BIN + 'm68k-elf-as', '-mcpu=5206e', '-o', 'tp.o', 'timeprobe.s')
    open(os.path.join(PDIR, 'tp.ld'), 'w').write(
        f'SECTIONS {{\n  .ext 0x{EXT[0]:X} : {{ tp.o(.ext) }}\n  .cave 0x{CAVE[0]:X} : {{ tp.o(.cave) }}\n}}\n')
    run(BIN + 'm68k-elf-ld', '-T', 'tp.ld', '-e', '_start', '-o', 'tp.elf', 'tp.o')
    data = {}
    for s in ('.ext', '.cave'):
        run(BIN + 'm68k-elf-objcopy', '-O', 'binary', '-j', s, 'tp.elf', f'tp{s.replace(".", "_")}.bin')
        data[s] = open(os.path.join(PDIR, f'tp{s.replace(".", "_")}.bin'), 'rb').read()
    syms = {}
    for line in subprocess.run([BIN + 'm68k-elf-nm', 'tp.elf'], check=True, capture_output=True, text=True,
                               cwd=PDIR).stdout.splitlines():
        a, _, n = line.split()
        syms[n] = int(a, 16)
    eo = EXT[0] - BASE
    if len(data['.ext']) > EXT[1] - EXT[0] or img[eo:eo + 8] != bytes(8) or \
            struct.unpack('>I', img[eo + 8:eo + 12])[0] != 0x1AB1B4:
        raise SystemExit('EXT is not the stock dormant table (base must be stock 4.70)')
    if len(data['.cave']) > CAVE[1] - CAVE[0] or bytes(img[CAVE[0] - BASE:CAVE[1] - BASE]) != bytes(CAVE[1] - CAVE[0]):
        raise SystemExit('vector cave not free')
    for a, (k, kind, tgt) in SITES.items():
        o = a - BASE
        if kind == 'bsr':
            op, disp = struct.unpack('>Hh', img[o:o + 4])
            if op != 0x6100 or a + 2 + disp != tgt:
                raise SystemExit(f'site {a:#x}: not bsr.w {tgt:#x}')
        elif img[o:o + 6] != b'\x4e\xb9' + struct.pack('>I', tgt):
            raise SystemExit(f'site {a:#x}: not jsr {tgt:#x}')
    mn, mx, get, put = struct.unpack('>ii', img[DESC + 6 - BASE:DESC + 14 - BASE]) + \
        struct.unpack('>II', img[DESC + 0x1A - BASE:DESC + 0x22 - BASE])
    if (mn, mx, get, put) != (-1, 7, 0, 0):
        raise SystemExit('descriptor 195 not stock')
    img[eo:eo + len(data['.ext'])] = data['.ext']
    img[CAVE[0] - BASE:CAVE[0] - BASE + len(data['.cave'])] = data['.cave']
    for a, (k, kind, tgt) in SITES.items():
        o, stub = a - BASE, syms[f'stub{k}']
        if kind == 'bsr':
            d = stub - (a + 2)
            if not -0x8000 <= d < 0x8000:
                raise SystemExit(f'site {a:#x}: stub out of bsr.w range')
            struct.pack_into('>h', img, o + 2, d)
        else:
            struct.pack_into('>I', img, o + 2, stub)
    struct.pack_into('>ii', img, DESC + 6 - BASE, 0, 31)
    struct.pack_into('>II', img, DESC + 0x1A - BASE, syms['probe_get'], syms['probe_set'])
    img[0x18:0x30] = NAME.ljust(24, b' ')
    struct.pack_into('>II', img, 4, 0, 0xffffffff)
    c = eos_lz.csum(img)
    struct.pack_into('>II', img, 4, c, c ^ 0xffffffff)
    open(out, 'wb').write(img)
    print(f'{out}: .ext {len(data[".ext"])}/{EXT[1] - EXT[0]}, .cave {len(data[".cave"])}/{CAVE[1] - CAVE[0]}; '
          f'checksum {c:08x}; name {NAME.decode()!r}; {len(SITES)} call sites')


if __name__ == '__main__':
    main()
