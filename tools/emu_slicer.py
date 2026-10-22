#!/usr/bin/env python3
"""Emulator test of the Beat Munger "Slice" key (patches/slicer/slicer.s) in EOS 4.71-beta2.

usage: emu_slicer.py BETA2.bin      (reads BETA2.bin.syms.json)
Runs slc_key (through the soft-key slot 0xB71F2) on random Beat Munger slice lists (mono L / R / stereo, sample
start offsets, close and out-of-range onsets, long lists) with every OS routine it calls replaced by a Python
model: sample table, clipboard copy 0xF7050, slot register / unregister, names, memory check, presets, voices,
zones, status line. Checks against an independent model of the slice rules: the copy regions, the new sample
slots and names, the zones (key, original key, sample), the clipboard header put back, Sample Edit's region put
back, call order (voices off before the memory check, on before leaving), callee-saved registers and sp; and the
refusals (busy -> deferred, no slices, no free slots or preset, not enough memory) changing nothing.
"""
import json, os, random, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import emu_p2k as ep        # noqa: E402
import math  # noqa: E402
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_READ   # noqa: E402
from unicorn.m68k_const import *   # noqa: E402,F403

BASE = 0x20000
RGN_S, RGN_E, RGN_C, CURHDR, PLAYER, DEFER = 0x10000E14, 0x10000E18, 0x10000E0E, 0x10005000, 0x100042F4, 0x10003EE8
KEY0, MAXK, MINF, PRE, SNAPW = 36, 92, 1024, 512, 256
CHIPP, CHIPS, MOVE = 0x10003DCC, 0x10070000, 0x2000    # port pointer, port registers, compaction shift (bytes)
HDRS, PRES = 0x10090000, 0x100B0000          # slot headers (slot * 0x5C), preset blocks
CUR, PLY, ARR = 0x10060000, 0x10061000, 0x10062000
SAVED = [UC_M68K_REG_D2, UC_M68K_REG_D3, UC_M68K_REG_D4, UC_M68K_REG_D5, UC_M68K_REG_D6, UC_M68K_REG_D7,
         UC_M68K_REG_A2, UC_M68K_REG_A3, UC_M68K_REG_A4, UC_M68K_REG_A5, UC_M68K_REG_A6]
STUBS = dict(AUD_STOP=0xE405C, AUD_BUSY=0xE4008, BM_EXIT=0xB6080, STATUS=0x1A20D8, SPRINTF=0x1A6EA0,
             SMP_HDR=0x13D32C, SMP_REG=0x13E854, SMP_UNREG=0x13E8C8, SMP_NAME=0x13D48C, MEM_NEED=0x13E3C8,
             MEM_SYNC=0x13DF14, VOICES_OFF=0x23E84, VOICES_ON=0x23F14, COPY_CLIP=0xF7050, PRE_PTR=0x139728,
             PRE_NEW=0x13C52C, PRE_NAME=0x13CD68, PRE_SEL=0x13A484, VOICE_I=0x513F4, ZONE_ADD=0x50E40,
             PORT_ADDR=0x956D4, PORT_END=0x95BA4)


