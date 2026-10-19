#!/usr/bin/env python3
"""cfdis.py BIN BASE START END  -- quick ColdFire/68k disassembly with string annotations."""
import sys, re, capstone

data = open(sys.argv[1], 'rb').read()
base = int(sys.argv[2], 0)
start = int(sys.argv[3], 0)
end = int(sys.argv[4], 0)

md = capstone.Cs(capstone.CS_ARCH_M68K, capstone.CS_MODE_BIG_ENDIAN | capstone.CS_MODE_M68K_040)


def cstr(addr):
    o = addr - base
    if not (0 <= o < len(data)):
        return None
    e = data.find(b'\0', o, o + 120)
    if e < 0 or e - o < 3:
        return None
    s = data[o:e]
    if sum(32 <= c < 127 or c in (9, 10, 13) for c in s) < len(s) * 0.9:
        return None
    return s.decode('latin1')


pc = start
while pc < end:
    o = pc - base
    insns = list(md.disasm(data[o:o + 10], pc, 1))
    if not insns:
        print(f'{pc:08x}:  {data[o:o+2].hex()}   dc.w')
        pc += 2
        continue
    i = insns[0]
    note = ''
    for m in re.findall(r'\$([0-9a-f]{3,8})', i.op_str):
        s = cstr(int(m, 16))
        if s:
            note = f'   ; "{s[:60]}"'
    print(f'{pc:08x}:  {i.bytes.hex():<20} {i.mnemonic:<10} {i.op_str}{note}')
    pc += i.size
