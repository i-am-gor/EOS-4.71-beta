#!/usr/bin/env python3
"""Exactness test of the RFX amp-path skip (patches/rfx/rfx.s): stock vs patched image.

usage: emu_rfx.py STOCK_LAYER.bin PATCHED.bin
Real code paths: note-on amp init FUN_000609D8 and amp tick FUN_00060B7C (RFX flag 0x10004D88 = 1), mono and
stereo voices, random inputs changing between ticks (envelope/vol inputs, pan, voice sends, Multimode channel
sends, mode, channel flag, offset 0x10004D84) with stretches where nothing changes.
After every call: RAM (voice, RFX blocks, channel, globals) identical except the patch's offset caches
(voice + 0x28C / 0x29C); chip register pages identical; every chip write that only stock made rewrote the
value already there; and every chip volume-byte write (+0x71) stock makes is also made (stock rewrites it
on every tick, and the hardware null test showed it must be kept). Reports how many amp-tick chip-writer
calls were reduced to the volume write.
"""
import random, struct, sys
from unicorn import UC_HOOK_MEM_WRITE, UC_HOOK_CODE
import os
import emu_cost as ec

AB = os.environ.get('AB_SWITCH')
STRICT = AB is not None and not int(AB) & 2   # RFX skip off: no cache bytes may differ

V = 0x10120000; V2 = V + 0x3FE; AMP = V + 0x76 + 0x94
BLK, BLK2, CHAN = 0x10130000, 0x10130100, 0x10150000
CHIP = 0x10140000                                     # chip pages: CHIP .. CHIP + 0x1000
GLOB = [(0x10004D70, 0x30), (0x10004F00, 0x30), (0x10002280, 0x40), (0x100007F0, 0x10)]
CACHES = (0x28C, 0x28D, 0x29C, 0x29D)


class Rig:
    def __init__(self, img):
        self.E = ec.Emu(img)
        self.writes = []
        self.E.mu.hook_add(UC_HOOK_MEM_WRITE, self._w, begin=CHIP, end=CHIP + 0x1000)
        self.calls = 0
        self.E.mu.hook_add(UC_HOOK_CODE, self._c, begin=0x10E280, end=0x10E281)

    def _w(self, mu, access, addr, size, value, ud):
        old = int.from_bytes(mu.mem_read(addr, size), 'big')
        self.writes.append((addr, size, value & ((1 << (8 * size)) - 1), old))

    def _c(self, mu, addr, size, ud):
        self.calls += 1

    def ram(self):
        r = bytearray(self.E.mu.mem_read(V, 0x800))
        for c in ([] if STRICT else CACHES):
            r[c] = 0
        r += self.E.mu.mem_read(BLK, 0x200) + self.E.mu.mem_read(CHAN, 0x100)
        for a, n in GLOB:
            r += self.E.mu.mem_read(a, n)
        return bytes(r)


