#!/usr/bin/env python3
"""Diagnostic CPU-load probe on top of an EOS 4.70 Sync8+TW+HPBP6 image (patches/probe/probe.s).

usage: build_probe.py BASE.bin OUT.bin
Code in interrupt vectors 76-95 (0x20330-0x2037F) and the free end of vectors 96-127 (0x203D0-0x203FF):
all the default 'Gen Trap' handler, never taken (EOS programs vectors 64-74). Hooks: main loop 0x321DE,
voice tick 0x60E90. Readout: SysEx parameter 195 (descriptor 0x25AF4) gets the probe getter/setter.
"""
import os, struct, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import eos_lz   # noqa: E402

PDIR = os.path.join(os.path.dirname(HERE), 'patches', 'probe')
BASE = 0x20000
BIN = '/opt/homebrew/bin/'
NAME = b'EOS 4.70 Sync8 LOADPROBE'
VLO, VHI = (0x20330, 0x20380), (0x203D0, 0x20400)
EXT2 = (0x68C7A, 0x68CA0)        # free tail of EXT after the Sync8 code (stock dormant method table, unreferenced)
STOCK = os.path.join(os.path.dirname(HERE), 'bin', 'eos470_flash_0x20000.bin')
DEFAULT_VEC = 0x20926
HOOKS = {0x321DE: ('41ed01842f08', 'probe_loop'), 0x60E90: ('2c3910000450', 'probe_tick')}
DESC = 0x25AF4                    # parameter 195 'Foreign sampler SCSI ID': +6 min, +10 max, +0x1A get, +0x1E set


def run(*cmd):
    subprocess.run(cmd, check=True, cwd=PDIR)


def main():
    base, out = sys.argv[1:3]
    img = bytearray(open(base, 'rb').read())
    run(BIN + 'm68k-elf-as', '-mcpu=5206e', '-o', 'probe.o', 'probe.s')
    open(os.path.join(PDIR, 'probe.ld'), 'w').write(
        f'SECTIONS {{\n  .vlo 0x{VLO[0]:X} : {{ probe.o(.vlo) }}\n  .vhi 0x{VHI[0]:X} : {{ probe.o(.vhi) }}\n'
        f'  .ext2 0x{EXT2[0]:X} : {{ probe.o(.ext2) }}\n}}\n')
    run(BIN + 'm68k-elf-ld', '-T', 'probe.ld', '-e', '_start', '-o', 'probe.elf', 'probe.o')
    data = {}
    for s in ('.vlo', '.vhi', '.ext2'):
        run(BIN + 'm68k-elf-objcopy', '-O', 'binary', '-j', s, 'probe.elf', f'probe{s.replace(".", "_")}.bin')
        data[s] = open(os.path.join(PDIR, f'probe{s.replace(".", "_")}.bin'), 'rb').read()
    syms = {}
    for line in subprocess.run([BIN + 'm68k-elf-nm', 'probe.elf'], check=True, capture_output=True, text=True,
                               cwd=PDIR).stdout.splitlines():
        a, _, n = line.split()
        syms[n] = int(a, 16)
    for s, (lo, hi) in (('.vlo', VLO), ('.vhi', VHI)):
        if len(data[s]) > hi - lo:
            raise SystemExit(f'{s}: {len(data[s])} > {hi - lo} bytes')
        if struct.unpack(f'>{(hi - lo) // 4}I', img[lo - BASE:hi - BASE]) != (DEFAULT_VEC,) * ((hi - lo) // 4):
            raise SystemExit(f'{s} area {lo:#x}-{hi - 1:#x} is not all default vectors')
    stock = open(STOCK, 'rb').read()
    if len(data['.ext2']) > EXT2[1] - EXT2[0] or img[EXT2[0] - BASE:EXT2[1] - BASE] != stock[EXT2[0] - BASE:EXT2[1] - BASE]:
        raise SystemExit('EXT tail is not free stock bytes')
    for a, (stock_, _) in HOOKS.items():
        if img[a - BASE:a - BASE + 6].hex() != stock_:
            raise SystemExit(f'hook {a:#x}: unexpected {img[a - BASE:a - BASE + 6].hex()}')
    mn, mx = struct.unpack('>ii', img[DESC + 6 - BASE:DESC + 14 - BASE])
    get, put = struct.unpack('>II', img[DESC + 0x1A - BASE:DESC + 0x22 - BASE])
    if (mn, mx, get, put) != (-1, 7, 0, 0):
        raise SystemExit(f'descriptor 195 not stock: {mn} {mx} {get:#x} {put:#x}')
    for s, (lo, _) in (('.vlo', VLO), ('.vhi', VHI), ('.ext2', EXT2)):
        img[lo - BASE:lo - BASE + len(data[s])] = data[s]
    for a, (_, sym) in HOOKS.items():
        img[a - BASE:a - BASE + 6] = b'\x4e\xb9' + struct.pack('>I', syms[sym])
    struct.pack_into('>ii', img, DESC + 6 - BASE, 0, 15)
    struct.pack_into('>II', img, DESC + 0x1A - BASE, syms['probe_get'], syms['probe_set'])
    img[0x18:0x30] = NAME.ljust(24, b' ')
    struct.pack_into('>II', img, 4, 0, 0xffffffff)
    c = eos_lz.csum(img)
    struct.pack_into('>II', img, 4, c, c ^ 0xffffffff)
    open(out, 'wb').write(img)
    print(f'{out}: .vlo {len(data[".vlo"])}/{VLO[1] - VLO[0]}, .vhi {len(data[".vhi"])}/{VHI[1] - VHI[0]}, '
          f'.ext2 {len(data[".ext2"])}/{EXT2[1] - EXT2[0]}; '
          f'checksum {c:08x}; name {NAME.decode()!r}; ' + ', '.join(f'{k}={v:#x}' for k, v in syms.items() if k.startswith('probe')))


if __name__ == '__main__':
    main()
