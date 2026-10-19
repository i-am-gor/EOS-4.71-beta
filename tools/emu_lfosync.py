#!/usr/bin/env python3
"""Emulator test for the LFO tempo-sync patch (Unicorn, ColdFire V4e core).

usage: emu_lfosync.py BASE.bin PATCHED.bin
1. Rates 0..127: LFO init (FUN_00061A50 as LFO 1, FUN_00061CDC as LFO 2) and ticks (FUN_00061BC0,
   FUN_00061D5C) with random shapes/sync/delay/variation, rate-cord and trigger inputs must leave
   the voice struct and random seed bit-identical to the base image.
2. Rates 128..143: phase must equal ((T - T0) mod P) * 65536 / P for internal clock and for
   external MIDI clock with interpolation; T0 = note-on tick (Key Sync) or 0 (Free Run);
   waveform output = shape table[phase >> 8]; random shape steps once per cycle; a synced note-on
   starts a never-started master clock at the arp tempo (and leaves a running one alone).
3. Front-panel Rate formatter: 0..127 identical to stock, 128..143 division names.
"""
import os, random, struct, sys
from unicorn import Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN
from unicorn.m68k_const import UC_M68K_REG_A7, UC_M68K_REG_A5, UC_CPU_M68K_CFV4E

BASE, RET = 0x20000, 0x1000
RAM, STACK = 0x10000000, 0x10080000
VOICE, PARAMS, BUF = 0x10010000, 0x10011000, 0x10012000
LFO1, LFO2 = VOICE + 0x188, VOICE + 0x1A8
INIT, INIT2, TICK1, TICK2 = 0x61A50, 0x61CDC, 0x61BC0, 0x61D5C
SEED, TICK, TPC, CLKMODE, QCLK, QUS, QMS, NOWMS = (0x1000229C, 0x10000428, 0x10000420, 0x1000042C,
                                                   0x10000440, 0x10000444, 0x10000448, 0x10000450)
CNT, LASTMS, PER, ACC = 0x100003F0, 0x100003F4, 0x100003F8, 0x100003FC
MCLK = 0x2172C                                       # 1 ms master clock routine
PORT0, PORTSZ = 0x102C94EA, 0x256
CALL_F8, CALL_FA, START_STK = 0x135F1E, 0x135F2C, 0x136B10
CLKRATE, CLKUS, PPQ, ARPTEMPO = 0x10000434, 0x1000043C, 0x1000041E, 0x1000719C
UI_RATE = (0x6B5B0, 0x6B65A)
WAVES = 0x6C76E
KTAB = (384, 192, 96, 72, 48, 36, 32, 24, 18, 16, 12, 9, 8, 6, 4, 3)
NAMES = ('4bars', '2bars', '1bar', '1/2.', '1/2', '1/4.', '1/2T', '1/4', '1/8.', '1/4T', '1/8', '1/16.',
         '1/8T', '1/16', '1/16T', '1/32')


class Emu:
    def __init__(self, img):
        self.img = img
        self.mu = mu = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
        mu.ctl_set_cpu_model(UC_CPU_M68K_CFV4E)
        mu.mem_map(0, 0x220000)
        mu.mem_write(BASE, img)
        mu.mem_write(RET, b'\x4e\x71')
        mu.mem_map(RAM, 0x81000)

    def w(self, a, fmt, *v):
        self.mu.mem_write(a, struct.pack('>' + fmt, *v))

    def r(self, a, fmt):
        return struct.unpack('>' + fmt, self.mu.mem_read(a, struct.calcsize('>' + fmt)))

    def call(self, fn, *args):
        sp = STACK - 0x200
        self.w(sp, 'I' * (len(args) + 1), RET, *args)
        self.mu.reg_write(UC_M68K_REG_A7, sp)
        self.mu.emu_start(fn, RET, count=20000)

    def snap(self):
        return bytes(self.mu.mem_read(VOICE, 0x200)) + bytes(self.mu.mem_read(SEED, 4))

    def setup(self, seed, ms, tick=0, mode=0, tpc=20):
        self.mu.mem_write(VOICE, bytes(0x200))
        self.w(SEED, 'I', seed)
        self.w(NOWMS, 'I', ms)
        self.w(TICK, 'I', tick)
        self.w(TPC, 'H', tpc)
        self.w(CLKMODE, 'I', mode)
        self.w(PPQ, 'H', 480)
        self.w(ARPTEMPO, 'I', 120)
        self.w(CLKRATE, 'I', 0)
        self.w(CLKUS, 'I', 0x412)
        self.w(CNT, 'III', 0, ms - 100000 if ms > 100000 else 0, 0)

    def lfo(self, n, rate, shape, delay, var, sync):
        self.w(PARAMS, 'BBBBB', rate, shape, delay, var, sync)
        if n == 1:
            self.call(INIT, LFO1, PARAMS)
        else:
            self.call(INIT2, LFO2, PARAMS)

    def tick(self, n, k):
        self.call(TICK1 if n == 1 else TICK2, LFO1 if n == 1 else LFO2, k)

    def fmt(self, slot, v):
        o = UI_RATE[slot] - BASE + 0x16
        fn = struct.unpack('>I', self.img[o:o + 4])[0]
        self.mu.mem_write(BUF, bytes(32))
        self.call(fn, v, BUF)
        return bytes(self.mu.mem_read(BUF, 32)).split(b'\0')[0].decode('latin1')


