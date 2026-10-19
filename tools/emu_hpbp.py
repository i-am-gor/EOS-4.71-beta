#!/usr/bin/env python3
"""Emulator test for the OB-Xa high-pass / band-pass patch (Unicorn, ColdFire V4e).

usage: emu_hpbp.py BASE.bin PATCHED.bin
Methods are reached through each image's own vtables. For 2nd/4th Order High-pass and Band-pass:
  computeFrames q 0..255: return value, SETMODE arguments, gain word 9, untouched words 2/3/6/7 and all
    non-pole words equal stock; pole words equal tools/hpbp.py (q 0..127)
  packQ q 0..127 (on a block first built by computeFrames): return value equals stock; pole words equal
    the tables; every other word equals the stock result
Display text (formatParam) of HP2, HP4, BP2, BP4 and Contrary BP: identical to stock for idx 0..2,
value 0..255. Every other vtable slot (0x6884C..0x68C9F) unchanged.
"""
import struct, sys
from unicorn import UC_HOOK_CODE

import emu_obxa as eo
import hpbp

BASE = 0x20000
LBUF, VBUF = 0x1000A000, 0x1000A100
F = {'HP2': (0x688FC, 'HP', 2, (4,)), 'HP4': (0x68928, 'HP', 4, (4, 8)),
     'BP2': (0x689D8, 'BP', 2, (8,)), 'BP4': (0x68A04, 'BP', 4, (0, 8)), 'CBP': (0x68A30, 'CBP', 2, (0,))}
CONTRARY = 0x68A30


def slot(img, vt, off):
    return struct.unpack('>I', img[vt + off - BASE:vt + off + 4 - BASE])[0]


def block(E):
    return list(struct.unpack('>16I', E.mu.mem_read(eo.BLK, 64)))


def main():
    stock_img, new_img = (open(p, 'rb').read() for p in sys.argv[1:3])
    S, N = eo.Emu(stock_img), eo.Emu(new_img)
    fails, n = [], 0
    for name, (vt, kind, poles, pole_words) in F.items():
        for q in range(256):
            args = [0, eo.BLK, 3, q, eo.STRUCT]
            ra, ba, ca = S.call(slot(stock_img, vt, 0x14), args)
            rb, bb, cb = N.call(slot(new_img, vt, 0x14), args)
            n += 1
            if hpbp.expected_return(kind, poles, q, ra) != rb or ca != cb:
                fails.append(f'{name} cf q{q}: return {ra:#x}/{rb:#x} setmode {ca}/{cb}')
            for w in range(16):
                if w not in pole_words and ba[w] != bb[w]:
                    fails.append(f'{name} cf q{q}: word {w} {ba[w]:08X} != stock {bb[w]:08X}'); break
            if q < 128:
                exp = hpbp.expected_block(kind, poles, q)
                for w, v in exp.items():
                    if bb[w] != v:
                        fails.append(f'{name} cf q{q}: word {w} {bb[w]:08X} != table {v:08X}'); break
        for q in range(128):
            # packQ on a block built by computeFrames (as on the E4)
            S.call(slot(stock_img, vt, 0x14), [0, eo.BLK, 3, 64, eo.STRUCT])
            sb = block(S)
            N.call(slot(new_img, vt, 0x14), [0, eo.BLK, 3, 64, eo.STRUCT])
            nb = block(N)
            S.mu.mem_write(eo.BLK, struct.pack('>16I', *sb))
            N.mu.mem_write(eo.BLK, struct.pack('>16I', *nb))
            ra, ba = call_keep(S, slot(stock_img, vt, 0x18), [0, eo.BLK, q, eo.STRUCT])
            rb, bb = call_keep(N, slot(new_img, vt, 0x18), [0, eo.BLK, q, eo.STRUCT])
            n += 1
            if hpbp.expected_return(kind, poles, q, ra) != rb:
                fails.append(f'{name} pq q{q}: return {rb:#x} != expected (stock {ra:#x})')
            exp = hpbp.expected_block(kind, poles, q)
            for w in range(16):
                want = exp[w] if w in pole_words else ba[w]
                if bb[w] != want:
                    fails.append(f'{name} pq q{q}: word {w} {bb[w]:08X} != {want:08X}'); break
    # display text
    for name, vt in list((k, v[0]) for k, v in F.items()):
        bad = 0
        for idx in (0, 1, 2):
            for v in range(256):
                outs = []
                for E, img in ((S, stock_img), (N, new_img)):
                    E.mu.mem_write(LBUF, bytes(64)); E.mu.mem_write(VBUF, bytes(64))
                    E.call(slot(img, vt, 0x1C), [0, idx, v, LBUF, VBUF])
                    outs.append((E.cstr(LBUF), E.cstr(VBUF)))
                n += 1
                if outs[0] != outs[1]:
                    bad += 1
                    if bad <= 3:
                        fails.append(f'{name} display idx {idx} v {v}: {outs[1]} != stock {outs[0]}')
        S.mu.mem_write(LBUF, bytes(64)); S.mu.mem_write(VBUF, bytes(64))
        S.call(slot(stock_img, vt, 0x1C), [0, 0, 0, LBUF, VBUF]); lo = S.cstr(VBUF)
        S.call(slot(stock_img, vt, 0x1C), [0, 0, 255, LBUF, VBUF]); hi = S.cstr(VBUF)
        print(f'  {name:10s} display {lo} .. {hi}: {768 - bad}/768 identical to stock')
    # vtables: only the intended slots changed
    changed = [a for a in range(0x6884C, 0x68CA0, 4)
               if stock_img[a - BASE:a + 4 - BASE] != new_img[a - BASE:a + 4 - BASE]]
    want = sorted([vt + 0x14 for vt, *_ in F.values()] + [vt + 0x18 for vt, *_ in F.values()] +
                  [F['BP2'][0] + 0x1C, F['BP4'][0] + 0x1C, F['CBP'][0] + 0x1C])
    n += 1
    if not set(changed) <= set(want):     # a slot may keep its value when the new entry sits at the stock address
        fails.append(f'unexpected vtable slots changed {[hex(a) for a in sorted(set(changed) - set(want))]}')
    print(f'{n} checks; {len(fails)} failures')
    for f in fails[:20]:
        print('  ' + f)
    sys.exit(1 if fails else 0)


def call_keep(E, fn, args):
    """Call without re-initialising the block; return (d0, block)."""
    mu = E.mu
    sp = eo.STACK - 0x200
    mu.mem_write(sp, struct.pack('>' + 'I' * (len(args) + 1), eo.RET, *args))
    mu.reg_write(eo.UC_M68K_REG_A7, sp)
    E.calls = []
    mu.emu_start(fn, eo.RET, count=10000)
    return mu.reg_read(eo.UC_M68K_REG_D0) & 0xffffffff, block(E)


if __name__ == '__main__':
    main()
