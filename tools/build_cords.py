#!/usr/bin/env python3
"""Cord processor optimization layer (patches/cords/cords.s) on top of Sync8+TW+HPBP6.

usage: build_cords.py BASE.bin OUT.bin [NAME]
Code in interrupt vectors 75-95 (0x2032C-0x2037F): all the default 'Gen Trap' handler, never taken.
0x5F8A4 in FUN_0005F89C (moveq #24,d7 ; lea $208(a1),a1) -> jsr cnt_hook;
FUN_0005F810 epilogue (0x5F892, movem + lea) -> jmp count_build + nop.
"""
import os, struct, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import eos_lz   # noqa: E402

PDIR = os.path.join(os.path.dirname(HERE), 'patches', 'cords')
BASE = 0x20000
BIN = '/opt/homebrew/bin/'
NAME = b'EOS 4.70 Sync8c+TW+HPBP6'
VLO = (0x2032C, 0x20380)
STOCK = os.path.join(os.path.dirname(HERE), 'bin', 'eos470_flash_0x20000.bin')
DEFAULT_VEC = 0x20926
CORDS, EPI = 0x5F89C, 0x5F892           # stock cord processor; epilogue of FUN_0005F810
CORDS_STOCK = '2f072f06226f000c'
HOOK, HOOK_STOCK = 0x5F8A4, '7e1843e90208'   # moveq #$18,d7 ; lea $208(a1),a1
EPI_STOCK = '4cd738804fef0010'          # movem.l (a7),d7/a3-a5 ; lea $10(a7),a7


def run(*cmd):
    subprocess.run(cmd, check=True, cwd=PDIR)


def build(base, out, name=NAME):
    img = bytearray(open(base, 'rb').read())
    run(BIN + 'm68k-elf-as', '-mcpu=5206e', '-o', 'cords.o', 'cords.s')
    open(os.path.join(PDIR, 'cords.ld'), 'w').write(
        f'SECTIONS {{\n  .vlo 0x{VLO[0]:X} : {{ cords.o(.vlo) }}\n}}\n')
    run(BIN + 'm68k-elf-ld', '-T', 'cords.ld', '-e', '_start', '-o', 'cords.elf', 'cords.o')
    data = {}
    for s in ('.vlo',):
        run(BIN + 'm68k-elf-objcopy', '-O', 'binary', '-j', s, 'cords.elf', f'cords{s.replace(".", "_")}.bin')
        data[s] = open(os.path.join(PDIR, f'cords{s.replace(".", "_")}.bin'), 'rb').read()
    syms = {}
    for line in subprocess.run([BIN + 'm68k-elf-nm', 'cords.elf'], check=True, capture_output=True, text=True,
                               cwd=PDIR).stdout.splitlines():
        a, _, n = line.split()
        syms[n] = int(a, 16)
    for s, (lo, hi) in (('.vlo', VLO),):
        if len(data[s]) > hi - lo:
            raise SystemExit(f'{s}: {len(data[s])} > {hi - lo}')
        if struct.unpack(f'>{(hi - lo) // 4}I', img[lo - BASE:hi - BASE]) != (DEFAULT_VEC,) * ((hi - lo) // 4):
            raise SystemExit(f'{s} {lo:#x}-{hi - 1:#x} not all default vectors')
    if img[CORDS - BASE:CORDS - BASE + 8].hex() != CORDS_STOCK or img[HOOK - BASE:HOOK - BASE + 6].hex() != HOOK_STOCK:
        raise SystemExit('FUN_0005F89C not stock')
    if img[EPI - BASE:EPI - BASE + 8].hex() != EPI_STOCK:
        raise SystemExit('FUN_0005F810 epilogue not stock')
    for s, (lo, _) in (('.vlo', VLO),):
        img[lo - BASE:lo - BASE + len(data[s])] = data[s]
    img[HOOK - BASE:HOOK - BASE + 6] = b'\x4e\xb9' + struct.pack('>I', syms['cnt_hook'])
    img[EPI - BASE:EPI - BASE + 8] = b'\x4e\xf9' + struct.pack('>I', syms['count_build']) + b'\x4e\x71'
    if len(name) > 24:
        raise SystemExit('name too long')
    img[0x18:0x30] = name.ljust(24, b' ')
    struct.pack_into('>II', img, 4, 0, 0xffffffff)
    c = eos_lz.csum(img)
    struct.pack_into('>II', img, 4, c, c ^ 0xffffffff)
    open(out, 'wb').write(img)
    print(f'{out}: .vlo {len(data[".vlo"])}/{VLO[1] - VLO[0]}; checksum {c:08x}; name {name.decode()!r}')
    return syms


if __name__ == '__main__':
    build(sys.argv[1], sys.argv[2], *(a.encode() for a in sys.argv[3:4]))
