#!/usr/bin/env python3
"""Emulator test for the interpolated-resonance + 4 Pole LP+Fuzz build (patches/lpfuzz/lpfuzz.s).

usage: emu_lpfuzz.py BASE.bin PATCHED.bin        (BASE = build/eos471_beta.bin)
1. Registry: the ctor builds 23 objects (stock 21 in stock order, LP+Fuzz, default last), count at +0x25C,
   type table = stock except type 3 -> LP+Fuzz; FUN_00068458 / FUN_000684A0 answer for all types / indexes.
2. Interpolation off (switch bit 0 = 0): every OB-Xa LP2/4/6, HP2/4, BP2/4, Contrary BP computeFrames and
   packQ call (all Q, modes) identical to the base image (block, SETMODE calls, return).
3. Interpolation on: the same calls equal the base result with the pole words replaced by the Python model
   v = a + ((b - a) * f >> shift) per byte (f = Q bits below the table index; last entry: no blend).
4. LP+Fuzz, every switch value: block = patched 4 Pole Low-pass at Q/2 (same switch) with words 0/4 moved to
   4/8, word 5 neutral, drive pole in word 0, cancelling zero (or neutral, bit 4) in word 1; return, SETMODE
   as LP4 at Q/2. Display: "Fuzz" for Q, LP text otherwise. Name, type.
5. Parameter 195 (0..31), descriptors (max 21, 31), image diff limited to the patched places.
"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import emu_p2k as ep     # noqa: E402

B = ep.BASE
N = 0xFFCFFFCF
VT = {'LP2': 0x68878, 'LP4': 0x688A4, 'LP6': 0x688D0, 'HP2': 0x688FC, 'HP4': 0x68928, 'BP2': 0x689D8,
      'BP4': 0x68A04, 'CBP': 0x68A30}
STOCK_VT = [0x68878, 0x688A4, 0x688D0, 0x688FC, 0x68928, 0x689D8, 0x68A04, 0x68A30, 0x68954, 0x68980, 0x689AC,
            0x68A5C, 0x68A88, 0x68AB4, 0x68AE0, 0x68B0C, 0x68B38, 0x687DC, 0x68B64, 0x68B94, 0x68BC4, 0x6884C]
SVF, LADB16 = 0x65FB0, 0x6875C
MGR = 0x10030000
LBUF, VBUF = 0x1000A000, 0x1000A100


def u32(img, a):
    return struct.unpack('>I', img[a - B:a - B + 4])[0]


def lerp_model(img, table, q, shift, last, on):
    i, f = q >> shift, q & ((1 << shift) - 1)
    a = u32(img, table + 4 * i)
    if not on or f == 0 or i >= last:
        return a
    b = u32(img, table + 4 * (i + 1))
    out = 0
    for k in (24, 16, 8, 0):
        x, y = (a >> k) & 0xFF, (b >> k) & 0xFF
        out = (out << 8) | ((x + (((y - x) * f) >> shift)) & 0xFF)
    return out


def hpbp_desc(img, vt):
    cf = u32(img, vt + 0x14)                       # lea desc(pc),a1 ; jmp/bra common_cf
    assert img[cf - B:cf - B + 2] == b'\x43\xfa'
    return cf + 2 + struct.unpack('>h', img[cf + 2 - B:cf + 4 - B])[0]


def expected_words(img, name, q, on):
    """{word index: value} of the table-driven pole words for this filter and Q."""
    if name.startswith('LP'):
        P = int(name[2])
        qq = min(q, 120) if P == 6 else q
        svf = lerp_model(img, SVF, qq, 2, 31, on)
        if P == 2:
            return {0: svf, 4: N, 8: N}
        lada = lerp_model(img, SVF + 128, qq, 2, 31, on)
        ladb = lerp_model(img, LADB16, qq, 3, 15, on)
        return {0: lada, 4: ladb, 8: svf if P == 6 else N}
    d = hpbp_desc(img, VT[name])
    out = {img[d + 8 - B] // 4: lerp_model(img, u32(img, d), q, img[d + 9 - B], 31, on)}
    if img[d + 10 - B] != 0xFF:
        out[img[d + 10 - B] // 4] = lerp_model(img, u32(img, d + 4), q, img[d + 11 - B], img[d + 14 - B], on)
    return out


def cstr(E, a):
    return E.rd(a, 64).split(b'\0')[0].decode(errors='replace')


def blockw(E):
    return list(struct.unpack('>16I', E.rd(ep.CHIP + 0x300, 64)))


def main():
    base_img, new_img = (open(p, 'rb').read() for p in sys.argv[1:3])
    S, P = ep.Emu(base_img), ep.Emu(new_img)
    fails, n = [], 0
    blk = ep.CHIP + 0x300

    # 1. registry
    for E, size in ((S, 0x25C), (P, 0x260)):
        E.mu.mem_write(MGR, bytes([0xA5]) * 0x300); E.heap = 0x10040000; E.mu.mem_write(0x10040000, bytes(0x400))
        E.w32(0x1000262C, MGR)
    rs = S.call(0x67F98, [MGR]); rp = P.call(0x67F98, [MGR])
    sm, pm = S.rd(MGR, 0x300), P.rd(MGR, 0x300)
    sobj = [struct.unpack('>I', sm[0x200 + 4 * i:0x204 + 4 * i])[0] for i in range(22)]
    pobj = [struct.unpack('>I', pm[0x200 + 4 * i:0x204 + 4 * i])[0] for i in range(23)]
    svt = [S.r32(o) for o in sobj]
    pvt = [P.r32(o) for o in pobj]
    lpf_vt = pvt[21]
    n += 1
    if rp != MGR or struct.unpack('>I', pm[0x25C:0x260])[0] != 23 or svt != STOCK_VT or \
            pvt[:21] + pvt[22:] != STOCK_VT or not 0x67F98 <= lpf_vt < 0x683F0:
        fails.append(f'registry list/count: {[hex(v) for v in pvt]} count {pm[0x25C:0x260].hex()}')
    stype = [struct.unpack('>I', sm[4 * t:4 * t + 4])[0] for t in range(128)]
    ptype = [struct.unpack('>I', pm[4 * t:4 * t + 4])[0] for t in range(128)]
    for t in range(128):
        sv, pv = S.r32(stype[t]), P.r32(ptype[t])
        n += 1
        if (t == 3 and pv != lpf_vt) or (t != 3 and pv != sv):
            fails.append(f'type table {t:#x}: {pv:#x} (stock {sv:#x})')
    for t in range(128):
        want = 21 if t == 3 else next((i for i, v in enumerate(pvt) if P.r32(ptype[t]) == v and v != 0x6884C), 22 if t == 0x7F else 0)
        n += 1
        got = P.call(0x68458, [t])
        if t in (0x7F, 3) or P.r32(ptype[t]) != 0x6884C:
            if got != want:
                fails.append(f'type->menu {t:#x}: {got} != {want}')
    for i in range(24):
        n += 1
        got = P.call(0x684A0, [i])
        want = P.call(u32(new_img, pvt[i] + 0x0C), [pobj[i]]) if i < 23 else 0
        if got != want:
            fails.append(f'menu->type {i}: {got:#x} != {want:#x}')
    n += 1
    if P.call(u32(new_img, lpf_vt + 0x0C), [0]) != 3 or cstr(P, P.call(u32(new_img, lpf_vt + 0x10), [0])) != '4 Pole LP+Fuzz':
        fails.append('LP+Fuzz type/name')

    # 2./3. OB-Xa filters, interpolation off and on
    for sw in (0, 1, 0x1E, 0x1F):
        on = bool(sw & 1)
        P.w32(ep.SW, sw)
        for name, vt in VT.items():
            for q in range(128):
                for mode in (0, 3):
                    for pq in (False, True):
                        if pq and mode:
                            continue
                        res = []
                        for E, img in ((S, base_img), (P, new_img)):
                            ep.fill_chip(E, q + mode)
                            fn = u32(img, vt + (0x18 if pq else 0x14))
                            r = E.call(fn, [0, blk, q, 0] if pq else [0, blk, mode, q, 0])
                            res.append((r, blockw(E), list(E.calls)))
                        exp = list(res[0][1])
                        for w, v in expected_words(base_img, name, q, on).items():
                            if not (pq and v == N and name.startswith('LP') and exp[w] != N):
                                exp[w] = v
                        if pq and name.startswith('LP'):         # packQ writes only the words it uses
                            P2 = int(name[2])
                            for w in ((4, 8) if P2 == 2 else (8,) if P2 == 4 else ()):
                                exp[w] = res[0][1][w]
                        n += 1
                        if res[1][0] != res[0][0] or res[1][2] != res[0][2] or res[1][1] != exp:
                            bad = [w for w in range(16) if res[1][1][w] != exp[w]]
                            fails.append(f'{name} sw{sw:#x} q{q} m{mode} {"pq" if pq else "cf"}: words {bad} '
                                         f'{[hex(res[1][1][w]) for w in bad]} != {[hex(exp[w]) for w in bad]}; '
                                         f'ret {res[1][0]:#x}/{res[0][0]:#x}')
    # 4. LP+Fuzz v5 (word 1 = zlerp(word 0, q) with bit 1, word 5 / 8 = word 4 with bit 2 / 3, FH 0x90 with bit 4); was v4: LP4 at Q/2 in words 0/4, low-frame F capped 0xDF, high-frame F capped FH (bits 2-3), zero stages
    #    1/5 (bit 1) at F = FLO + ((0xE0 - FLO) * q >> 7), FLO 0x90 / 0x50 (bit 4), word 8 neutral,
    #    word 9 = base - GOFF[q >> 4], SETMODE 0xC0 after LP4's on computeFrames (bit 1)
    import re
    goff = [u32(new_img, 0x6871C + 4 * i) for i in range(16)]

    def zl(w, q):
        out = 0
        for sh in (24, 16, 8, 0):
            a, t = (w >> sh) & 0xFF, (0xFFE0FFE0 >> sh) & 0xFF
            out = (out << 8) | ((a + int((t - a) * q / 127)) & 0xFF)
        return out

    def cap(w, fh):
        b = list(w.to_bytes(4, 'big'))
        b[1], b[3] = min(b[1], 0xDF), min(b[3], fh)
        return int.from_bytes(bytes(b), 'big')
    for sw in range(32):
        P.w32(ep.SW, sw)
        P.w32(0x10004D7C, 0x00FE00FE)
        for q in list(range(0, 128, 3)) + [127]:
            for mode in (0, 2):
                for pq in (False, True):
                    if pq and mode:
                        continue
                    ep.fill_chip(P, q * 7 + sw)
                    lp4 = u32(new_img, VT['LP4'] + (0x18 if pq else 0x14))
                    r4 = P.call(lp4, [0, blk, q >> 1, 0] if pq else [0, blk, mode, q >> 1, 0])
                    b4, c4 = blockw(P), list(P.calls)
                    ep.fill_chip(P, q * 7 + sw)
                    fn = u32(new_img, lpf_vt + (0x18 if pq else 0x14))
                    r = P.call(fn, [0, blk, q, 0] if pq else [0, blk, mode, q, 0x10009000])
                    got, calls = blockw(P), list(P.calls)
                    exp = list(b4)
                    fh = 0x90 if sw & 16 else 0xDF
                    exp[0], exp[4] = cap(b4[0], fh), cap(b4[4], fh)
                    exp[1] = zl(exp[0], q) if sw & 2 else N
                    exp[5] = exp[4] if sw & 4 else N
                    exp[8] = exp[4] if sw & 8 else N
                    exp[9] = (0x00FE00FE - goff[q >> 4]) & 0xFFFFFFFF
                    want_calls = list(c4)
                    if not pq and sw & 2:
                        want_calls.append((blk, mode, 0xC0, None))
                    n += 1
                    ok_calls = len(calls) == len(want_calls) and all(
                        c[:3] == w[:3] for c, w in zip(calls, want_calls))
                    if got != exp or r != r4 or not ok_calls:
                        bad = [w for w in range(16) if got[w] != exp[w]]
                        fails.append(f'LPF sw{sw} q{q} m{mode} {"pq" if pq else "cf"}: words {bad} '
                                     f'{[hex(got[w]) for w in bad]} != {[hex(exp[w]) for w in bad]} ret {r:#x}/{r4:#x} '
                                     f'calls {calls} / {want_calls}')
    # display
    for idx, v in ((0, 0), (0, 200), (1, 0), (1, 77), (1, 127), (2, 5)):
        outs = []
        for vt in (VT['LP4'], lpf_vt):
            P.mu.mem_write(LBUF, bytes(64)); P.mu.mem_write(VBUF, bytes(64))
            P.call(u32(new_img, vt + 0x1C), [0, idx, v, LBUF, VBUF])
            outs.append((cstr(P, LBUF), cstr(P, VBUF)))
        n += 1
        want = ('Fuzz', str(v)) if idx == 1 else outs[0]
        if outs[1] != want:
            fails.append(f'display idx {idx} v {v}: {outs[1]} != {want}')
    # 5. switch, descriptors, image diff
    get, put = struct.unpack('>II', new_img[ep.DESC195 + 0x1A - B:ep.DESC195 + 0x22 - B])
    for v, want in ((-1, 0), (5, 5), (31, 31), (33, 1), (0, 0)):
        P.call(put, [ep.DESC195, v & 0xffffffff]); n += 1
        if P.r32(ep.SW) != want or P.call(get, [ep.DESC195]) != want:
            fails.append(f'param 195 set {v}')
    n += 1
    if (u32(new_img, 0x5AC48 + 10), u32(new_img, 0x6B58E + 10), u32(new_img, ep.DESC195 + 10),
            new_img[0x5AC48 + 0x15 - B], new_img[0x6B58E + 0x15 - B]) != (21, 21, 31, 21, 21):
        fails.append('descriptor maxima')
    allowed = [(0x18, 0x30), (4, 12), (0x67F98, 0x683F0), (0x6843C, 0x6843E), (0x6841A, 0x6841C), (0x6846E, 0x68470),
               (0x6848E, 0x68490), (0x684B0, 0x684B2), (0x5AC48 + 10, 0x5AC48 + 14), (0x6B58E + 10, 0x6B58E + 14), (0x5AC48 + 0x15, 0x5AC48 + 0x16), (0x6B58E + 0x15, 0x6B58E + 0x16),
               (ep.DESC195 + 10, ep.DESC195 + 14), (ep.DESC195 + 0x1A, ep.DESC195 + 0x22), (0x65E5A, 0x65E60),
               (0x6684E, 0x66854)]
    bad = [i + B for i in range(len(base_img)) if base_img[i] != new_img[i]
           and not any(lo <= i + B < hi or lo <= i < hi for lo, hi in allowed)]
    n += 1
    if bad:
        fails.append(f'unexpected changes at {[hex(a) for a in bad[:8]]} ({len(bad)} bytes)')
    print(f'{n} checks; {len(fails)} failures')
    for f in fails[:25]:
        print('  ' + f)
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
