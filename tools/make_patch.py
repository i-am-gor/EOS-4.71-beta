#!/usr/bin/env python3
"""Make the redistributable 4.71-beta patch: only the bytes that differ from stock EOS 4.70.

usage: make_patch.py STOCK.bin PATCHED.bin OUT.e4p
Format (big-endian): b'E4PATCH1', sha256(stock) 32, sha256(patched) 32, u32 image length, u8 name length,
name, u32 range count, then per range: u32 offset (image-relative), u32 length, bytes.
Ranges are exact runs of differing bytes (no unchanged stock bytes are included).
"""
import hashlib, struct, sys


def main():
    a, b = (open(p, 'rb').read() for p in sys.argv[1:3])
    assert len(a) == len(b)
    runs, i = [], 0
    while i < len(a):
        if a[i] != b[i]:
            j = i
            while j < len(a) and a[j] != b[j]:
                j += 1
            runs.append((i, b[i:j]))
            i = j
        else:
            i += 1
    name = b[0x18:0x30].rstrip(b' \0')
    out = bytearray(b'E4PATCH1' + hashlib.sha256(a).digest() + hashlib.sha256(b).digest())
    out += struct.pack('>IB', len(b), len(name)) + name + struct.pack('>I', len(runs))
    for off, data in runs:
        out += struct.pack('>II', off, len(data)) + data
    open(sys.argv[3], 'wb').write(out)
    # self-check
    img = bytearray(a)
    for off, data in runs:
        img[off:off + len(data)] = data
    assert bytes(img) == b
    print(f'{sys.argv[3]}: {name.decode()!r}, {len(runs)} ranges, {sum(len(d) for _, d in runs)} patched bytes, '
          f'{len(out)} bytes total')


if __name__ == '__main__':
    main()
