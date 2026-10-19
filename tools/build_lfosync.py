#!/usr/bin/env python3
"""Build the LFO tempo-sync patch on top of an EOS 4.70 image (stock or OB-Xa v3d).

usage: build_lfosync.py BASE.bin OUT.bin [NAME]
Assembles patches/lfosync/lfosync.s at 0x20400 (unused interrupt vectors 128-255, all zero in 4.70),
hooks the LFO tick (0x61BF4) and the end of LFO init (0x61B9C), extends LFO 1/2 Rate to 0..143 in
the front-panel field descriptors (0x6B5B0, 0x6B65A, new formatter) and the editor/SysEx voice
descriptors (0x5AC6A, 0x5AD14), sets the header name and fixes the checksum.
"""
import os, struct, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import eos_lz   # noqa: E402

ROOT = os.path.dirname(HERE)
PDIR = os.path.join(ROOT, 'patches', 'lfosync')
BASE = 0x20000
CAVE = (0x20400, 0x20600)
EXT = (0x68BF0, 0x68CA0)      # dormant filter method tables (unreferenced; v3d leaves them stock)
HDR = (0x20080, 0x201C0)      # image header padding (zero; loader header fields end at 0x20041); 0x201C0.. = HPBP .hdr2
OBX = (0x660B0, 0x660C0)
VEC = (0x20380, 0x20400)      # interrupt vectors 96-127: all the default 'Gen Trap' handler, never taken
VEC_DEFAULT = 0x20926
# stock 16-bit words replaced in place: address -> (stock hex, new hex)
WORD_PATCHES = {
    0x60A50: ('e885', 'ea85'),   # pan bug: final pan = sum >> 4 -> >> 5 (note-on, FUN_000609D8)
    0x60BEA: ('e881', 'ea81'),   # same, per tick (FUN_00060B7C)
}      # NOP padding at the end of the OB-Xa region (v3d code ends at 0x660B0)
BIN = '/opt/homebrew/bin/'
NDIV = 16
RATE_MAX = 127 + NDIV
NAME = b'EOS 4.70 Sync8+Transwave'

# hook address -> (stock bytes, symbol, pad)
HOOKS = {
    0x61BF4: ('7c00302d0010', 'lfo_tick'),          # moveq #0,d6 ; move.w 0x10(a5),d0
    0x61B9C: ('426d0018426d001a', 'lfo_init'),      # clr.w 0x18(a5) ; clr.w 0x1a(a5)
}
# hook address -> (stock bytes, symbol): jsr instead of jmp (returns to the next stock instruction)
JSR_HOOKS = {
    0x61C84: ('7000302d0012e080', 'lfo_look'),
    0x21732: ('4aa800106664', 'mclk_hook'),         # FUN_0002172C: tst.l $10(a0) ; bne.b $2179c (external: return)      # moveq #0,d0 ; move.w 0x12(a5),d0 ; asr.l #8,d0
    # loop shift d7 = word 0x1C(a5) + (word 0x0A(a5) >> 5): note-on (FUN_0005FAE0), every tick (FUN_0005FE4C)
    0x5FBA6: ('3e2d001c322d000a48c748c1ea81de81', 'sl_shift'),
    0x5FECA: ('3e2d001c322d000a48c748c1ea81de81', 'sl_shift'),
}
# cord destination table 0x6344C (8 bytes per code: name ptr, accumulator offset, flags)
DEST_TABLE = 0x6344C
NEW_DESTS = {58: ('name_scn', 0x1C, 0x200)}   # SLpScn on unused code 58 (offset 0x1E); 55 stays unused
NOP_OUT = {0x135F24: '4eb9000216c0'}                # jsr FUN_000216C0: now called from midi_clk2
# stock immediates patched: address -> (stock bytes, new bytes or symbol)
SHAPE_FMT_MASKS = (0x6A8E8, 0x6A8F2)                # and.l #$f,d0 in the shape formatter -> #$1f
SYNC_FMT_TABLE = 0x6A912                            # movea.l #$10003374,a0 operand in the sync formatter
SHAPE_NAME16 = 0x1FB664                             # .data pointer: shape-name table entry 16 (was "key sync")
UI_SHAPE = (0x6B5D2, 0x6B67C)                       # front-panel 'Shape' fields
VOICE_SHAPE = (0x5AC8C, 0x5AD36)                    # editor/SysEx voice parameters 106, 111
SHAPE_MAX = 16
# jsr <abs> in the MIDI realtime parser (FUN_00135DF8) whose target is replaced: address -> (stock target, symbol)
CALLS = {
    0x135F1E: (0x136B0C, 'midi_clk'),     # F8 timing clock: empty stub, called before FUN_000216C0
    0x135F2C: (0x136B10, 'midi_start'),   # FA start
}
PATCH_RAM_FLASH = 0x205F0          # flash bytes copied to the patch RAM (0x100003F0..): must stay zero
UI_RATE = (0x6B5B0, 0x6B65A)        # front-panel 'Rate' fields (LFO 1, LFO 2)
VOICE_RATE = (0x5AC6A, 0x5AD14)     # editor/SysEx voice parameters 105, 110
STOCK_FMT = 0x6A880


