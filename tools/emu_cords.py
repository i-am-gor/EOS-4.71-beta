#!/usr/bin/env python3
"""Bit-exactness test of the cord processor optimization (patches/cords/cords.s).

usage: emu_cords.py STOCK.bin PATCHED.bin
Random voice blocks and preset cord tables (real source/destination codes, disabled slots, shared
destinations, sources that are other cords' destinations): the stock and patched images run the note-on
setup FUN_0005F810, then repeated cord passes FUN_0005F89C with the sources changing in between. After
every call the whole block must be identical except slot 0 byte 13 (the slot count; never used by stock).
Also: instruction counts per pass, and a corrupt-count check: any count byte must terminate and visit at
most the 24 slots (the count is always written first: FUN_0005F4A8 runs the setup at 0x5F58A before it
queues the voice item at 0x5F5AE).
"""
import random, struct, sys
import os
import emu_cost as ec

AB = os.environ.get('AB_SWITCH')            # A/B build: switch byte value for the new image
STRICT = AB is not None and not int(AB) & 1   # cord patch off: must be byte-identical (no mask)

V, P = 0x10100000, 0x10110000          # amp block (voice + 0x76), preset voice data
SIZE = 0x600
SETUP, CORDS = 0x5F810, 0x5F89C
SRC = [0, 8, 9, 10, 12, 13, 14, 16, 17, 18, 20, 21, 22, 23, 24, 25, 26, 27, 32, 33, 34, 35, 36, 37, 38, 39,
       80, 81, 82, 83, 88, 89, 90, 96, 97, 98, 104, 105, 106, 144, 145, 146, 147, 148, 149]
DST = [0, 8, 9, 10, 11, 12, 16, 17, 18, 19, 20, 21, 22, 23, 32, 33, 34, 35, 36, 40, 41, 42, 47, 48, 49, 50,
       52, 53, 54, 56, 57, 58, 60, 61, 64, 65, 66, 67, 68, 72, 73, 74, 75, 76, 80, 81, 82, 83, 84, 85, 86, 87]


SRC_INT = [c for c in range(1, 256) if not (16 <= c <= 27 or 32 <= c <= 43 or 193 <= c <= 195)]
DST_INT = list(range(1, 192))           # codes that resolve inside the voice block (probed with a zero block)


def mask(b):
    if STRICT:
        return bytes(b)
    b = bytearray(b)
    b[0x208 + 13] = 0
    return bytes(b)


def main():
    stock, new = (open(p, 'rb').read() for p in sys.argv[1:3])
    S, N = ec.Emu(stock), ec.Emu(new)
    rnd = random.Random(4700)
    fails, n, cnt_s, cnt_n, passes, skipped = [], 0, 0, 0, 0, 0
    nact_seen = {}
    for case in range(1500):
        blk = bytes(rnd.getrandbits(8) for _ in range(SIZE))
        tab = bytearray(rnd.getrandbits(8) for _ in range(0x200))
        nact = rnd.choice([0, 1, 3, 6, 10, 16, 24])
        act = set(rnd.sample(range(24), nact))
        internal = case % 2 == 0                 # half the tables: codes that stay inside the voice
        srcs, dsts = (SRC_INT, DST_INT) if internal else (SRC[1:], DST[1:])
        for k in range(24):
            o = 0xBC + 4 * k
            if k in act:
                tab[o], tab[o + 1] = rnd.choice(srcs), rnd.choice(dsts)
                tab[o + 2] = rnd.randrange(256)
            else:
                tab[o], tab[o + 1] = rnd.choice([(0, rnd.choice(DST)), (rnd.choice(SRC), 0)])
        for E in (S, N):
            E.mu.mem_write(V, blk)
            E.mu.mem_write(P, bytes(tab))
        if AB is not None:                            # switch byte in both (stock ignores it)
            S.w(0x100003F0, 'B', int(AB)); N.w(0x100003F0, 'B', int(AB))
        try:
            S.call(SETUP, V, P); N.call(SETUP, V, P)
        except Exception as ex:
            fails.append(f'case {case}: setup crashed ({ex})'); break
        n += 1
        if mask(S.mu.mem_read(V, SIZE)) != mask(N.mu.mem_read(V, SIZE)):
            fails.append(f'case {case}: block differs after setup'); break
        ok = True
        for k in range(24):
            src, dst, _, _, en = struct.unpack('>IIhhB', S.mu.mem_read(V + 0x208 + 16 * k, 13))
            if en and not ((0x10000000 <= src < 0x10400000 or 0x20000 <= src < 0x200000)
                           and 0x10000000 <= dst < 0x10400000):
                ok = False
        if not ok:
            skipped += 1
            continue
        nact_seen[nact] = nact_seen.get(nact, 0) + 1
        for step in range(12):
            # change some source values: random words inside the block (sources point into the voice)
            for _ in range(rnd.randrange(0, 40)):
                o = rnd.randrange(0, 0x200) & ~1
                if 0x208 <= o < 0x388:
                    continue
                w = struct.pack('>h', rnd.randrange(-32768, 32768))
                S.mu.mem_write(V + o, w); N.mu.mem_write(V + o, w)
            S.call(CORDS, V); a = S.n
            N.call(CORDS, V); b = N.n
            cnt_s += a; cnt_n += b; passes += 1
            n += 1
            sb, nb = S.mu.mem_read(V, SIZE), N.mu.mem_read(V, SIZE)
            if mask(sb) != mask(nb) or S.mu.mem_read(0x10000000, 0x10000) != N.mu.mem_read(0x10000000, 0x10000):
                diff = [hex(i) for i in range(SIZE) if mask(sb)[i] != mask(nb)[i]][:8]
                fails.append(f'case {case} step {step} ({nact} active): block differs at {diff}'); break
        if fails:
            break
    # corrupt list: random list bytes, no setup -> must terminate and only process enabled slots in order
    for case in range(200):
        blk = bytearray(rnd.getrandbits(8) for _ in range(SIZE))
        for k in range(24):
            o = 0x208 + 16 * k
            struct.pack_into('>II', blk, o, V + 0x500, V + 0x580 + 2 * k)   # safe pointers
            blk[o + 12] = rnd.choice([0, 0, 1])
        blk[0x208 + 13] = rnd.randrange(0, 256)                # any count byte
        N.mu.mem_write(V, bytes(blk))
        try:
            N.call(CORDS, V)
        except Exception as ex:
            fails.append(f'corrupt count case {case}: {ex}'); break
        n += 1
        if N.n > 2000:
            fails.append(f'corrupt count case {case}: {N.n} instructions (no termination?)')
    print(f'{n} checks; {len(fails)} failures; {skipped} of 1500 random tables skipped (pointer outside the '
          f'emulated RAM); cord pass mean instructions: stock {cnt_s / passes:.0f}, new {cnt_n / passes:.0f}')
    print('  tested tables by active cord count:', dict(sorted(nact_seen.items())))
    for f in fails:
        print('  ' + f)
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
