#!/usr/bin/env python3
"""Option A test patch: CEM3320 (OB-Xa) 2-pole resonance law for the 2/4/6-pole lowpasses.

Data-only, in place (image size unchanged):
  * RES16 table @0x6875C (used by LP2/LP4/LP6 computeFrames)          -> notes/cem3320.md
  * immediates in FUN_00065E18 (realtime resonance -> stage word, used by LP packQ)
  * header name -> "EOS 4.70 CEM3320 test" so the loader shows which OS it is loading

usage: patch_cem3320.py BASE.bin OUT.bin
"""
import struct, sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eos_lz      # noqa: E402
import cem3320     # noqa: E402

BASE = 0x20000

# (address, original bytes, new bytes, what)
CODE = [
    (0x65E3C, '72ce', '72b6', 'X_low slope  -50 -> -74      (moveq #imm,d1)'),
    (0x65E3E, '70fd', '7009', 'F_low slope   -3 -> +9       (moveq #imm,d0)'),
    (0x65E4A, 'dcbc84000000', 'dcbc95000000', 'X_low base 0x84 -> 0x95'),
    (0x65E5C, 'd2bc00080000', 'd2bc00010000', 'F_low base 0x08 -> 0x01'),
    (0x65E66, '72d5', '72c3', 'X_high slope -43 -> -61     (moveq #imm,d1)'),
    (0x65E70, 'd0bc0000ff00', 'd0bc0000fd00', 'X_high base 0xFF -> 0xFD'),
    (0x65E7A, 'e480', 'e880', 'F_high slope q>>2 -> q>>4  (asr.l #n,d0)'),
    (0x65E7C, 'd0bc000000cf', 'd0bc000000e7', 'F_high base 0xCF -> 0xE7'),
]
RES16_ADDR = 0x6875C
NAME = b'EOS 4.70 CEM3320 test'

# patched FUN_00065E18: (base, slope) per field, byte = base + (slope*q')>>7 ; F_high = base + q'>>4
X_LO, F_LO, X_HI, F_HI = (0x95, -74), (0x01, 9), (0xFD, -61), 0xE7


def formula(q):
    """Python twin of the patched FUN_00065E18 (verified against Unicorn by emu_fun65e18.py)."""
    u = min(0x7f, ((q * 0x11) >> 4) & 0xff)
    return ((((X_LO[1] * u) >> 7) + X_LO[0]) << 24 | (((F_LO[1] * u) >> 7) + F_LO[0]) << 16 |
            (((X_HI[1] * u) >> 7) + X_HI[0]) << 8 | ((u >> 4) + F_HI)) & 0xffffffff


def table16():
    # computeFrames indexes with q>>3; sample the realtime formula mid-step so both paths agree
    return [formula(8 * j + 4) for j in range(16)]


def patch(img):
    img = bytearray(img)
    for addr, old, new, what in CODE:
        o, ob, nb = addr - BASE, bytes.fromhex(old), bytes.fromhex(new)
        if img[o:o + len(ob)] != ob:
            raise SystemExit(f'{addr:#x}: expected {old}, found {img[o:o+len(ob)].hex()} - wrong base image?')
        img[o:o + len(nb)] = nb
    o = RES16_ADDR - BASE
    stock = b''.join(struct.pack('>I', w) for w in cem3320.ef.RES16)
    if img[o:o + 64] != stock:
        raise SystemExit('RES16 table does not match stock 4.70')
    img[o:o + 64] = b''.join(struct.pack('>I', w) for w in table16())
    assert img[0x18:0x30].startswith(b'EOS v4.70')
    img[0x18:0x30] = NAME.ljust(24, b' ')
    return bytes(img)


def main():
    base = open(sys.argv[1], 'rb').read()
    out = patch(base)
    # recompute length + checksum (same as eos_lz.py fixsum)
    img = bytearray(out)
    struct.pack_into('>II', img, 4, 0, 0xffffffff)
    c = eos_lz.csum(img)
    struct.pack_into('>II', img, 4, c, c ^ 0xffffffff)
    open(sys.argv[2], 'wb').write(img)
    diff = sum(a != b for a, b in zip(base, img))
    print(f'{sys.argv[2]}: {diff} bytes changed, checksum {c:08x}')


if __name__ == '__main__':
    main()