def run(*cmd):
    subprocess.run(cmd, check=True, cwd=PDIR)


def assemble():
    run(BIN + 'm68k-elf-as', '-mcpu=5206e', '-o', 'lfosync.o', 'lfosync.s')
    with open(os.path.join(PDIR, 'lfosync.ld'), 'w') as f:
        f.write('SECTIONS {\n  .text 0x%X : { lfosync.o(.text) }\n  .ext 0x%X : { lfosync.o(.ext) }\n  .obx 0x%X : { lfosync.o(.obx) }\n  .hdr 0x%X : { lfosync.o(.hdr) }\n  .vec 0x%X : { lfosync.o(.vec) }\n}\n'
                % (CAVE[0], EXT[0], OBX[0], HDR[0], VEC[0]))
    run(BIN + 'm68k-elf-ld', '-T', 'lfosync.ld', '-e', '_start', '-o', 'lfosync.elf', 'lfosync.o')
    run(BIN + 'm68k-elf-objcopy', '-O', 'binary', '-j', '.text', 'lfosync.elf', 'lfosync.bin')
    run(BIN + 'm68k-elf-objcopy', '-O', 'binary', '-j', '.ext', 'lfosync.elf', 'lfosync_ext.bin')
    run(BIN + 'm68k-elf-objcopy', '-O', 'binary', '-j', '.obx', 'lfosync.elf', 'lfosync_obx.bin')
    run(BIN + 'm68k-elf-objcopy', '-O', 'binary', '-j', '.hdr', 'lfosync.elf', 'lfosync_hdr.bin')
    run(BIN + 'm68k-elf-objcopy', '-O', 'binary', '-j', '.vec', 'lfosync.elf', 'lfosync_vec.bin')
    syms = {}
    out = subprocess.run([BIN + 'm68k-elf-nm', 'lfosync.elf'], check=True, capture_output=True, text=True, cwd=PDIR).stdout
    for line in out.splitlines():
        a, _, n = line.split()
        syms[n] = int(a, 16)
    return (open(os.path.join(PDIR, 'lfosync.bin'), 'rb').read(), syms,
            open(os.path.join(PDIR, 'lfosync_ext.bin'), 'rb').read(),
            open(os.path.join(PDIR, 'lfosync_obx.bin'), 'rb').read(),
            open(os.path.join(PDIR, 'lfosync_hdr.bin'), 'rb').read(),
            open(os.path.join(PDIR, 'lfosync_vec.bin'), 'rb').read())


def desc(img, a):
    o = a - BASE
    mn, mx, off = struct.unpack('>iII', img[o + 6:o + 18])
    return dict(min=mn, max=mx, off=off, width=img[o + 0x14], scale=img[o + 0x15],
                fmt=struct.unpack('>I', img[o + 0x16:o + 0x1A])[0])