def fly(dt, per):
    """Clocks since the last F8 in 1/256 (flyfrac): hold one clock if late, then run on (clock stopped)."""
    x = dt * 256
    if x <= per:
        return (x * 256) // per
    y = x - per
    if y <= per:
        return 256
    return (y // per) * 256 + ((y % per) * 256) // per


def clk_model(st, now):
    """midi_clk2 on (CNT, LASTMS, PER)."""
    cnt, last, per = st
    dt = (now - last) & 0xFFFFFFFF
    inc = 1
    if per and dt < 250:                              # dropped clocks catch up; a stop does not
        r = (dt * 256 + (per >> 1)) // per
        inc = r if r > 2 else 1
    if dt <= 200:
        per = dt * 256 if per == 0 else per + ((dt * 256 - per) >> 3)
    return (cnt + inc) & 0xFFFFFFFF, now, per


def wave(img, shape, phase):
    o = WAVES + (shape & 15) * 0x200 + (phase >> 8) * 2 - BASE
    return struct.unpack('>h', img[o:o + 2])[0]


def main():
    base_img, new_img = (open(p, 'rb').read() for p in sys.argv[1:3])
    a, b = Emu(base_img), Emu(new_img)
    rnd = random.Random(470)
    fails, n = [], 0

    # 1. stock rates are untouched
    for case in range(600):
        lfo = 1 + case % 2
        rate = rnd.randrange(128)
        shape = rnd.choice([0xFF] + list(range(16)))
        delay, var, sync = rnd.choice([0, 0, 5, 40]), rnd.choice([0, 0, 30, 100]), rnd.randrange(2)
        seed, ms = rnd.getrandbits(32), rnd.randrange(1, 10 ** 7)
        for E in (a, b):
            E.setup(seed, ms)
            E.lfo(lfo, rate, shape, delay, var, sync)
        n += 1
        if a.snap() != b.snap():
            fails.append(f'init lfo{lfo} rate {rate} shape {shape} sync {sync}: struct differs')
            continue
        for step in range(40):
            k, rm, trig = rnd.choice([1, 1, 2, 3]), rnd.randrange(-600, 600), rnd.choice([0, 0, 0, 0x1000, -5])
            for E in (a, b):
                p = LFO1 if lfo == 1 else LFO2
                E.w(p, 'h', rm)
                E.w(p + 0x18, 'h', trig)
                E.tick(lfo, k)
            n += 1
            if a.snap() != b.snap():
                fails.append(f'tick lfo{lfo} rate {rate} shape {shape} step {step}: struct differs')
                break

    # 2. synced rates
    def expect(T, T0, d, tpc):
        P = KTAB[d] * tpc
        return ((T - T0) % P) * 65536 // P
    for case in range(800):
        lfo, d = 1 + case % 2, rnd.randrange(16)
        shape = rnd.choice([0xFF] + list(range(16)))
        sync = rnd.randrange(2)                       # 0 = key sync, 1 = free run
        tpc = rnd.choice([20, 20, 20, 4, 40])
        ext = case % 3 == 0
        t0 = rnd.randrange(0, 1 << 24)
        b.setup(rnd.getrandbits(32), rnd.randrange(1, 10 ** 7), tick=t0, mode=1 if ext else 0, tpc=tpc)
        b.w(VOICE + 0x2E, 'I', t0)
        b.lfo(lfo, 128 + d, shape, 0, rnd.choice([0, 50]), sync)
        p = LFO1 if lfo == 1 else LFO2
        marker = b.r(p + 0x10, 'H')[0]
        want = 0x8000 | d | (0x2000 if sync == 0 else 0) | (0x4000 if lfo == 2 else 0)
        n += 1
        if marker != want:
            fails.append(f'init lfo{lfo} div {d} sync {sync}: marker {marker:#x} != {want:#x}')
            continue
        kick_rate = b.r(CLKRATE, 'I')[0]
        n += 1
        if kick_rate != 1000000 // (60000000 // 120 // 480):
            fails.append(f'clock start: ticks/s {kick_rate} after a synced note-on (expected 960)')
        T, last_out = t0, None
        cnt0 = rnd.randrange(0, 1 << 20) if ext else 0
        if ext:                                       # note-on happened with MIDI clock running
            b.w(CNT, 'I', cnt0)
            b.lfo(lfo, 128 + d, shape, 0, 0, sync)
        cnt, ms = cnt0, b.r(NOWMS, 'I')[0]
        for step in range(30):
            T += rnd.randrange(0, 4 * tpc)
            b.w(TICK, 'I', T)
            if ext:
                cnt += rnd.randrange(0, 5)
                per = rnd.choice([0, 12 * 256, 25 * 256 + 77, 125 * 256, 20 * 256 + 213])
                dt = rnd.choice([rnd.randrange(0, 250), rnd.randrange(250, 4000), rnd.randrange(4000, 3600000)])
                mode = rnd.choice([1, 1, 0])          # Clock Source: 1 = External
                b.w(CLKMODE, 'I', mode)
                ms += rnd.randrange(1, 60)
                b.w(CNT, 'I', cnt); b.w(PER, 'I', per); b.w(LASTMS, 'I', (ms - dt) & 0xFFFFFFFF); b.w(NOWMS, 'I', ms)
                el = ((cnt - (cnt0 & 0xFFFF)) & 0xFFFF) if sync == 0 else cnt
                K = KTAB[d]
                if per and (dt < 250 or mode == 1):
                    e_ext = ((el * 256 + fly(dt, per)) % (K * 256)) * 256 // K
                else:                                 # no period yet / clock gone in internal mode
                    e_ext = expect(T, t0 if sync == 0 else 0, d, tpc)
            old = b.r(p + 0x12, 'H')[0]
            prev_out = b.r(p + 2, 'h')[0]
            b.w(p, 'h', rnd.randrange(-600, 600))             # rate cords are ignored
            b.tick(lfo, rnd.choice([1, 2]))
            ph, out, outp = b.r(p + 0x12, 'H')[0], b.r(p + 2, 'h')[0], b.r(p + 4, 'h')[0]
            e = e_ext if ext else expect(T, t0 if sync == 0 else 0, d, tpc)
            n += 1
            if ph != e:
                fails.append(f'lfo{lfo} div {d} sync {sync} ext {ext} T {T}: phase {ph} != {e}' + (f' dt {dt} per {per} mode {mode}' if ext else ''))
                break
            if shape != 0xFF and out != wave(new_img, shape, ph):
                fails.append(f'lfo{lfo} div {d} shape {shape}: output {out} != table {wave(new_img, shape, ph)}')
                break
            if shape == 0xFF and ph >= old and out != prev_out:
                fails.append(f'lfo{lfo} div {d} random: output changed without a phase wrap')
                break
            if (outp - out) & 0xFFFF != 0x800:
                fails.append(f'lfo{lfo} div {d}: unipolar output {outp} != {out}+0x800')
                break

    # 2b. a running clock is left alone
    b.setup(5, 1000)
    b.w(CLKRATE, 'I', 777); b.w(ARPTEMPO, 'I', 90)
    b.lfo(1, 135, 1, 0, 0, 0)
    n += 1
    if b.r(CLKRATE, 'I')[0] != 777 or b.r(ARPTEMPO, 'I')[0] != 90:
        fails.append('clock start: changed an already running clock')

    # 2c. MIDI clock hooks: call sites, counting, period smoothing, Start reset
    for a_, sym_ in ((CALL_F8, 'clk'), (CALL_FA, 'start')):
        n += 1
        tgt = struct.unpack('>I', new_img[a_ - BASE + 2:a_ - BASE + 6])[0]
        if new_img[a_ - BASE:a_ - BASE + 2] != b'\x4e\xb9' or not (0x68BF0 <= tgt < 0x68CA0 or 0x20400 <= tgt < 0x205F0
                                                                   or 0x20080 <= tgt < 0x201C0):
            fails.append(f'{sym_} call site {a_:#x} not patched')
    clk = struct.unpack('>I', new_img[CALL_F8 - BASE + 2:CALL_F8 - BASE + 6])[0]
    start = struct.unpack('>I', new_img[CALL_FA - BASE + 2:CALL_FA - BASE + 6])[0]
    b.setup(1, 50000)
    b.mu.mem_write(START_STK, b'\x4e\x75')            # stub the sequencer's Start handler
    for port, counted in ((2, False), (4, False), (1, True), (0, True)):
        b.w(CNT, 'III', 0, 0, 0)
        b.mu.reg_write(UC_M68K_REG_A5, PORT0 + port * PORTSZ)
        b.call(clk)
        n += 1
        if b.r(CNT, 'I')[0] != int(counted):
            fails.append(f'midi_clk: port {port} counted={b.r(CNT, "I")[0]}, expected {int(counted)}')
    b.mu.reg_write(UC_M68K_REG_A5, PORT0)
    b.w(CNT, 'III', 0, 0, 0)
    ms, st = 50000, (0, 0, 0)
    for i in range(400):
        dt = 25 if i < 100 else 15
        if i in (50, 300):
            dt = 900                                  # a gap: catch-up, period kept
        if i == 200:
            dt = 3 * 3600 * 1000                      # a 3-hour stop
        if i == 120:
            dt = 70                                   # a few dropped clocks
        if 130 <= i < 180:
            dt = (8, 22, 15, 1, 30, 14)[i % 6]          # jitter: no extra counts
        ms += dt
        b.w(NOWMS, 'I', ms)
        b.call(clk)
        st = clk_model(st, ms)
        got = b.r(CNT, 'III')
        n += 1
        if got != st:
            fails.append(f'midi_clk: clock {i} dt {dt}: CNT/LASTMS/PER {got} != {st}')
            break
    b.call(start)
    n += 1
    if b.r(CNT, 'I')[0] != 0:
        fails.append('midi_start: CNT not cleared')
    b.w(NOWMS, 'I', ms + 5000)
    b.call(clk)
    n += 1
    if b.r(CNT, 'I')[0] != 1:
        fails.append(f'midi_start: first clock after Start and a stop counted {b.r(CNT, "I")[0]}, expected 1')

    # 2e. master clock flywheel (FUN_0002172C, 1 ms): internal = stock; external with clock = stock;
    #     external with the clock > 2 periods late = TICK += TPC*256/PER per ms (16.16 accumulator)
    blk = 0x1000041C
    for case in range(300):
        mode = rnd.choice([0, 1, 1])
        tpc = rnd.choice([20, 20, 4, 40])
        per = rnd.choice([0, 25 * 256, 20 * 256 + 213, 41 * 256 + 170, 125 * 256])
        dt = rnd.choice([rnd.randrange(0, 60), rnd.randrange(60, 5000), rnd.randrange(5000, 3600000)])
        ms = rnd.randrange(4000000, 10 ** 7)
        acc0 = rnd.randrange(0, 65536)
        state = bytes(rnd.getrandbits(8) for _ in range(0x40))
        for E in (a, b):
            E.setup(1, ms, tick=rnd.randrange(1 << 20), mode=mode, tpc=tpc)
        for E in (a, b):
            E.mu.mem_write(blk, state[:0x10])                          # flags, counters, accumulators
            E.w(CLKMODE, 'I', mode); E.w(TPC, 'H', tpc); E.w(NOWMS, 'I', ms)
            E.w(PER, 'I', per); E.w(LASTMS, 'I', (ms - dt) & 0xFFFFFFFF); E.w(ACC, 'I', acc0)
            E.w(CLKRATE, 'I', rnd.choice([0, 960, 1600]) if E is a else a.r(CLKRATE, 'I')[0])
        t_a, t_b = a.r(TICK, 'I')[0], b.r(TICK, 'I')[0]
        b.w(TICK, 'I', t_a); b.mu.mem_write(blk, bytes(a.mu.mem_read(blk, 0x40)))
        steps = rnd.randrange(1, 40)
        for _ in range(steps):
            a.call(MCLK); b.call(MCLK)
        n += 1
        if mode == 0:
            if bytes(a.mu.mem_read(blk, 0x40)) != bytes(b.mu.mem_read(blk, 0x40)):
                fails.append(f'master clock internal mode differs from stock (case {case})'); break
            continue
        acc, add = acc0, 0
        if per and dt * 256 > 2 * per:
            inc = (tpc << 24) // per
            for _ in range(steps):
                acc += inc; add += acc >> 16; acc &= 0xFFFF
        elif per:
            acc = 0
        got = (b.r(TICK, 'I')[0] - t_a) & 0xFFFFFFFF
        if got != add or b.r(ACC, 'I')[0] != acc or a.r(TICK, 'I')[0] != t_a:
            fails.append(f'master flywheel tpc {tpc} per {per} dt {dt} x{steps}: +{got} acc {b.r(ACC, "I")[0]}, '
                         f'expected +{add} acc {acc} (stock +{a.r(TICK, "I")[0] - t_a})'); break
    n += 1
    if new_img[0x21732 - BASE:0x21734 - BASE] != b'\x4e\xb9':
        fails.append('master clock hook at 0x21732 not installed')

    # 2f. boot fix: a stock-rate note-on starts a never-started master clock, a running one is left alone
    for rate, pre, want in ((40, 0, 960), (40, 777, 777), (135, 0, 960)):
        b.setup(5, 1000)
        b.w(CLKRATE, 'I', pre); b.w(ARPTEMPO, 'I', 120)
        b.lfo(1, rate, 1, 0, 0, 0)
        n += 1
        if b.r(CLKRATE, 'I')[0] != want:
            fails.append(f'boot clock start: rate {rate} pre {pre}: ticks/s {b.r(CLKRATE, "I")[0]} != {want}')

    # 2g. pan bug fix: final pan shift >> 4 -> >> 5 at note-on and per tick
    for adr, want in ((0x60A50, 'ea85'), (0x60BEA, 'ea81')):
        n += 1
        if new_img[adr - BASE:adr - BASE + 2].hex() != want or base_img[adr - BASE:adr - BASE + 2].hex()[:2] != 'e8':
            fails.append(f'pan shift at {adr:#x}: {new_img[adr - BASE:adr - BASE + 2].hex()} != {want}')

    # 2d. master tick: physical-port F8 -> FUN_000216C0 (external mode adds TPC), internal ports -> nothing
    b.setup(1, 50000, tick=1000, mode=1, tpc=20)
    for port, adv in ((0, 20), (1, 20), (2, 0), (3, 0), (4, 0)):
        t0_ = b.r(TICK, 'I')[0]
        b.mu.reg_write(UC_M68K_REG_A5, PORT0 + port * PORTSZ)
        b.call(clk)
        n += 1
        if b.r(TICK, 'I')[0] - t0_ != adv:
            fails.append(f'master tick after F8 on port {port}: +{b.r(TICK, "I")[0] - t0_}, expected +{adv}')
    n += 1
    if new_img[0x135F24 - BASE:0x135F2A - BASE] != b'\x4e\x71' * 3:
        fails.append('jsr FUN_000216C0 at 0x135F24 not NOPed')

    # 2e. shape 16 = falling saw: rising saw table read backwards, stock and synced rates
    saw = struct.unpack('>256h', new_img[0x6CB6E - BASE:0x6CB6E - BASE + 512])
    for lfo, rate, sync in ((1, 64, 0), (2, 20, 1), (1, 135, 1), (2, 141, 0)):
        b.setup(9, 123456, tick=5000)
        b.w(VOICE + 0x2E, 'I', 5000)
        b.lfo(lfo, rate, 16, 0, 0, sync)
        p = LFO1 if lfo == 1 else LFO2
        n += 1
        if b.r(p + 0x14, 'I')[0] != 0x6CB6E | 0x80000000:
            fails.append(f'shape 16 lfo{lfo}: wave pointer {b.r(p + 0x14, "I")[0]:#x}')
        T = 5000
        for step in range(40):
            T += 37
            b.w(TICK, 'I', T)
            b.tick(lfo, 1)
            ph, out = b.r(p + 0x12, 'H')[0], b.r(p + 2, 'h')[0]
            n += 1
            if out != saw[255 - (ph >> 8)]:
                fails.append(f'shape 16 lfo{lfo} rate {rate}: out {out} != reversed saw {saw[255 - (ph >> 8)]}')
                break
            if b.r(p + 0x14, 'I')[0] != 0x6CB6E | 0x80000000:
                fails.append('shape 16: wave pointer flag lost after a tick'); break
    # falling: over one stock-rate cycle the output steps down except at the wrap
    b.setup(3, 1000); b.lfo(1, 100, 16, 0, 0, 0)
    outs = []
    for _ in range(60):
        b.tick(1, 1); outs.append(b.r(LFO1 + 2, 'h')[0])
    downs = sum(1 for x, y in zip(outs, outs[1:]) if y < x); ups = sum(1 for x, y in zip(outs, outs[1:]) if y > x)
    n += 1
    if downs <= 3 * ups:
        fails.append(f'shape 16 not falling: {downs} down / {ups} up steps')

    # 2f. shape and sync names
    def fmt_at(E, fn, v):
        E.mu.mem_write(BUF, bytes(32)); E.call(fn, v & 0xFFFFFFFF, BUF)
        return bytes(E.mu.mem_read(BUF, 32)).split(b'\0')[0].decode('latin1')
    for E in (a, b):                                   # .data pointer tables live in RAM: load them
        img_ = E.img
        E.mu.mem_write(0x10000400, img_[0x1F86F0 - BASE:0x1FFE80 - BASE])
    SHAPE_FMT, SYNC_FMT = 0x6A8BC, 0x6A90C
    for v in list(range(16)) + [0xFF, -1]:
        n += 1
        if fmt_at(a, SHAPE_FMT, v) != fmt_at(b, SHAPE_FMT, v):
            fails.append(f'shape name {v}: {fmt_at(b, SHAPE_FMT, v)!r} != stock {fmt_at(a, SHAPE_FMT, v)!r}')
    n += 1
    if fmt_at(b, SHAPE_FMT, 16) != 'saw down':
        fails.append(f'shape name 16: {fmt_at(b, SHAPE_FMT, 16)!r}')
    for v in (0, 1):
        n += 1
        if fmt_at(a, SYNC_FMT, v) != fmt_at(b, SYNC_FMT, v):
            fails.append(f'sync name {v}: {fmt_at(b, SYNC_FMT, v)!r} != stock {fmt_at(a, SYNC_FMT, v)!r}')
    print('  shape 2 / 16 names:', repr(fmt_at(b, SHAPE_FMT, 2)), repr(fmt_at(b, SHAPE_FMT, 16)),
          ' sync 0/1:', repr(fmt_at(b, SYNC_FMT, 0)), repr(fmt_at(b, SYNC_FMT, 1)))

    # 3. formatter
    for slot in (0, 1):
        for v in range(144):
            got = b.fmt(slot, v)
            want = a.fmt(slot, v) if v < 128 else NAMES[v - 128]
            n += 1
            if got != want:
                fails.append(f'fmt lfo{slot + 1} {v}: {got!r} != {want!r}')
    print(f'  rate 1 / 64 / 127: {b.fmt(0, 1)!r} {b.fmt(0, 64)!r} {b.fmt(0, 127)!r};  128..143: '
          + ' '.join(b.fmt(0, v) for v in range(128, 144)))
    print(f'{n} checks; {len(fails)} failures')
    for f in fails[:20]:
        print('  ' + f)
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
