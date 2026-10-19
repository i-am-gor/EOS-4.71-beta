#!/usr/bin/env python3
"""A/B diagnostic build: stock 4.70 + timing probe + cord patch + RFX skip, each switchable at runtime.

usage: build_ab.py OUT.bin
Switch byte ABSWITCH = 0x100003F0 (patch-RAM slot, zero at boot on a stock base: both patches OFF).
bit 0 = cord patch, bit 1 = RFX skip; set over SysEx: parameter 195 value 32 + bits.
OFF = stock code paths: cord loop runs 24 slots and no count byte is written; FUN_00060674 runs the stock
body (only its first 8 bytes are a jump to a dispatcher that re-executes them).
Layout: probe stubs in EXT, probe + new RFX writer + dispatcher in the vector cave, cord code in interrupt
vectors 96-127 and vol_only in vectors 75-95 (all the default handler on stock).
"""
import os, struct, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import eos_lz            # noqa: E402
import build_timeprobe as tp  # noqa: E402
import build_rfx as br   # noqa: E402

ROOT = os.path.dirname(HERE)
BIN = '/opt/homebrew/bin/'
BASE = 0x20000
SWITCH = 0x100003F0
NAME = b'EOS 4.70 AB C/R switch'
STOCK = os.path.join(ROOT, 'bin', 'eos470_flash_0x20000.bin')
VEC = (0x20380, 0x20400)
VLOW = (0x2032C, 0x20380)       # vectors 75-95 (default handler on stock): vol_only
DEFAULT_VEC = 0x20926


def asm(pdir, src, obj, sections, defsym=True):
    cmd = [BIN + 'm68k-elf-as', '-mcpu=5206e'] + (['--defsym', f'ABSWITCH={SWITCH:#x}'] if defsym else []) + ['-o', obj, src]
    subprocess.run(cmd, check=True, cwd=pdir)
    ld = 'SECTIONS {\n' + ''.join(f'  {s} 0x{a:X} : {{ {obj}({s}) }}\n' for s, a in sections) + '}\n'
    open(os.path.join(pdir, obj + '.ld'), 'w').write(ld)
    subprocess.run([BIN + 'm68k-elf-ld', '-T', obj + '.ld', '-e', '_start', '-o', obj + '.elf', obj], check=True, cwd=pdir)
    data = {}
    for s, _ in sections:
        out = obj + s.replace('.', '_') + '.bin'
        subprocess.run([BIN + 'm68k-elf-objcopy', '-O', 'binary', '-j', s, obj + '.elf', out], check=True, cwd=pdir)
        data[s] = open(os.path.join(pdir, out), 'rb').read()
    syms = {}
    for line in subprocess.run([BIN + 'm68k-elf-nm', obj + '.elf'], check=True, capture_output=True, text=True,
                               cwd=pdir).stdout.splitlines():
        a, _, n = line.split()
        syms[n] = int(a, 16)
    return data, syms


def put(img, addr, data, limit):
    if addr + len(data) > limit:
        raise SystemExit(f'{addr:#x}: {len(data)} bytes overflow {limit:#x}')
    img[addr - BASE:addr - BASE + len(data)] = data
    return addr + len(data)


def main():
    out = sys.argv[1]
    img = bytearray(open(STOCK, 'rb').read())
    stock = bytes(img)
    if struct.unpack('>53I', img[VLOW[0] - BASE:VEC[1] - BASE]) != (DEFAULT_VEC,) * 53:
        raise SystemExit('vectors 75-127 not default')
    if bytes(img[SWITCH - 0x10000000 + 0x20200 - BASE:SWITCH - 0x10000000 + 0x20200 - BASE + 4]) != bytes(4):
        raise SystemExit('switch byte flash image not zero')
    # 1. timing probe with the switch command (EXT stubs + cave)
    pd = os.path.join(ROOT, 'patches', 'timeprobe')
    d, sy = asm(pd, 'timeprobe.s', 'tpab.o', [('.ext', tp.EXT[0]), ('.cave', tp.CAVE[0])])
    put(img, tp.EXT[0], d['.ext'], tp.EXT[1])
    cave_end = put(img, tp.CAVE[0], d['.cave'], tp.CAVE[1])
    for a, (k, kind, tgt) in tp.SITES.items():
        stub = sy[f'stub{k}']
        if kind == 'bsr':
            struct.pack_into('>h', img, a - BASE + 2, stub - (a + 2))
        else:
            struct.pack_into('>I', img, a - BASE + 2, stub)
    struct.pack_into('>ii', img, tp.DESC + 6 - BASE, 0, 35)
    struct.pack_into('>II', img, tp.DESC + 0x1A - BASE, sy['probe_get'], sy['probe_set'])
    # 2. cord patch (switch variant) at the start of vectors 96-127
    pc = os.path.join(ROOT, 'patches', 'cords')
    d, syc = asm(pc, 'cords.s', 'cab.o', [('.vlo', VEC[0])])
    vec_next = put(img, VEC[0], d['.vlo'], VEC[1])
    img[0x5F8A4 - BASE:0x5F8AA - BASE] = b'\x4e\xb9' + struct.pack('>I', syc['cnt_hook'])
    img[0x5F892 - BASE:0x5F89A - BASE] = b'\x4e\xf9' + struct.pack('>I', syc['count_build']) + b'\x4e\x71'
    # 3. RFX: new writer in the cave after the probe; vol_only + dispatcher in vectors; jump at 0x60674
    pr = os.path.join(ROOT, 'patches', 'rfx')
    body_at = (cave_end + 3) & ~3
    vtail_at = VLOW[0]
    d0, s0 = asm(pr, 'rfx_ab.s', 'rab.o', [('.body', body_at), ('.vtail', vtail_at), ('.disp', 0x60674),
                                         ('.dsp2', body_at + 0x112)])
    put(img, vtail_at, d0['.vtail'], VLOW[1])
    if len(d0['.body']) > 0x112:
        raise SystemExit('RFX writer larger than its slot')
    put(img, body_at, d0['.body'], body_at + 0x112)
    disp_end = put(img, body_at + 0x112, d0['.dsp2'], tp.CAVE[1])
    if img[0x60674 - BASE:0x6067C - BASE] != stock[0x60674 - BASE:0x6067C - BASE]:
        raise SystemExit('FUN_00060674 entry not stock')
    put(img, 0x60674, d0['.disp'], 0x6067C)
    img[0x18:0x30] = NAME.ljust(24, b' ')
    struct.pack_into('>II', img, 4, 0, 0xffffffff)
    c = eos_lz.csum(img)
    struct.pack_into('>II', img, 4, c, c ^ 0xffffffff)
    open(out, 'wb').write(img)
    print(f'{out}: probe cave {tp.CAVE[0]:#x}-{cave_end:#x}, RFX writer {body_at:#x}+{len(d0[".body"])}, cords '
          f'{VEC[0]:#x}+{len(d["vlo" if False else ".vlo"]) if False else vec_next - VEC[0]}, vol_only {vtail_at:#x}+'
          f'{len(d0[".vtail"])}, dispatcher {body_at + 0x112:#x}+{len(d0[".dsp2"])} (cave used to {disp_end:#x} of {tp.CAVE[1]:#x}); checksum {c:08x}; '
          f'syms cnt_hook={syc["cnt_hook"]:#x} count_build={syc["count_build"]:#x} rfx_writer={s0["rfx_writer"]:#x}')


if __name__ == '__main__':
    main()
