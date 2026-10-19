#!/usr/bin/env python3
"""RFX amp-path skip layer (patches/rfx/rfx.s): FUN_00060674 replaced in place (0x60674-0x60783).

usage: build_rfx.py BASE.bin OUT.bin [NAME]
Checks: the 272 bytes are stock 4.70; no code outside the function branches or jumps into it except at its
entry; new body <= 272 bytes (rest NOP).
"""
import os, re, struct, subprocess, sys
import capstone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import eos_lz   # noqa: E402

PDIR = os.path.join(os.path.dirname(HERE), 'patches', 'rfx')
BASE = 0x20000
BIN = '/opt/homebrew/bin/'
NAME = b'EOS 4.70 Sync8d+TW+HPBP6'
FN = (0x60674, 0x60784)
VTAIL = (0x203D0, 0x20400)     # free end of interrupt vectors 96-127 (default handler)
DEFAULT_VEC = 0x20926
STOCK = os.path.join(os.path.dirname(HERE), 'bin', 'eos470_flash_0x20000.bin')


def run(*cmd):
    subprocess.run(cmd, check=True, cwd=PDIR)


def inbound(img):
    """Branch/jump/call targets inside FN[0]+1..FN[1] from code outside the function."""
    md = capstone.Cs(capstone.CS_ARCH_M68K, capstone.CS_MODE_BIG_ENDIAN | capstone.CS_MODE_M68K_040)
    bad = []
    for o in range(0, 0x1F86F0 - BASE, 0x4000):
        for i in md.disasm(img[o:o + 0x4000 + 16], BASE + o):
            if FN[0] <= i.address < FN[1]:
                continue
            m = re.match(r'\$([0-9a-f]+)', i.op_str)
            if i.mnemonic[0] in 'bj' and m and FN[0] < int(m.group(1), 16) < FN[1]:
                bad.append((hex(i.address), i.mnemonic, i.op_str))
    return bad


def build(base, out, name=NAME):
    img = bytearray(open(base, 'rb').read())
    run(BIN + 'm68k-elf-as', '-mcpu=5206e', '-o', 'rfx.o', 'rfx.s')
    open(os.path.join(PDIR, 'rfx.ld'), 'w').write(f'SECTIONS {{\n  .body 0x{FN[0]:X} : {{ rfx.o(.body) }}\n'
                                                f'  .vtail 0x{VTAIL[0]:X} : {{ rfx.o(.vtail) }}\n}}\n')
    run(BIN + 'm68k-elf-ld', '-T', 'rfx.ld', '-e', '_start', '-o', 'rfx.elf', 'rfx.o')
    run(BIN + 'm68k-elf-objcopy', '-O', 'binary', '-j', '.body', 'rfx.elf', 'rfx_body.bin')
    body = open(os.path.join(PDIR, 'rfx_body.bin'), 'rb').read()
    run(BIN + 'm68k-elf-objcopy', '-O', 'binary', '-j', '.vtail', 'rfx.elf', 'rfx_vtail.bin')
    vtail = open(os.path.join(PDIR, 'rfx_vtail.bin'), 'rb').read()
    vlo, vhi = VTAIL[0] - BASE, VTAIL[1] - BASE
    if len(vtail) > vhi - vlo or struct.unpack(f'>{(vhi - vlo) // 4}I', img[vlo:vhi]) != (DEFAULT_VEC,) * ((vhi - vlo) // 4):
        raise SystemExit('vectors 116-127 not free (default handler) or vol_only too big')
    stock = open(STOCK, 'rb').read()
    lo, hi = FN[0] - BASE, FN[1] - BASE
    if img[lo:hi] != stock[lo:hi]:
        raise SystemExit('FUN_00060674 is not stock in the base image')
    if len(body) > hi - lo:
        raise SystemExit(f'body {len(body)} > {hi - lo} bytes')
    bad = inbound(img)
    if bad:
        raise SystemExit(f'branches into FUN_00060674 body: {bad[:5]}')
    img[lo:lo + len(body)] = body
    img[lo + len(body):hi] = b'\x4e\x71' * ((hi - lo - len(body)) // 2)
    img[vlo:vlo + len(vtail)] = vtail
    if len(name) > 24:
        raise SystemExit('name too long')
    img[0x18:0x30] = name.ljust(24, b' ')
    struct.pack_into('>II', img, 4, 0, 0xffffffff)
    c = eos_lz.csum(img)
    struct.pack_into('>II', img, 4, c, c ^ 0xffffffff)
    open(out, 'wb').write(img)
    print(f'{out}: FUN_00060674 body {len(body)}/{hi - lo}, vol_only {len(vtail)}/{VTAIL[1] - VTAIL[0]}; checksum {c:08x}; name {name.decode()!r}')


if __name__ == '__main__':
    build(sys.argv[1], sys.argv[2], *(a.encode() for a in sys.argv[3:4]))
