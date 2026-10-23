#!/usr/bin/env python3
"""Emulator check of the frozen LP+Fuzz release ("EOS 4.71-beta2", build_lpfuzz.py --release) against the
hardware-tested test build ("EOS 4.71 LPFuzz5 T") at switch 15.

usage: emu_lpfuzz_rel.py BASE.bin TEST.bin RELEASE.bin
1. Registry: same 23 objects / order / type table as the test build (LP+Fuzz vtable may sit elsewhere), type 3 name.
2. Every OB-Xa LP2/4/6, HP2/4, BP2/4, Contrary BP and LP+Fuzz computeFrames / packQ call (all Q, modes 0..3):
   release (switch RAM garbage) == test build with switch 15 (block words, SETMODE calls, return value).
3. LP+Fuzz display ("Fuzz" / LP text) equal.
4. Descriptor 195 stock (max 7, no getter/setter); filter-type descriptors max 21.
5. Image diff vs the base limited to the patched places (no descriptor 195).
"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import emu_p2k as ep     # noqa: E402
from emu_lpfuzz import VT, MGR, LBUF, VBUF, u32, blockw, cstr   # noqa: E402

B = ep.BASE


def registry(E):
    E.mu.mem_write(MGR, bytes([0xA5]) * 0x300); E.heap = 0x10040000; E.mu.mem_write(0x10040000, bytes(0x400))
    E.w32(0x1000262C, MGR)
    E.call(0x67F98, [MGR])
    m = E.rd(MGR, 0x300)
    objs = [struct.unpack('>I', m[0x200 + 4 * i:0x204 + 4 * i])[0] for i in range(23)]
    vts = [E.r32(o) for o in objs]
    types = [E.r32(struct.unpack('>I', m[4 * t:4 * t + 4])[0]) for t in range(128)]
    return vts, types, struct.unpack('>I', m[0x25C:0x260])[0]


def main():
    base_img, test_img, rel_img = (open(p, 'rb').read() for p in sys.argv[1:4])
    T, R = ep.Emu(test_img), ep.Emu(rel_img)
    fails, n = [], 0
    blk = ep.CHIP + 0x300
    (tv, tt, tc), (rv, rt, rc) = registry(T), registry(R)
    lt, lr = tv[21], rv[21]
    n += 1
    if tc != 23 or rc != 23 or tv[:21] + tv[22:] != rv[:21] + rv[22:] or \
            [lr if v == lt else v for v in tt] != rt:
        fails.append('registry differs')
    n += 1
    if R.call(u32(rel_img, lr + 0x0C), [0]) != 3 or cstr(R, R.call(u32(rel_img, lr + 0x10), [0])) != '4 Pole LP+Fuzz':
        fails.append('LP+Fuzz type/name')
    T.w32(ep.SW, 15)
    for garbage in (0, 0xFFFFFFFF, 0x1E):
        R.w32(ep.SW, garbage)
        for name, (vt_t, vt_r) in list({k: (v, v) for k, v in VT.items()}.items()) + [('LPF', (lt, lr))]:
            for q in range(128):
                for mode in range(4):
                    for pq in (False, True):
                        if pq and mode:
                            continue
                        res = []
                        for E, img, vt in ((T, test_img, vt_t), (R, rel_img, vt_r)):
                            E.w32(0x10004D7C, 0x00FE00FE)
                            ep.fill_chip(E, q * 3 + mode)
                            fn = u32(img, vt + (0x18 if pq else 0x14))
                            r = E.call(fn, [0, blk, q, 0] if pq else [0, blk, mode, q, 0x10009000])
                            res.append((r, blockw(E), [c[:3] for c in E.calls]))
                        n += 1
                        if res[0] != res[1]:
                            fails.append(f'{name} q{q} m{mode} {"pq" if pq else "cf"} (SW {garbage:#x})')
    for idx, v in ((0, 0), (0, 200), (1, 0), (1, 77), (1, 127), (2, 5)):
        outs = []
        for E, img, vt in ((T, test_img, lt), (R, rel_img, lr)):
            E.mu.mem_write(LBUF, bytes(64)); E.mu.mem_write(VBUF, bytes(64))
            E.call(u32(img, vt + 0x1C), [0, idx, v, LBUF, VBUF])
            outs.append((cstr(E, LBUF), cstr(E, VBUF)))
        n += 1
        if outs[0] != outs[1]:
            fails.append(f'display idx {idx} v {v}: {outs[1]} != {outs[0]}')
    n += 1
    if rel_img[ep.DESC195 - B:ep.DESC195 - B + 0x22] != base_img[ep.DESC195 - B:ep.DESC195 - B + 0x22]:
        fails.append('descriptor 195 not stock')
    n += 1
    if (u32(rel_img, 0x5AC48 + 10), u32(rel_img, 0x6B58E + 10), rel_img[0x5AC48 + 0x15 - B], rel_img[0x6B58E + 0x15 - B]) != (21, 21, 21, 21):
        fails.append('filter-type descriptor maxima')
    allowed = [(0x18, 0x30), (4, 12), (0x67F98, 0x683F0), (0x6843C, 0x6843E), (0x6841A, 0x6841C), (0x6846E, 0x68470),
               (0x6848E, 0x68490), (0x684B0, 0x684B2), (0x5AC48 + 10, 0x5AC48 + 14), (0x6B58E + 10, 0x6B58E + 14), (0x5AC48 + 0x15, 0x5AC48 + 0x16), (0x6B58E + 0x15, 0x6B58E + 0x16),
               (0x65E5A, 0x65E60), (0x6684E, 0x66854)]
    bad = [i + B for i in range(len(base_img)) if base_img[i] != rel_img[i]
           and not any(lo <= i + B < hi or lo <= i < hi for lo, hi in allowed)]
    n += 1
    if bad:
        fails.append(f'unexpected changes at {[hex(a) for a in bad[:8]]} ({len(bad)} bytes)')
    print(f'{n} checks; {len(fails)} failures')
    import collections
    print(dict(collections.Counter(f.split(" ")[0] for f in fails)))
    for f in fails[:25]:
        print('  ' + f)
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
