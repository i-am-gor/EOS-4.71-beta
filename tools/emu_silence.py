#!/usr/bin/env python3
"""Emulator test for Sample Edit "Insert Silence" in EOS 4.71-beta2 (patches/silence/silence.s, build_beta2.py).

usage: emu_silence.py BASE.bin BETA2.bin       (BASE = build/eos471_beta.bin)
The LP+Fuzz release is rebuilt from BASE into a temp file (REL); BETA2 must equal REL except for the Insert
Silence places. The routines the new code calls are stubbed (rts + recording hook): memory check 0x13E3C8,
current sample 0x13D2F4, sample length 0x13D578, gap opener 0xF7464, zero fill 0xF7988, Paste exec 0xF79D4,
0x26138, 0xAE9F8, dispatcher 0xFB6F8.
1. Image diff BETA2 vs REL limited to the build_beta2 places (freed string blocks, reserved/user vectors, filter-region
   tail, pea sites, hooks, destination 55, menu slot, Paste exec pointer, name, checksum); vectors 31-47 default; the LP+Fuzz release itself is checked by emu_lpfuzz_rel.py.
2. Menu slot: "Insert Silence" / "Silnc", handler = sil_key, arg 0, level 2, flags 0x02.
3. Exec pointer -> paste_wrap: page pointer != 0 -> Paste (0xF79D4) only, nothing else called; page 0 -> sil_exec.
4. sil_exec over random regions / lengths: N = 4 (fixed), memory check with 4N + 16; on failure returns
   0xFC000002 and touches nothing; else gap(N, pos) then zero(N, pos), pos = start (+1 when start = length - 5),
   returns 0; d2-d7 / a2-a6 preserved.
5. sil_key: operation 3 and page 0 stored; with 0xAE9F8 true calls 0xFB6F8(3, current sample, 0xB32E0, 0);
   false: no dispatch.
"""
import os, random, struct, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import emu_p2k as ep     # noqa: E402
import build_lpfuzz      # noqa: E402
import json   # noqa: E402
from build_beta2 import A, B_, C, V16, V48, U48, REGION_END, MENU, EXEC_PTR, NAME, PEAS, HOOKS, DEST_TABLE, SNAP_AT, SLEW_AT, PM, PM_PB, BM_SLOT, SCN_NAME, PAN_TAB   # noqa: E402
from unicorn.m68k_const import (UC_M68K_REG_D0, UC_M68K_REG_D1, UC_M68K_REG_A0, UC_M68K_REG_A1,   # noqa: E402
                                UC_M68K_REG_A7, UC_M68K_REG_D2, UC_M68K_REG_A6)
from unicorn import UC_HOOK_CODE   # noqa: E402

B = ep.BASE
STUBS = {'memchk': 0x13E3C8, 'cursmp': 0x13D2F4, 'smplen': 0x13D578, 'gap': 0xF7464, 'zero': 0xF7988,
         'paste': 0xF79D4, 'pre': 0x26138, 'ae9f8': 0xAE9F8, 'disp': 0xFB6F8}
REG_START, REG_END, PAGE, OPCODE = 0x10000E14, 0x10000E18, 0x10003EE4, 0x10003ED8
SAVED = list(range(UC_M68K_REG_D2, UC_M68K_REG_D2 + 6)) + list(range(UC_M68K_REG_A0 + 2, UC_M68K_REG_A6 + 1))


def cstr(img, a):
    return img[a - B:a - B + 32].split(b'\0')[0].decode('latin1')


class Rig:
    def __init__(self, img):
        self.E = ep.Emu(img)
        self.log, self.ret = [], {'memchk': 0, 'cursmp': 7, 'smplen': 1000, 'paste': 0x1234, 'ae9f8': 1}
        for name, a in STUBS.items():
            self.E.mu.mem_write(a, b'\x4e\x75')
            self.E.mu.hook_add(UC_HOOK_CODE, self._hook(name), begin=a, end=a)

    def _hook(self, name):
        def h(mu, addr, size, _):
            sp = mu.reg_read(UC_M68K_REG_A7)
            args = struct.unpack('>4I', mu.mem_read(sp + 4, 16))
            self.log.append((name, mu.reg_read(UC_M68K_REG_D0) & 0xffffffff, mu.reg_read(UC_M68K_REG_D1) & 0xffffffff,
                             args))
            v = self.ret.get(name, 0)
            mu.reg_write(UC_M68K_REG_D0, v & 0xffffffff)
            for r in (UC_M68K_REG_D1, UC_M68K_REG_A0, UC_M68K_REG_A1):
                mu.reg_write(r, 0xDEADBEEF)
        return h

    def run(self, fn):
        self.log = []
        regs = {r: 0x5A5A0000 + i for i, r in enumerate(SAVED)}
        d0 = self.E.call(fn, [], regs)
        kept = all((self.E.mu.reg_read(r) & 0xffffffff) == v for r, v in regs.items())
        return d0, kept