def build(base_path, out_path, name=NAME):
    img = bytearray(open(base_path, 'rb').read())
    code, syms, ext, obx, hdr, vec = assemble()
    if len(vec) > VEC[1] - VEC[0]:
        raise SystemExit(f'vec too big: {len(vec)} > {VEC[1] - VEC[0]}')
    if struct.unpack(f'>{(VEC[1] - VEC[0]) // 4}I', img[VEC[0] - BASE:VEC[1] - BASE]) != (VEC_DEFAULT,) * ((VEC[1] - VEC[0]) // 4):
        raise SystemExit('vectors 96-127 are not all the default handler')
    for a, (stock, _) in WORD_PATCHES.items():
        if img[a - BASE:a - BASE + 2].hex() != stock:
            raise SystemExit(f'word patch {a:#x}: unexpected bytes {img[a - BASE:a - BASE + 2].hex()}')
    lo, hi = CAVE
    if lo + len(code) > PATCH_RAM_FLASH:
        raise SystemExit(f'patch too big: {len(code)} > {PATCH_RAM_FLASH - lo} (would overlap the patch RAM image)')
    if bytes(img[lo - BASE:hi - BASE]) != bytes(hi - lo):
        raise SystemExit('vector cave 0x20400-0x205FF is not all zero')
    eo = EXT[0] - BASE
    if len(ext) > EXT[1] - EXT[0]:
        raise SystemExit(f'ext too big: {len(ext)}')
    if img[eo:eo + 8] != bytes(8) or struct.unpack('>I', img[eo + 8:eo + 12])[0] != 0x1AB1B4:
        raise SystemExit('EXT region is not the stock dormant method tables')
    for o in range(0, len(img) - 4, 2):
        v = struct.unpack('>I', img[o:o + 4])[0]
        if EXT[0] <= v < EXT[1] and not EXT[0] <= BASE + o < EXT[1]:
            raise SystemExit(f'EXT region referenced from {BASE + o:#x}')
    for a, (stock, _) in HOOKS.items():
        if img[a - BASE:a - BASE + len(stock) // 2].hex() != stock:
            raise SystemExit(f'hook {a:#x}: unexpected bytes {img[a - BASE:a - BASE + 8].hex()}')
    ho = HDR[0] - BASE
    if len(hdr) > HDR[1] - HDR[0]:
        raise SystemExit(f'hdr too big: {len(hdr)} > {HDR[1] - HDR[0]}')
    if bytes(img[0x30:HDR[1] - BASE]) != bytes(HDR[1] - BASE - 0x30):
        raise SystemExit('image header 0x20030-0x201FF is not all zero')
    for code_, (_, off_, fl_) in NEW_DESTS.items():
        o_ = DEST_TABLE + 8 * code_ - BASE
        cur = struct.unpack('>IHH', img[o_:o_ + 8])
        if cur[1] != 0x1E:
            raise SystemExit(f'destination {code_} is in use: {cur}')
    oo = OBX[0] - BASE
    if len(obx) > OBX[1] - OBX[0] or bytes(img[oo:OBX[1] - BASE]) != b'\x4e\x71' * ((OBX[1] - OBX[0]) // 2):
        raise SystemExit('OB-Xa tail 0x660B0-0x660BF is not NOP padding (base must be OB-Xa v3d)')
    for a, (stock, _) in list(JSR_HOOKS.items()) + [(a, (st, None)) for a, st in NOP_OUT.items()]:
        if img[a - BASE:a - BASE + len(stock) // 2].hex() != stock:
            raise SystemExit(f'hook {a:#x}: unexpected bytes {img[a - BASE:a - BASE + 8].hex()}')
    for a in SHAPE_FMT_MASKS:
        if img[a - BASE:a - BASE + 6].hex() != 'c0bc0000000f':
            raise SystemExit(f'shape formatter mask at {a:#x} not stock')
    if img[SYNC_FMT_TABLE - BASE:SYNC_FMT_TABLE - BASE + 4] != struct.pack('>I', 0x10003374):
        raise SystemExit('sync formatter table operand not stock')
    if img[SHAPE_NAME16 - BASE:SHAPE_NAME16 - BASE + 4] != struct.pack('>I', 0x6C620):
        raise SystemExit('.data shape/sync name pointer not stock')
    for a, off in zip(UI_SHAPE + VOICE_SHAPE, (0x97, 0x9F, 0x97, 0x9F)):
        d = desc(img, a)
        if d['min'] not in (-1, 0) or (d['max'], d['off'], d['width'], d['scale']) != (15, off, 8, 0):
            raise SystemExit(f'descriptor {a:#x} not stock LFO Shape: {d}')
    for a, (tgt, _) in CALLS.items():
        if img[a - BASE:a - BASE + 6] != b'\x4e\xb9' + struct.pack('>I', tgt):
            raise SystemExit(f'call {a:#x}: not jsr {tgt:#x}')
    for a, off in zip(UI_RATE + VOICE_RATE, (0x96, 0x9E, 0x96, 0x9E)):
        d = desc(img, a)
        if (d['min'], d['max'], d['off'], d['width'], d['scale']) != (0, 127, off, 8, 127):
            raise SystemExit(f'descriptor {a:#x} not stock LFO Rate: {d}')
    for a in UI_RATE:
        if desc(img, a)['fmt'] != STOCK_FMT:
            raise SystemExit(f'descriptor {a:#x}: formatter is not the stock rate formatter')

    img[lo - BASE:lo - BASE + len(code)] = code
    img[eo:eo + len(ext)] = ext
    img[oo:oo + len(obx)] = obx
    img[ho:ho + len(hdr)] = hdr
    img[VEC[0] - BASE:VEC[0] - BASE + len(vec)] = vec
    for a, (_, new) in WORD_PATCHES.items():
        img[a - BASE:a - BASE + 2] = bytes.fromhex(new)
    for code_, (sym_, off_, fl_) in NEW_DESTS.items():
        struct.pack_into('>IHH', img, DEST_TABLE + 8 * code_ - BASE, syms[sym_], off_, fl_)
    for a, (stock, sym) in JSR_HOOKS.items():
        n = len(stock) // 2
        img[a - BASE:a - BASE + n] = b'\x4e\xb9' + struct.pack('>I', syms[sym]) + b'\x4e\x71' * ((n - 6) // 2)
    for a, stock in NOP_OUT.items():
        img[a - BASE:a - BASE + len(stock) // 2] = b'\x4e\x71' * (len(stock) // 4)
    for a in SHAPE_FMT_MASKS:
        img[a - BASE:a - BASE + 6] = bytes.fromhex('c0bc0000001f')
    struct.pack_into('>I', img, SYNC_FMT_TABLE - BASE, syms['synctab'])
    struct.pack_into('>I', img, SHAPE_NAME16 - BASE, syms['sawname'])
    for a in UI_SHAPE + VOICE_SHAPE:
        struct.pack_into('>I', img, a - BASE + 10, SHAPE_MAX)
    for a, (stock, sym) in HOOKS.items():
        n = len(stock) // 2
        patch = b'\x4e\xf9' + struct.pack('>I', syms[sym])
        img[a - BASE:a - BASE + n] = patch + b'\x4e\x71' * ((n - 6) // 2)
    for a, (_, sym) in CALLS.items():
        struct.pack_into('>I', img, a - BASE + 2, syms[sym])
    for a in UI_RATE + VOICE_RATE:
        o = a - BASE
        struct.pack_into('>I', img, o + 10, RATE_MAX)
        img[o + 0x15] = RATE_MAX                     # scale = max: stored value = displayed value
    for a in UI_RATE:
        struct.pack_into('>I', img, a - BASE + 0x16, syms['lfo_fmt'])

    if len(name) > 24:
        raise SystemExit(f'header name {name!r} is {len(name)} bytes; the field holds 24')
    size0 = len(img)
    img[0x18:0x30] = name.ljust(24, b' ')
    if len(img) != size0 or len(img) != len(open(base_path, 'rb').read()):
        raise SystemExit('image size changed while patching')
    struct.pack_into('>II', img, 4, 0, 0xffffffff)
    c = eos_lz.csum(img)
    struct.pack_into('>II', img, 4, c, c ^ 0xffffffff)
    open(out_path, 'wb').write(img)
    print(f'{out_path}: {len(code)} / {PATCH_RAM_FLASH - lo} bytes in the vector cave, {len(ext)} / {EXT[1] - EXT[0]} in EXT, {len(obx)} / {OBX[1] - OBX[0]} in the OB-Xa tail, {len(hdr)} / {HDR[1] - HDR[0]} in the header, {len(vec)} / {VEC[1] - VEC[0]} in vectors 96-127, checksum {c:08x}, name {name.decode()!r}')
    print('symbols: ' + ', '.join(f'{k}={v:#x}' for k, v in sorted(syms.items(), key=lambda kv: kv[1])
                                    if not k.startswith(('_', '.'))))
    return syms


if __name__ == '__main__':
    build(sys.argv[1], sys.argv[2], *(a.encode() for a in sys.argv[3:4]))
