#!/usr/bin/env python3
"""Emulator test for the "'Slice" cord destination in EOS 4.71-beta2 (patches/slice/slice.s, build_beta2.py).

usage: emu_slice.py BETA2.bin      (symbols from BETA2.bin.syms.json written by build_beta2.py)
1. Destination 55 = "'Slice", accumulator 0x1C, flags 0x0100; hooks: 0x61B9C jmp sl_mode, 0x5FBA6/0x5FECA jsr shift_w,
   0x5FD2C jmp slice_exit + nop.
2. sl_mode: 24 random cords; voice+0x1E = 1 iff an LFO-1 call has a cord with dst 55, src != 0, amt != 0 (LFO 2:
   untouched); always continues into lfo_init (stubbed) with the stack unchanged.
3. shift_w: Slice voice -> stock shift (SLoop sum >> 5 + base) without calling sl_shift; others -> sl_shift (stubbed).
4. slice_exit: random headers / sums / SStart offsets, mono and stereo, one-shot and looped, reverse flag, zero
   loop length: note structs equal a Python model; d2-d5 preserved; d6/d7/a2/a4/a5 and the stack restored as the
   stock epilogue does; non-Slice voices: unchanged, except with a non-zero SLpScn sum a forward looped channel
   starts at its loop start (scan_start).
"""
import json, random, struct, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import emu_p2k as ep     # noqa: E402
from unicorn import UC_HOOK_CODE   # noqa: E402
from unicorn.m68k_const import (UC_M68K_REG_A1, UC_M68K_REG_D1, UC_M68K_REG_D0, UC_M68K_REG_D2, UC_M68K_REG_D6, UC_M68K_REG_D7,   # noqa: E402
                                UC_M68K_REG_A0, UC_M68K_REG_A2, UC_M68K_REG_A3, UC_M68K_REG_A4,
                                UC_M68K_REG_A5, UC_M68K_REG_A7)

B = ep.BASE
VOICE, HDR, CH, LFOP = 0x10050000, 0x10051000, 0x10052000, 0x10053000
SMPBASE = 0x100071BC
LFO_INIT, SL_SHIFT, LFO2_RET = 0x204D8, 0x20080, 0x61CF0
FULL = 4032


def s32(v):
    v &= 0xffffffff
    return v - (1 << 32) if v & 0x80000000 else v


def tdiv(a, b):
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def model_one(note, hdr, side, ssum, base, root):
    """note: dict 12/16/20/0x19 -> values; hdr: dict of header longs. Returns the new note dict."""
    n = dict(note)
    if n[0x19]:
        return n
    o = 4 * side
    bb = hdr[0x3C + o] + base
    LS, LE = (hdr[0x24 + o] + bb) >> 1, (hdr[0x2C + o] + bb) >> 1
    L = LE - LS
    if L <= 0:
        return n
    S, E = (hdr[0x14 + o] + bb) >> 1, (hdr[0x1C + o] + bb) >> 1
    p = ssum * 127
    p += FULL // 2 if p >= 0 else -(FULL // 2)
    j = tdiv(p, FULL) - root
    Fa, Fb = (E - LE + 1) // L, (LS - S) // L
    j = max(-Fb, min(Fa, j))
    shift = j * L
    start = LS + shift
    off = n[12] - S
    off = max(0, off)
    if off >= L:
        off = L - 1
    n[12] = start + off
    if n[16] == 8:
        n[20] = LE + shift - 1
    else:
        n[16] += shift
        n[20] += shift
    return n