class World:
    """Python model of the OS state the slicer touches."""

    def __init__(self, E, r, case):
        self.E, self.mu, self.log = E, E.mu, []
        mu = self.mu
        self.slots = {}                                     # slot -> header address
        for s in r.sample(range(1, 1000), case['used']):
            self.slots[s] = HDRS + 0x5C * s
        self.clip = case['clip']
        if self.clip:
            self.slots[0] = HDRS
            self.clipbytes = bytes(r.getrandbits(8) for _ in range(0x5C))
            mu.mem_write(HDRS, self.clipbytes)
        self.presets = {p: PRES + 0x1000 * p for p in case['presets']}
        self.mem_ok, self.busy = case['mem_ok'], case['busy']
        self.orig = set(self.slots) - {0}
        self.zones = {}                                     # preset -> zone count
        self.wave = case['wave']
        self.base = list(case['base'])                      # current channel bases (moved by the memory check)
        self.port = None
        self.names = {}

    def sample(self, addr):
        """Sample at a port byte address: the data belongs to the current base, frame = (addr - base) / 2."""
        ch = 0 if self.case_ch & 1 else 1
        return wave_at(self.wave, ((addr & 0x3FFFFFFF) - self.base[ch]) // 2)

    def port_read(self, mu, access, addr, size, value, _):
        if self.port is None:
            raise RuntimeError('sample port read before an address was set')
        mu.mem_write(CHIPS + 0x1C, struct.pack('>h', self.sample(self.port)))
        self.port += 2
        self.reads += 1

    def args(self, n):
        sp = self.mu.reg_read(UC_M68K_REG_A7)
        return struct.unpack(f'>{n}I', self.mu.mem_read(sp + 4, 4 * n))

    def cstr(self, a):
        return bytes(self.mu.mem_read(a, 40)).split(b'\0')[0].decode('latin1')

    def ret(self, v):
        self.mu.reg_write(UC_M68K_REG_D0, v & 0xffffffff)
        for reg in (UC_M68K_REG_D1, UC_M68K_REG_A0, UC_M68K_REG_A1):
            self.mu.reg_write(reg, 0xDEADBEEF)

    def hook(self, mu, a, size, _):
        name = self.at[a]
        E, r32 = self.E, self.E.r32
        if name == 'AUD_BUSY':
            self.ret(1 if self.busy else 0); self.log.append(('busy',)); return
        if name == 'SMP_HDR':
            s = self.args(1)[0]; self.ret(self.slots.get(s, 0)); return
        if name == 'SMP_REG':
            s = self.args(1)[0]
            if s in self.slots:
                self.ret(0)
            else:
                self.slots[s] = HDRS + 0x5C * s; self.ret(self.slots[s])
            self.log.append(('reg', s)); return
        if name == 'SMP_UNREG':
            s = self.args(1)[0]; self.slots.pop(s, None); self.log.append(('unreg', s)); self.ret(0); return
        if name == 'COPY_CLIP':
            st, en, ch = r32(RGN_S), r32(RGN_E), self.E.rd(RGN_C, 1)[0]
            self.log.append(('copy', st, en, ch))
            self.slots[0] = HDRS                            # as 0xF7050: slot 0 (re)made from the region
            mu.mem_write(HDRS, struct.pack('>III', 0xC0C0, st, en) + bytes(0x5C - 12))
            self.ret(0); return
        if name == 'SPRINTF':
            buf, fmt, n = self.args(3)
            assert self.cstr(fmt) == '%02d', self.cstr(fmt)
            mu.mem_write(buf, b'%02d\0' % n); self.ret(2); return
        if name == 'SMP_NAME':
            s, nm, ln = self.args(3)
            assert ln == 0
            self.names[s] = self.cstr(nm); self.log.append(('name', s, self.cstr(nm))); self.ret(0); return
        if name == 'MEM_NEED':
            self.log.append(('mem', self.args(1)[0]))
            if self.mem_ok:                                 # compaction moves the sample data
                self.base = [b + MOVE for b in self.base]
                mu.mem_write(CUR + 0x3C, struct.pack('>II', *self.base))
            self.ret(0 if self.mem_ok else -1); return
        if name == 'PORT_ADDR':
            self.port = self.args(1)[0]; self.log.append(('port', self.port)); self.ret(0); return
        if name == 'PORT_END':
            self.port = None; self.log.append(('port_end',)); self.ret(0); return
        if name == 'PRE_PTR':
            p = self.args(1)[0]; self.ret(self.presets.get(p, 0)); return
        if name == 'PRE_NEW':
            p = self.args(1)[0]
            a = PRES + 0x1000 * p
            mu.mem_write(a, bytes(0x1000))
            self.presets[p] = a; self.zones[p] = 1
            self.log.append(('pnew', p)); self.ret(a); return
        if name == 'VOICE_I':
            pa, i = self.args(2)
            assert i == 0
            self.ret(pa + 0x52); return
        if name == 'ZONE_ADD':
            v, p = self.args(2)
            assert v == self.presets[p] + 0x52, 'zone added to the wrong voice'
            z = v + 0x11C + 22 * self.zones[p]
            self.zones[p] += 1
            self.ret(z); return
        if name == 'PRE_NAME':
            p, nm = self.args(2); self.log.append(('pname', p, self.cstr(nm))); self.ret(0); return
        if name == 'PRE_SEL':
            self.log.append(('psel', self.args(1)[0])); self.ret(0); return
        if name == 'STATUS':
            f, a1, a2 = self.args(3)
            self.log.append(('status', self.cstr(f), a1, a2)); self.ret(0); return
        self.log.append((name.lower(),)); self.ret(0)


def rig(img):
    E = ep.Emu(img)
    E.mu.mem_map(0x10090000, 0x400000)
    W = {}
    at = {a: n for n, a in STUBS.items()}
    for a in at:
        E.mu.mem_write(a, b'\x4e\x75')
    E.mu.hook_add(UC_HOOK_MEM_READ, lambda mu, ac, a, sz, v, u: W['w'].port_read(mu, ac, a, sz, v, u),
                  begin=CHIPS + 0x1C, end=CHIPS + 0x1D)
    for a in at:
        E.mu.hook_add(UC_HOOK_CODE, lambda mu, a, s, u: W['w'].hook(mu, a, s, u), begin=a, end=a)
    return E, W, at


def wave_at(wave, f):
    kind, a, per, ph, seed = wave
    if kind == 'dc':
        return a
    v = a * math.sin(2 * math.pi * f / per + ph) + ((f * 2654435761 + seed) % 97 - 48)
    return max(-32768, min(32767, int(round(v))))


def snap(wave, c, r0):
    f0 = c - SNAPW
    s = [wave_at(wave, f0 + k + r0) for k in range(SNAPW + 1)]
    best = None
    for k in range(1, SNAPW + 1):
        if (s[k - 1] < 0) != (s[k] < 0):
            best = k
    return c if best is None else f0 + best


def expect(case):
    """Independent model: region starts, ends, slots, names, zones."""
    hdrlen, start, chb, ents = case['len'], case['start'], case['ch'], case['ents']
    nch = 2 if chb == 3 else 1
    base = case['base'][0 if chb & 1 else 1] | 0x40000000
    rmax = hdrlen - 5
    if not ents or rmax < 3 * MINF:
        return None
    r0 = start // 2 + 2
    starts = [0]
    for e in ents:
        rr = ((e - base) >> (nch)) - r0 - PRE          # 2*nch bytes per frame: shift 1 (mono) or 2 (stereo)
        if len(starts) >= MAXK:
            break
        if rr >= starts[-1] + MINF and rr <= rmax - MINF:
            starts.append(rr)
    starts = [starts[0]] + [snap(case['wave'], c, r0) for c in starts[1:]]
    k = len(starts)
    regions = [(starts[i], starts[i + 1] - 1 if i + 1 < k else rmax) for i in range(k)]
    total = 0
    for i in range(k):
        ln = (starts[i + 1] if i + 1 < k else rmax + 1) - starts[i]
        t = 2 * ln + 10 + 0x5C
        total += (2 * t if nch == 2 else t) + 10
    return regions, total


def make_case(r):
    chb = r.choice([1, 2, 3])
    frames = r.choice([2000, 50000, 200000, r.randrange(60, 400000)])
    start = 2 * r.choice([0, 0, r.randrange(0, 50)])
    end = start + 2 * frames - 2
    nch = 2 if chb == 3 else 1
    base = [0x00100000 + 2 * r.randrange(0, 1 << 20), 0x00400000 + 2 * r.randrange(0, 1 << 20)]
    eb = base[0 if chb & 1 else 1] | 0x40000000
    n = r.choice([0, 1, 4, 16, r.randrange(1, 200)])
    fr = sorted(r.randrange(0, frames + 40) for _ in range(n))
    if r.random() < 0.3 and fr:
        fr[0] = 0
    if r.random() < 0.2 and len(fr) > 2:
        fr[1] = fr[0] + r.randrange(0, 20)                 # close onsets
    ents = [eb + 2 * nch * f for f in fr]
    return dict(ch=chb, len=frames, start=start, end=end, base=base, ents=ents,
                used=r.choice([0, 5, 300, 990, 999]), clip=r.random() < 0.6,
                presets=r.sample(range(0, 1000), r.choice([0, 3, 999, 1000])),
                mem_ok=r.random() < 0.85, busy=r.random() < 0.05,
                wave=(r.choice(['sine', 'sine', 'sine', 'dc']), r.choice([3000, -2500, 12000, 200]),
                      r.choice([40, 300, 900, 4000, r.randrange(8, 3000)]), r.random() * 6.3, r.randrange(1000)),
                name=r.choice([b'Amen Break 160  ', b'LOOP            ', b'1234567890123456', b'            ']))


def run_case(E, W, at, key, case, seed):
    mu = E.mu
    w = World(E, random.Random(seed), case)
    w.at, w.case_ch, w.reads = at, case['ch'], 0
    W['w'] = w
    mu.mem_write(0x10000000, bytes(0x60000))
    hdr = bytearray(0x5C)
    hdr[0:16] = case['name']
    struct.pack_into('>II', hdr, 0x14, case['start'], case['start'])
    struct.pack_into('>II', hdr, 0x1C, case['end'], case['end'])
    struct.pack_into('>II', hdr, 0x3C, *case['base'])
    hdr[0x3A] = case['ch'] << 1
    mu.mem_write(CUR, bytes(hdr))
    E.w32(CURHDR, CUR)
    E.w32(CHIPP, CHIPS)
    E.w32(PLAYER, PLY)
    E.w32(PLY + 0x23A, len(case['ents']))
    E.w32(PLY + 0x23E, ARR)
    mu.mem_write(ARR, b''.join(struct.pack('>I', e) for e in case['ents']) or b'\0' * 4)
    rs, re_, rc = 0x1234, 0x5678, 3
    E.w32(RGN_S, rs); E.w32(RGN_E, re_); mu.mem_write(RGN_C, bytes([rc]))
    E.w32(DEFER, 0x77777777)
    regs = {k: 0x11110000 + 0x101 * i for i, k in enumerate(SAVED)}
    sp = ep.STACK - 0x400
    mu.mem_write(sp, struct.pack('>I', ep.RET))
    mu.reg_write(UC_M68K_REG_A7, sp)
    for rg, v in regs.items():
        mu.reg_write(rg, v)
    mu.emu_start(key, ep.RET, count=20_000_000)
    out = [mu.reg_read(k) & 0xffffffff for k in SAVED]
    fails = []
    if out != [regs[k] for k in SAVED] or mu.reg_read(UC_M68K_REG_A7) != ep.STACK - 0x400 + 4:
        fails.append('registers / sp not preserved')
    log = w.log
    kinds = [x[0] for x in log]
    ex = expect(case)
    if case['busy']:
        if E.r32(DEFER) != key or kinds != ['aud_stop', 'busy']:
            fails.append(f'busy: {log}')
        return fails, 'busy'
    if E.r32(DEFER) != 0:
        fails.append('DEFER not cleared')
    st = [x for x in log if x[0] == 'status']
    changed = any(k in kinds for k in ('copy', 'reg', 'unreg', 'pnew', 'voices_off'))
    if ex is None:
        if changed or not st or 'no slices' not in st[-1][1]:
            fails.append(f'no-slice case: {log[-3:]}')
        return fails, 'none'
    regions, total = ex
    k = len(regions)
    free = 999 - case['used']
    if free < k or len(case['presets']) == 1000:
        if changed or not st or 'no free' not in st[-1][1]:
            fails.append(f'no-room case: {kinds[-4:]}')
        return fails, 'room'
    pfree = min(set(range(1000)) - set(case['presets']))
    mem = [x for x in log if x[0] == 'mem']
    if mem != [('mem', total)]:
        fails.append(f'memory request {mem} != {total}')
    if kinds.index('voices_off') > kinds.index('mem'):
        fails.append('voices not off before the memory check')
    if not case['mem_ok']:
        if any(x in kinds for x in ('copy', 'reg', 'pnew')) or kinds[-3:] != ['voices_on', 'bm_exit', 'status'] \
                or 'memory' not in st[-1][1]:
            fails.append(f'mem-fail case: {kinds[-5:]}')
        return fails, 'mem'
    ports = [x for x in log if x[0] in ('port', 'port_end')]
    if len(ports) != k or (k > 1 and kinds.index('port_end') > kinds.index('copy')) or (k > 1 and w.reads != (k - 1) * (SNAPW + 1)):
        fails.append(f'sample port use: {len(ports)} calls, {w.reads} reads for {k} slices')
    copies = [x[1:] for x in log if x[0] == 'copy']
    if copies != [(a, b, case['ch']) for a, b in regions]:
        fails.append(f'copy regions differ (first {copies[:3]} vs {regions[:3]})')
    newslots = [x[1] for x in log if x[0] == 'name']
    exp_slots = sorted(set(range(1, 1000)) - w.orig)[:k]
    if newslots != exp_slots:
        fails.append(f'slots {newslots[:5]} != {exp_slots[:5]}')
    stem = case['name'][:12].decode('latin1').rstrip(' \0')
    exp_names = [f'{stem} {i + 1:02d}' if stem else f' {i + 1:02d}' for i in range(k)]
    if [w.names.get(s) for s in newslots] != exp_names:
        fails.append(f'names {[w.names.get(s) for s in newslots][:3]} != {exp_names[:3]}')
    for s in newslots:                                    # each new slot got the clipboard copy's header
        h = E.rd(HDRS + 0x5C * s, 12)
        i = newslots.index(s)
        if struct.unpack('>III', h) != (0xC0C0, regions[i][0], regions[i][1]):
            fails.append(f'slot {s} header not the copy'); break
    if case['clip']:
        if w.slots.get(0) != HDRS or E.rd(HDRS, 0x5C) != w.clipbytes:
            fails.append('clipboard not restored')
    elif 0 in w.slots:
        fails.append('clipboard slot left registered')
    if (E.r32(RGN_S), E.r32(RGN_E), E.rd(RGN_C, 1)[0]) != (rs, re_, rc):
        fails.append('Sample Edit region not restored')
    if ('pnew', pfree) not in log or ('psel', pfree) not in log or ('pname', pfree, stem) not in log:
        fails.append(f'preset {pfree}: {[x for x in log if x[0][0] == "p"]}')
    pa = w.presets.get(pfree, 0)
    if w.zones.get(pfree) != k:
        fails.append(f'zones {w.zones.get(pfree)} != {k}')
    for i in range(k):
        z = E.rd(pa + 0x52 + 0x11C + 22 * i, 22)
        key_ = KEY0 + i
        if (z[0], z[1], z[2], z[3], z[12], struct.unpack('>H', z[8:10])[0]) != (key_, 0, 0, key_, key_, newslots[i]):
            fails.append(f'zone {i}: {z.hex()}'); break
    if kinds[-3:] != ['voices_on', 'bm_exit', 'status'] or st[-1][1:] != ('Sliced: %d samples, preset %d', k, pfree):
        fails.append(f'ending {log[-3:]}')
    return fails, 'ok'


def main():
    img = open(sys.argv[1], 'rb').read()
    syms = json.load(open(sys.argv[1] + '.syms.json'))
    key = struct.unpack('>I', img[0xB71F6 - BASE:0xB71FA - BASE])[0]
    nm = struct.unpack('>I', img[0xB71F2 - BASE:0xB71F6 - BASE])[0]
    assert key == syms['slc_key'] and img[nm - BASE:nm - BASE + 6] == b'Slice\0'
    E, W, at = rig(img)
    r = random.Random(1)
    tally, fails = {}, []
    for t in range(int(sys.argv[2]) if len(sys.argv) > 2 else 600):
        case = make_case(r)
        try:
            f, kind = run_case(E, W, at, key, case, t)
        except Exception as ex:         # noqa: BLE001
            f, kind = [f'exception {ex!r}'], 'exc'
        tally[kind] = tally.get(kind, 0) + 1
        if f:
            fails.append(f'case {t} ({kind}, ch {case["ch"]}, {len(case["ents"])} entries): {f[0]}')
    print(f'{sum(tally.values())} cases {tally}; {len(fails)} failures')
    for f in fails[:12]:
        print('  ' + f)
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