def main():
    base_img, new_img = (open(p, 'rb').read() for p in sys.argv[1:3])
    with tempfile.TemporaryDirectory() as td:
        build_lpfuzz.build(sys.argv[1], os.path.join(td, 'rel.bin'), NAME, release=True)
        rel_img = open(os.path.join(td, 'rel.bin'), 'rb').read()
    fails, n = [], 0
    syms = json.load(open(sys.argv[2] + '.syms.json'))
    m = new_img[MENU - B:MENU - B + 18]
    name, short, key, arg = struct.unpack('>4I', m[:16])
    wrap = struct.unpack('>I', new_img[EXEC_PTR - B:EXEC_PTR - B + 4])[0]
    # 1. image diff: only the Insert Silence / Slice places
    allowed = [(0x18, 0x30), (4, 12), A, B_, C, V16, V48, U48, (syms['filter_tail'], REGION_END),
               (MENU, MENU + 18), (EXEC_PTR, EXEC_PTR + 4), (DEST_TABLE + 8 * 55, DEST_TABLE + 8 * 56),
               (SNAP_AT, SNAP_AT + 22), (SLEW_AT, SLEW_AT + 30), PM, (PM_PB, PM_PB + 4),
               (BM_SLOT, BM_SLOT + 8), (SCN_NAME, SCN_NAME + 7), (PAN_TAB + 126, PAN_TAB + 130)]
    allowed += [(a, a + 6) for a in PEAS] + [(a, a + len(h[0]) // 2) for a, h in HOOKS.items()]
    bad = [i + B for i in range(len(rel_img)) if rel_img[i] != new_img[i]
           and not any(lo <= i + B < hi or lo <= i < hi for lo, hi in allowed)]
    n += 1
    if bad:
        fails.append(f'unexpected changes at {[hex(a) for a in bad[:8]]} ({len(bad)} bytes)')
    for site in PEAS:
        n += 1
        if new_img[site - B:site - B + 6] != bytes.fromhex('598f4e714e71'):
            fails.append(f'pea site {site:#x} not subq/nop/nop')
    # vectors 31-47 (NMI, TRAP) back to the default handler
    n += 1
    if any(struct.unpack('>I', new_img[a - B:a - B + 4])[0] != 0x20926 for a in range(0x2027C, 0x202C0, 4)):
        fails.append('vectors 31-47 not default')
    # 2. menu
    n += 1
    if (cstr(new_img, name), cstr(new_img, short), arg, m[16:18]) != ('Insert Silence', 'Silnc', 0, b'\x02\x02') \
            or wrap != syms['paste_wrap'] or key != syms['sil_key']:
        fails.append(f'menu slot {m.hex()} / exec {wrap:#x}')
    R = Rig(new_img)
    # 3. wrapper -> Paste
    for page in (0xB65AC, 1, 0xFFFFFFFF):
        R.E.w32(PAGE, page)
        d0, kept = R.run(wrap)
        n += 1
        if [x[0] for x in R.log] != ['paste'] or d0 != 0x1234:
            fails.append(f'paste_wrap page {page:#x}: {R.log} d0 {d0:#x}')
    # 4. sil_exec through the wrapper
    rnd = random.Random(11)
    cases = [(0, 0, 1000), (0, 7, 1000), (0, 3, 50), (995, 995, 1000), (995, 1002, 1000), (12, 11, 1000)]
    cases += [(s, s + rnd.randrange(0, 64), L) for L in (20, 1000, 1 << 20) for s in
              (rnd.randrange(0, L) for _ in range(30))]
    for (start, end, L) in cases:
        for memok in (True, False):
            R.E.w32(PAGE, 0); R.E.w32(REG_START, start); R.E.w32(REG_END, end)
            R.ret['memchk'] = 0 if memok else -1
            R.ret['smplen'] = L
            d0, kept = R.run(wrap)
            N = 4                                          # fixed: the region end is not used
            if not memok:
                want, wd0 = [('memchk', 4 * N + 16)], 0xFC000002
            else:
                pos = start + 1 if start == L - 5 else start
                want = [('memchk', 4 * N + 16), ('cursmp',), ('smplen', 7), ('gap', N, pos), ('zero', N, pos)]
                wd0 = 0
            got = []
            for nm, r0, r1, args in R.log:
                got.append({'memchk': (nm, args[0]), 'cursmp': (nm,), 'smplen': (nm, args[0]),
                            'gap': (nm, r0, r1), 'zero': (nm, r0, r1)}.get(nm, (nm,)))
            n += 1
            if got != want or d0 != wd0 or not kept:
                fails.append(f'sil_exec start {start} end {end} len {L} mem {memok}: {got} != {want}, d0 {d0:#x}, '
                             f'saved regs {"ok" if kept else "CLOBBERED"}')
    # 5. soft-key handler
    for ok in (1, 0, 0x100):
        R.E.w32(OPCODE, 0x77); R.E.w32(PAGE, 0xB65AC)
        R.ret['ae9f8'] = ok
        d0, kept = R.run(key)
        names = [x[0] for x in R.log]
        disp = [x[3] for x in R.log if x[0] == 'disp']
        ae = [x[3][0] for x in R.log if x[0] == 'ae9f8']
        want_disp = [(3, 7, 0xB32E0, 0)] if ok & 0xFF else []
        n += 1
        if R.E.r32(OPCODE) != 3 or R.E.r32(PAGE) != 0 or names[:2] != ['pre', 'ae9f8'] or ae != [0xB530C] or \
                disp != want_disp or not kept:
            fails.append(f'sil_key ae9f8={ok:#x}: op {R.E.r32(OPCODE)} page {R.E.r32(PAGE):#x} log {R.log}')
    print(f'{n} checks; {len(fails)} failures')
    for f in fails[:20]:
        print('  ' + f)
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
