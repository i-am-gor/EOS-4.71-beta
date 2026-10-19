#!/usr/bin/env python3
"""Instruction-count cost model of EOS 4.70 hot paths (Unicorn, ColdFire), stock vs patched image.

usage: emu_cost.py IMAGE.bin
  sched   1 ms/2 kHz scheduler FUN_00020ED8 with N voice timers (one bucket) + idle sentinel bucket:
          instructions per call with 0 due items and with K items due in the same call
  cords   per-voice cord processor FUN_0005F89C with A of the 24 cord slots active
The counts are executed instructions (ColdFire 5206e: most take 1-3 cycles, divides ~35).
"""
import struct, sys
from unicorn import Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE
from unicorn.m68k_const import UC_M68K_REG_A7, UC_CPU_M68K_CFV4E

BASE, RET = 0x20000, 0x1000
SCHED, CORDS = 0x20ED8, 0x5F89C
NOWMS = 0x10000450
FLAG, BUCKETS = 0x1030960C, 0x1030961E          # scheduler flag word, first bucket (a2+0x12)
HEAP = 0x10200000
STUB = 0x100F0000                                # task: rts


class Emu:
    def __init__(self, img):
        mu = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
        try:
            mu.ctl_set_cpu_model(UC_CPU_M68K_CFV4E)
        except Exception:
            pass
        mu.mem_map(0, 0x200000 + 0x100000)
        mu.mem_write(BASE, img)
        mu.mem_map(0x10000000, 0x400000)
        mu.mem_map(0x08500000, 0x10000)
        mu.mem_map(0x20000000, 0x1000)
        mu.mem_write(RET, b'\x4e\x71\x4e\x71')
        mu.mem_write(STUB, b'\x4e\x75')
        self.mu, self.n = mu, 0
        mu.hook_add(UC_HOOK_CODE, self._count)

    def _count(self, mu, addr, size, ud):
        self.n += 1

    def w(self, a, fmt, *v):
        self.mu.mem_write(a, struct.pack('>' + fmt, *v))

    def call(self, fn, *args):
        sp = 0x10080000 - 0x400
        self.mu.mem_write(sp, struct.pack('>' + 'I' * (len(args) + 1), RET, *args))
        self.mu.reg_write(UC_M68K_REG_A7, sp)
        self.n = 0
        self.mu.emu_start(fn, RET, count=5_000_000)
        return self.n


def sched_setup(E, nvoice, ndue, now=100000):
    """Bucket 0: nvoice timer items (circular), ndue of them due; bucket 1: idle sentinel (due, task 0)."""
    E.w(FLAG, 'H', 0)
    E.w(NOWMS, 'I', now)
    items = [HEAP + 0x100 * i for i in range(nvoice)]
    dl = HEAP + 0x10000                          # deadline words
    for i, it in enumerate(items):
        E.mu.mem_write(it, bytes(0x50))
        E.w(it, 'I', items[(i + 1) % nvoice])     # next
        E.w(it + 4, 'I', items[i - 1])            # prev
        E.w(it + 8, 'I', STUB)                    # task
        E.w(it + 0xC, 'I', 0)
        E.w(it + 0x1C, 'I', dl + 4 * i)           # -> deadline
        E.w(it + 0x20, 'I', NOWMS)                # -> time source
        E.w(it + 0x24, 'I', 0)
        # due items get a deadline <= now once; the task does not reschedule, so make them due only once:
        E.w(dl + 4 * i, 'I', now if i < ndue else now + 5)
    sent = HEAP + 0x20000
    E.mu.mem_write(sent, bytes(0x50))
    E.w(sent, 'I', sent); E.w(sent + 4, 'I', sent)
    E.w(sent + 8, 'I', 0)                         # task 0 = end of the pass
    E.w(sent + 0x1C, 'I', dl + 0x8000); E.w(dl + 0x8000, 'I', 0)
    E.w(sent + 0x20, 'I', NOWMS)
    b0, b1 = BUCKETS, BUCKETS + 0x40
    E.w(b0, 'III', b1, items[0] if nvoice else 0, 5)
    E.w(b1, 'III', 0, sent, 5)


class Bump:
    """Task stub that pushes the item's deadline 10 ms ahead (like the voice tick)."""


def main():
    img = open(sys.argv[1], 'rb').read()
    E = Emu(img)
    # task that reschedules: deadline += 10  (item+0x1C -> deadline); written as a tiny routine
    # move.l 4(sp),a0 ; movea.l $1c(a0),a0 ; addi.l #10,(a0) ; rts   -- but task gets item[0xC] (arg), so
    # store the item pointer in item+0xC.
    E.mu.mem_write(STUB, bytes.fromhex('206f0004' '2068001c' '2010' '06800000000a' '2080' '4e75'))
    print('scheduler FUN_00020ED8 (one call):')
    print(f'  {"voices":>6s} {"due":>4s} {"instr":>8s} {"per voice tick":>15s}')
    for nv in (0, 16, 32, 64, 128):
        for nd in sorted({0, 1, min(nv, 6), min(nv, 13), nv}):
            sched_setup(E, nv, nd)
            for i in range(nv):
                E.w(HEAP + 0x100 * i + 0xC, 'I', HEAP + 0x100 * i)
            n = E.call(SCHED)
            per = f'{n / nd:.0f}' if nd else ''
            print(f'  {nv:6d} {nd:4d} {n:8d} {per:>15s}')
    print('cord processor FUN_0005F89C (one voice tick):')
    V = HEAP + 0x80000
    for act in (0, 1, 3, 6, 12, 24):
        E.mu.mem_write(V, bytes(0x400))
        for k in range(24):
            e = V + 0x208 + 16 * k
            E.w(e, 'I', V + 0x380)                 # -> source value
            E.w(e + 4, 'I', V + 0x3C0 + 2 * k)     # -> destination accumulator
            E.w(e + 8, 'h', 100 << 5)               # amount
            E.mu.mem_write(e + 12, bytes([1 if k < act else 0]))
        E.w(V + 0x380, 'h', 0x800)
        n = E.call(CORDS, V)
        print(f'  {act:2d} active cords: {n:4d} instructions')


if __name__ == '__main__':
    main()