def main():
    img = open(sys.argv[1], 'rb').read()
    syms = json.load(open(sys.argv[1] + '.syms.json'))
    E = ep.Emu(img)
    mu = E.mu
    mu.mem_map(0x10050000, 0x10000) if False else None
    stub = {}
    for a, nm in ((LFO_INIT, 'lfo_init'), (SL_SHIFT, 'sl_shift')):
        mu.mem_write(a, b'\x4e\x75')
        def h(m, addr, size, _, nm=nm):
            stub.setdefault(nm, []).append(m.reg_read(UC_M68K_REG_A7))
        mu.hook_add(UC_HOOK_CODE, h, begin=a, end=a)
    fails, n = [], 0
    u32 = lambda a: struct.unpack('>I', img[a - B:a - B + 4])[0]
    # 1. table and hooks
    T = 0x6344C + 8 * 55
    nm_, off_, fl_ = struct.unpack('>IHH', img[T - B:T - B + 8])
    n += 1
    if img[nm_ - B:nm_ - B + 7] != b"'Slice\0" or off_ != 0x1C or fl_ != 0x0100:
        fails.append(f'destination 55: {nm_:#x} {off_:#x} {fl_:#x}')
    hooks = {0x61B9C: b'\x4e\xf9' + struct.pack('>I', syms['sl_mode']),
             0x5FBA6: b'\x4e\xb9' + struct.pack('>I', syms['shift_w']),
             0x5FECA: b'\x4e\xb9' + struct.pack('>I', syms['shift_t']),
             0x5FD2C: b'\x4e\xf9' + struct.pack('>I', syms['slice_exit']) + b'\x4e\x71',
             0x5F914: b'\x4e\xb9' + struct.pack('>I', syms['pit_hook']) + b'\x4e\x71'}
    for a, want in hooks.items():
        n += 1
        if img[a - B:a - B + len(want)] != want:
            fails.append(f'hook {a:#x}: {img[a - B:a - B + len(want)].hex()} != {want.hex()}')
    r = random.Random(3)
    # 2. sl_mode
    lfo1 = VOICE + 0x188
    for trial in range(400):
        cords = bytearray()
        want = False
        for k in range(24):
            src, dst, amt = r.choice([0, r.randrange(256)]), r.choice([55, 58, 53, r.randrange(80)]), \
                r.choice([0, r.randrange(256)])
            if trial % 7 == 0:
                dst = 1
            cords += bytes([src, dst, amt, r.randrange(256)])
            want |= dst == 55 and src != 0 and amt != 0
        lfo2 = trial % 5 == 0
        mu.mem_write(LFOP + 0x26, bytes(cords))
        E.w32(VOICE + 0x1C, 0xABCD0033)                    # 0x1C sum, 0x1E flag = 0, 0x1F original key 0x33
        stub.clear()
        args = [0, 0, 0, 0, 0, LFO2_RET if lfo2 else 0x61CE0]
        E.call(syms['sl_mode'], args, {UC_M68K_REG_A3: LFOP, UC_M68K_REG_A5: lfo1})
        flag = struct.unpack('>H', E.rd(VOICE + 0x1E, 2))[0]
        exp = (0x100 if (want and not lfo2) else 0) | 0x33
        n += 1
        if flag != exp or len(stub.get('lfo_init', [])) != 1 or E.rd(VOICE + 0x1C, 2) != b'\xab\xcd':
            fails.append(f'sl_mode trial {trial}: flag {flag} want {exp} lfo_init {stub.get("lfo_init")}')
    # 3. shift_w
    P = VOICE + 0x5A
    for trial in range(200):
        flag = r.choice([0, 1])
        base, sl = r.randrange(-3000, 3000), r.randrange(-32768, 32768)
        mu.mem_write(P - 0x3C, struct.pack('>BB', flag, r.randrange(256)))
        mu.mem_write(P + 0x1C, struct.pack('>h', base))
        mu.mem_write(P + 0x0A, struct.pack('>h', sl))
        stub.clear()
        E.call(syms['shift_w'], [], {UC_M68K_REG_A5: P})
        d7 = s32(mu.reg_read(UC_M68K_REG_D7))
        n += 1
        if flag:
            if d7 != base + (sl >> 5) or stub.get('sl_shift'):
                fails.append(f'shift_w slice: d7 {d7} != {base + (sl >> 5)} {stub}')
        elif len(stub.get('sl_shift', [])) != 1:
            fails.append(f'shift_w stock: sl_shift not called {stub}')
    # 4. slice_exit
    RET = ep.RET
    for trial in range(3000):
        stereo = r.random() < 0.5
        flag = 0 if trial % 9 == 0 else 1
        base = r.randrange(0, 1 << 22) & ~1
        mu.mem_write(SMPBASE, struct.pack('>I', base))
        hdr = {}
        for side in (0, 1):
            o = 4 * side
            blk = r.randrange(0, 1 << 22) & ~1
            nfr = r.choice([r.randrange(40, 400), r.randrange(400, 200000)])
            S = 0
            Eb = 2 * (nfr - 1)
            if trial % 11 == 0:                              # tiny slices on long samples: F > 65535 (cap)
                nfr, L = r.randrange(140000, 300000), r.choice([1, 2])
            else:
                L = r.choice([0, r.randrange(1, max(2, nfr // 3))]) if trial % 13 == 0 else r.randrange(1, max(2, nfr // 2))
            Eb = 2 * (nfr - 1)
            ls = r.randrange(0, max(1, nfr - L))
            hdr[0x14 + o], hdr[0x1C + o] = S, Eb
            hdr[0x24 + o], hdr[0x2C + o] = 2 * ls, 2 * (ls + L)
            hdr[0x3C + o] = blk
        for k, v in hdr.items():
            mu.mem_write(HDR + k, struct.pack('>I', v))
        ssum = r.choice([0, r.randrange(-4032, 4033), r.randrange(-32768, 32768), 4032, -4032, 32 * r.randrange(128)])
        root = r.choice([0, 36, 60, r.randrange(128), r.randrange(256)])
        mu.mem_write(P - 0x3E, struct.pack('>hBB', ssum, flag, root))
        mu.mem_write(P + 0x30, struct.pack('>I', HDR))
        notes, addrs = [], [CH + 0x4A, CH + 0x448]
        for side in (0, 1):
            o = 4 * side
            bb = hdr[0x3C + o] + base
            looped = r.random() < 0.5
            note = {12: ((hdr[0x14 + o] + bb) >> 1) + r.choice([0, r.randrange(0, 3000), -1]),
                    16: (((hdr[0x24 + o] + bb) >> 1) if looped else 8),
                    20: (((hdr[0x2C + o] + bb) >> 1) - 1 if looped else (hdr[0x1C + o] + bb) >> 1),
                    0x19: 1 if r.random() < 0.1 else 0}
            notes.append(note)
            a = addrs[side]
            mu.mem_write(a, bytes(0x30))
            mu.mem_write(a + 12, struct.pack('>III', note[12] & 0xffffffff, note[16] & 0xffffffff, note[20] & 0xffffffff))
            mu.mem_write(a + 0x18, bytes([2 if stereo else 0, note[0x19]]))
        # stack: saved d6, d7, a2, a4, a5 then the caller's return address
        sp = ep.STACK - 0x400
        saved = [0x11111111, 0x22222222, CH, CH + 0x4A, P]
        mu.mem_write(sp, struct.pack('>6I', *saved, RET))
        mu.reg_write(UC_M68K_REG_A7, sp)
        for i in range(4):
            mu.reg_write(UC_M68K_REG_D2 + i, 0x5A5A0000 + i)
        mu.reg_write(UC_M68K_REG_A4, CH + 0x4A); mu.reg_write(UC_M68K_REG_A5, P); mu.reg_write(UC_M68K_REG_A2, CH)
        mu.reg_write(UC_M68K_REG_D6, 0xDEAD); mu.reg_write(UC_M68K_REG_D7, 0xBEEF)
        mu.emu_start(syms['slice_exit'], RET, count=20000)
        got = []
        for side in (0, 1):
            v = struct.unpack('>III', E.rd(addrs[side] + 12, 12))
            got.append({12: s32(v[0]), 16: s32(v[1]), 20: s32(v[2]), 0x19: notes[side][0x19]})
        exp = []
        for side in (0, 1):
            if flag and (side == 0 or stereo):
                exp.append(model_one(notes[side], hdr, side, ssum, base, root))
            elif not flag and ssum != 0 and (side == 0 or stereo) and not notes[side][0x19] and notes[side][16] != 8:
                n2 = dict(notes[side]); n2[12] = n2[16]; exp.append(n2)    # SLpScn: start at the loop
            else:
                exp.append(dict(notes[side]))
        regs_ok = [mu.reg_read(UC_M68K_REG_D2 + i) & 0xffffffff for i in range(4)] == [0x5A5A0000 + i for i in range(4)]
        regs_ok &= [mu.reg_read(x) & 0xffffffff for x in (UC_M68K_REG_D6, UC_M68K_REG_D7, UC_M68K_REG_A2,
                                                           UC_M68K_REG_A4, UC_M68K_REG_A5)] == saved
        regs_ok &= (mu.reg_read(UC_M68K_REG_A7) & 0xffffffff) == sp + 24
        n += 1
        if got != exp or not regs_ok:
            fails.append(f'slice_exit trial {trial} stereo {stereo} flag {flag} sum {ssum}: {got} != {exp} regs {regs_ok}')
    # 5. pit_hook: voice+0x1F = zone +12; d1 = zone word +10, d0 low word = header word +0x38 (as the replaced code)
    ZONE = 0x10054000
    for trial in range(200):
        zk, zw, hw = r.randrange(256), r.randrange(65536), r.randrange(65536)
        mu.mem_write(ZONE + 10, struct.pack('>HB', zw, zk)); mu.mem_write(HDR + 0x38, struct.pack('>H', hw))
        mu.mem_write(P - 0x3C, b'\x01\x00')
        d0in, d1in = r.randrange(1 << 32), r.randrange(1 << 32)
        E.call(syms['pit_hook'], [], {UC_M68K_REG_A1: ZONE, UC_M68K_REG_A0: HDR, UC_M68K_REG_A5: P,
                                       UC_M68K_REG_D0: d0in, UC_M68K_REG_D1: d1in})
        d0, d1 = mu.reg_read(UC_M68K_REG_D0) & 0xffffffff, mu.reg_read(UC_M68K_REG_D1) & 0xffffffff
        n += 1
        if E.rd(P - 0x3C, 2) != bytes([1, zk]) or d1 & 0xffff != zw or d0 & 0xffff != hw or d0 >> 16 != d0in >> 16:
            fails.append(f'pit_hook trial {trial}: {E.rd(P - 0x3C, 2).hex()} d0 {d0:#x} d1 {d1:#x}')
    print(f'{n} checks; {len(fails)} failures')
    for f in fails[:15]:
        print('  ' + f)
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
