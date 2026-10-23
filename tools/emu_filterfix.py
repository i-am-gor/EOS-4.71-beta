#!/usr/bin/env python3
"""Emulator test of the beta2 filter fixes (notes/filter_survey_beta2.md recommendations 1 and 2).

usage: emu_filterfix.py OLD_BETA2.bin NEW_BETA2.bin
For every Q 0..127, in both computeFrames (note-on) and packQ (realtime), with the base gain word set to
0x00FE00FE (and to 0x00C200C2 = Master Headroom 15):
  HP2 / HP4 / Contrary BP: words 0..8 and the return value identical to OLD; word 9 = base - off*0x00010001,
      off = (q*q*K) >> 14 (K 32 / 48 / 16), written by computeFrames and now also by packQ.
  BP2 / BP4, 2/4/6-pole LP, Swept EQ: block and return identical to OLD.
  LP+Fuzz: all words identical to OLD; computeFrames' return now equals packQ's for every Q (and packQ's is
      unchanged).
"""
import struct, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import emu_obxa as emu      # noqa: E402
import eos_filter as ef     # noqa: E402

BASE, GAINBASE = 0x20000, 0x10004D7C
VT = {'2pole': 0x68878, '4pole': 0x688A4, '6pole': 0x688D0, 'hp2': 0x688FC, 'hp4': 0x68928, 'bp2': 0x689D8,
      'bp4': 0x68A04, 'cbp': 0x68A30, 'sweq': 0x68954}
K = {'hp2': 32, 'hp4': 48, 'cbp': 16}


def s32(v):
    return v - (1 << 32) if v & 0x80000000 else v


def methods(img, vt):
    return (struct.unpack('>I', img[vt + 0x14 - BASE:vt + 0x18 - BASE])[0],
            struct.unpack('>I', img[vt + 0x18 - BASE:vt + 0x1C - BASE])[0])


def run(E, img, vt, q, base):
    cf, pq = methods(img, vt)
    E.mu.mem_write(GAINBASE, struct.pack('>I', base))
    r1, b1, _ = E.call(cf, [0, emu.BLK, 0, q], blk_init=ef.NEUTRAL)
    E.mu.mem_write(GAINBASE, struct.pack('>I', base))
    r2, b2, _ = E.call(pq, [0, emu.BLK, q, 0], blk_init=ef.NEUTRAL)
    return s32(r1), list(b1[:10]), s32(r2), list(b2[:10])


def lpfuzz_vt(img):
    i = img.find(bytes.fromhex('887888a488d088fc'))
    return 0x60000 + struct.unpack('>H', img[i + 42:i + 44])[0]


def main():
    old, new = (open(p, 'rb').read() for p in sys.argv[1:3])
    O, N = emu.Emu(old), emu.Emu(new)
    fails, n = [], 0
    for base in (0x00FE00FE, 0x00C200C2):
        for name, vt in VT.items():
            for q in range(128):
                n += 1
                ro, bo, po, qo = run(O, old, vt, q, base)
                rn, bn, pn, qn = run(N, new, vt, q, base)
                if name in K:
                    off = (q * q * K[name]) >> 14
                    want = base - off * 0x00010001
                    ok = (bn[:9] == bo[:9] and qn[:9] == qo[:9] and rn == ro and pn == pn and pn == po
                          and bn[9] == want and qn[9] == want)
                else:
                    ok = (bn, rn, qn, pn) == (bo, ro, qo, po)
                if not ok:
                    fails.append(f'{name} q {q} base {base:#x}: old {ro} {hex(bo[9])}/{po} {hex(qo[9])} '
                                 f'new {rn} {hex(bn[9])}/{pn} {hex(qn[9])}')
        vo, vn = lpfuzz_vt(old), lpfuzz_vt(new)
        for q in range(128):
            n += 1
            ro, bo, po, qo = run(O, old, vo, q, base)
            rn, bn, pn, qn = run(N, new, vn, q, base)
            if not (bn == bo and qn == qo and pn == po and rn == pn):
                fails.append(f'lpfuzz q {q}: cf ret {ro}->{rn}, pq ret {po}->{pn}, words same {bn == bo and qn == qo}')
    print(f'{n} checks; {len(fails)} failures')
    for f in fails[:12]:
        print('  ' + f)
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
