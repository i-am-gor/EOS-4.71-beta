#!/usr/bin/env python3
"""Emulator test of the loop-shift glide (patches/slpscn/slew.s + shift_t) in EOS 4.71-beta2.

usage: emu_slew.py BASE.bin BETA2.bin      (a no-glide beta2 is built from BASE as the reference)
Runs the real 10 ms tick FUN_0005FE4C(pitch, channel) on random voices (SLoop and SLpScn sums, sample geometry,
stored shift, mono / stereo) in both images, with 0x96028 and the chip update 0x95DD0 stubbed. Target shift T and
stored shift P: |T - P| <= 64 -> results identical to the reference; otherwise stored shift = P +- 64 and every loop
point moved by the same +-64; T == P -> no chip update in either.
"""
import os, random, struct, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import emu_p2k as ep        # noqa: E402
import build_beta2          # noqa: E402
from unicorn import UC_HOOK_CODE   # noqa: E402

LIM = 64
VOICE, HDR, CH = 0x10050000, 0x10051000, 0x10052000
P = VOICE + 0x5A


def s32(v):
    v &= 0xffffffff
    return v - (1 << 32) if v & 0x80000000 else v


def rig(img):
    E = ep.Emu(img)
    calls = []
    for a in (0x96028, 0x95DD0):
        E.mu.mem_write(a, b'\x4e\x75')
    E.mu.hook_add(UC_HOOK_CODE, lambda m, a, s, _: calls.append(a), begin=0x95DD0, end=0x95DD0)
    return E, calls


def state(E, r, prev, sloop, scan, stereo, geo):
    E.mu.mem_write(VOICE, bytes(0x500)); E.mu.mem_write(CH, bytes(0x500))
    E.mu.mem_write(P + 0x10, struct.pack('>h', 1))           # +0x10 > 0: tick exits after the loop update
    E.mu.mem_write(P + 0x1C, struct.pack('>h', 0))           # base
    E.mu.mem_write(P + 0x0A, struct.pack('>h', sloop))       # SLoop sum
    E.mu.mem_write(P - 0x3E, struct.pack('>h', scan))        # SLpScn sum
    E.mu.mem_write(P + 0x2C, struct.pack('>h', prev))        # stored shift
    E.mu.mem_write(P + 0x30, struct.pack('>I', HDR))
    E.mu.mem_write(P + 0x36, bytes([0, 0]))                  # loop moves enabled; +0x37 = 0
    for k, v in geo.items():
        E.mu.mem_write(HDR + k, struct.pack('>I', v))
    E.mu.mem_write(HDR + 0x3A, bytes([0x40]))                # forward loop
    n = CH + 0x4A
    E.mu.mem_write(n + 0x10, struct.pack('>II', 0x40000, 0x40100))
    E.mu.mem_write(n + 0x18, bytes([2 if stereo else 1, 0, 0]))
    E.mu.mem_write(CH + 0x3FE + 0x5A, struct.pack('>II', 0x50000, 0x50100))


def run(E, calls):
    del calls[:]
    E.call(0x5FE4C, [P, CH])
    n = CH + 0x4A
    lp = struct.unpack('>II', E.rd(n + 0x10, 8))
    rp = struct.unpack('>II', E.rd(CH + 0x3FE + 0x5A, 8))
    stored = struct.unpack('>h', E.rd(P + 0x2C, 2))[0]
    return stored, lp, rp, len(calls)


def main():
    base, new = sys.argv[1], sys.argv[2]
    with tempfile.TemporaryDirectory() as td:
        ref_path = os.path.join(td, 'ref.bin')
        build_beta2.build(base, ref_path, slew=False)
        ref_img = open(ref_path, 'rb').read()
    new_img = open(new, 'rb').read()
    R, rc = rig(ref_img)
    N, nc = rig(new_img)
    r = random.Random(7)
    fails, n, big, small = [], 0, 0, 0
    for t in range(4000):
        L = r.choice([256, 64, 1000, r.randrange(2, 3000)])
        frames = r.randrange(2, 40)
        geo = {0x14: 0, 0x24: 4, 0x2C: 4 + 2 * L, 0x1C: 4 + 2 * L * frames - 2}
        prev = r.randrange(-3000, 3000)
        sloop = r.choice([0, r.randrange(-32768, 32768)])
        scan = r.choice([0, r.randrange(-4064, 4065), r.randrange(-32768, 32768)])
        stereo = r.random() < 0.5
        if t % 2:                                           # half the trials: stored shift near the target
            state(R, r, prev, sloop, scan, stereo, geo)
            prev = max(-32768, min(32767, run(R, rc)[0] + r.randrange(-80, 81)))
        state(R, r, prev, sloop, scan, stereo, geo)
        state(N, r, prev, sloop, scan, stereo, geo)
        sr, lr, rr, cr = run(R, rc)
        sn, ln, rn, cn = run(N, nc)
        T = sr                                              # reference stores the target
        d = T - prev
        n += 1
        if T == prev:
            ok = (sn, ln, rn, cn) == (sr, lr, rr, cr)
        elif abs(d) <= LIM:
            small += 1
            ok = (sn, ln, rn, cn) == (sr, lr, rr, cr)
        else:
            big += 1
            dd = LIM if d > 0 else -LIM
            el = (0x40000 + dd, 0x40100 + dd)
            er = (0x50000 + dd, 0x50100 + dd) if stereo else (0x50000, 0x50100)
            ok = sn == prev + dd and ln == el and rn == er and cn == 1
        if not ok:
            fails.append(f'trial {t}: prev {prev} target {T} stereo {stereo}: ref {(sr, lr, rr, cr)} new {(sn, ln, rn, cn)}')
    print(f'{n} checks ({big} clamped, {small} within the limit); {len(fails)} failures')
    for f in fails[:12]:
        print('  ' + f)
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