def main():
    stock, new = (open(p, 'rb').read() for p in sys.argv[1:3])
    S, N = Rig(stock), Rig(new)
    rnd = random.Random(470)
    fails, n, ticks, skipped_calls, stock_calls = [], 0, 0, 0, 0
    for case in range(300):
        stereo = case % 3 == 0
        vb = bytearray(rnd.getrandbits(8) for _ in range(0x800))
        struct.pack_into('>I', vb, 0x1A, 2 if stereo else 1)
        struct.pack_into('>I', vb, 0x3FE + 0x1A, 8)
        struct.pack_into('>I', vb, 0x72, BLK); struct.pack_into('>I', vb, 0x3FE + 0x72, BLK2)
        struct.pack_into('>I', vb, 0xA, CHAN); struct.pack_into('>I', vb, 0x42, 0)
        struct.pack_into('>I', vb, 0x26, CHIP + 0x800); struct.pack_into('>I', vb, 0x2E, CHIP + 0xA00)
        vb[0x109] = rnd.choice([0, 1, 2, 3]); vb[0x108] = rnd.choice([0, 0x80])
        vb[0x15C + 0x20] = rnd.choice([0, 1, 2])
        blk = bytearray(rnd.getrandbits(8) for _ in range(0x200))
        for b in (0, 0x100):
            struct.pack_into('>II', blk, b + 0x36, CHIP + 0x100 + b, CHIP + 0x400 + b)
        chan = bytes(rnd.getrandbits(8) for _ in range(0x100))
        g = {a: bytes(rnd.getrandbits(8) for _ in range(n_)) for a, n_ in GLOB}
        for R in (S, N):
            E = R.E
            E.mu.mem_write(V, bytes(vb)); E.mu.mem_write(BLK, bytes(blk)); E.mu.mem_write(CHAN, chan)
            E.mu.mem_write(CHIP, bytes(0x1000))
            for a, d in g.items():
                E.mu.mem_write(a, d)
            E.w(0x10004D88, 'I', 1)
            if AB is not None and R is N:
                E.w(0x100003F0, 'B', int(AB))
            E.w(0x10004F04, 'B', rnd.choice([0, 2]) if R is S else S.E.mu.mem_read(0x10004F04, 1)[0])
        steps = [('noteon', None)] + [('tick', None)] * 40
        for k, (kind, _) in enumerate(steps):
            if k and rnd.random() < 0.45:              # change one input (same in both)
                what = rnd.choice(['env', 'vol', 'pan', 'send', 'chansend', 'mode', 'chflag', 'offset', 'multi'])
                if what == 'env':
                    a, v = V + 0x15C + 8, struct.pack('>h', rnd.randrange(-0x800, 0x1000))
                elif what == 'vol':
                    a, v = AMP + rnd.choice([0, 4, 0xE]), struct.pack('>h', rnd.randrange(-0x800, 0x800))
                elif what == 'pan':
                    a, v = AMP + rnd.choice([2, 6]), struct.pack('>h', rnd.randrange(-0x1000, 0x1000))
                elif what == 'send':
                    a, v = V + 0x26E + 2 * rnd.randrange(8), struct.pack('>h', rnd.randrange(-0x400, 0x1400))
                elif what == 'chansend':
                    a, v = CHAN + 0x50 + rnd.randrange(8), bytes([rnd.getrandbits(8)])
                elif what == 'mode':
                    a, v = 0x10004F04, bytes([rnd.choice([0, 2])])
                elif what == 'chflag':
                    a, v = CHAN + 2, bytes([rnd.choice([0xFE, 0x00, 0x05])])
                elif what == 'multi':
                    a, v = 0x1000228C, bytes([rnd.choice([0, 0, 1])])
                else:
                    a, v = 0x10004D84, struct.pack('>I', rnd.choice([0, 0, 0x20, 0x1000, rnd.getrandbits(32)]))
                for R in (S, N):
                    R.E.mu.mem_write(a, v)
            for R in (S, N):
                R.writes, R.calls = [], 0
                try:
                    if kind == 'noteon':
                        R.E.call(0x609D8, AMP, V)
                    else:
                        R.E.call(0x60B7C, AMP, V)
                except Exception as ex:
                    fails.append(f'case {case} step {k} {"stock" if R is S else "new"}: {ex}')
            if fails:
                break
            n += 1
            if kind == 'tick':
                ticks += 1; stock_calls += S.calls; skipped_calls += S.calls - N.calls
            if S.ram() != N.ram():
                d = [i for i, (x, y) in enumerate(zip(S.ram(), N.ram())) if x != y][:6]
                fails.append(f'case {case} step {k} ({kind}): RAM differs at {d}'); break
            if bytes(S.E.mu.mem_read(CHIP, 0x1000)) != bytes(N.E.mu.mem_read(CHIP, 0x1000)):
                fails.append(f'case {case} step {k} ({kind}): chip state differs'); break
            sw, nw = list(S.writes), list(N.writes)
            for w in nw:
                if w in sw:
                    sw.remove(w)
            extra = [w for w in sw if w[2] != w[3]]
            volw = lambda ws: sorted(w for w in ws if (w[0] - CHIP) % 0x100 == 0x71 and w[0] < CHIP + 0x800)
            if volw(S.writes) != volw(N.writes):
                fails.append(f'case {case} step {k}: chip volume-byte writes differ: stock {volw(S.writes)} '
                             f'new {volw(N.writes)}'); break
            if extra or (len(nw) > len(S.writes)):
                fails.append(f'case {case} step {k}: stock-only writes that changed a value: {extra[:3]}'); break
        if fails:
            break
    print(f'{n} calls compared; {len(fails)} failures; amp ticks {ticks}: chip writer called {stock_calls} '
          f'times in stock, skipped {skipped_calls} ({100 * skipped_calls / max(1, stock_calls):.0f} %)')
    for f in fails:
        print('  ' + f)
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
