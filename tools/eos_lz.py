#!/usr/bin/env python3
"""E-mu EOS floppy image codec (magic 0x76543211, "Lz77").

Reimplemented from the EOS Primary Loader (PL01 01f05) filter at loader 0x18be8.
Stream: MSB-first bits.  flag(1)=0 -> literal(8); flag=1 -> dist(8), len(8).
dist==0 terminates.  If len > dist the loader copies ONE byte from dist back and
then repeats that byte len times (RLE quirk) -- reproduced exactly here.
Window = 256-byte ring; output bytes are pushed into the ring after each token.

usage: eos_lz.py unpack FLOPPY.img OUT.bin
       eos_lz.py fixsum IN.bin OUT.bin          (recompute length + checksum after patching)
       eos_lz.py pack   IN.bin OUT_FLOPPY.img   (IN.bin = 0x76543210 image incl. header)
"""
import struct, sys

WIN = 256


class BitReader:
    def __init__(self, data):
        self.d, self.p, self.buf, self.cnt = data, 0, 0, 0

    def get(self, n):
        v = 0
        for _ in range(n):
            if self.cnt == 0:
                if self.p >= len(self.d):
                    return -1
                self.buf, self.p, self.cnt = self.d[self.p], self.p + 1, 8
            self.cnt -= 1
            v = (v << 1) | ((self.buf >> self.cnt) & 1)
        return v


def decompress(comp):
    br = BitReader(comp)
    ring = bytearray(WIN)
    pos = 0
    out = bytearray()
    while True:
        f = br.get(1)
        if f < 0:
            break
        if f == 1:
            dist, ln = br.get(8), br.get(8)
            if dist <= 0 or ln < 0:
                break
            s = (pos - dist) % WIN
            if ln > dist:
                chunk = bytes([ring[s]]) * ln
            else:
                chunk = bytes(ring[(s + i) % WIN] for i in range(ln))
        else:
            b = br.get(8)
            if b < 0:
                break
            chunk = bytes([b])
        for b in chunk:
            ring[pos] = b
            pos = (pos + 1) % WIN
        out += chunk
    return bytes(out)


class BitWriter:
    def __init__(self):
        self.out, self.acc, self.n = bytearray(), 0, 0

    def put(self, v, n):
        for i in range(n - 1, -1, -1):
            self.acc = (self.acc << 1) | ((v >> i) & 1)
            self.n += 1
            if self.n == 8:
                self.out.append(self.acc)
                self.acc, self.n = 0, 0

    def flush(self):
        if self.n:
            self.out.append(self.acc << (8 - self.n))
            self.acc, self.n = 0, 0
        return bytes(self.out)


def compress(data):
    """Greedy encoder producing streams the loader's decoder accepts.
    Copies must have len <= dist (no overlap); len > dist is only legal as a
    run of the single byte data[i-dist]."""
    bw = BitWriter()
    i, n = 0, len(data)
    heads = {}  # 3-byte prefix -> list of recent positions
    while i < n:
        best_d, best_l = 0, 0
        # run of one byte: emit as dist=1 RLE (len must exceed 1)
        if i >= 1:
            c = data[i - 1]
            r = 0
            while r < min(255, n - i) and data[i + r] == c:
                r += 1
            if r >= 2:
                best_d, best_l = 1, r
        key = data[i:i + 3]
        for p in reversed(heads.get(key, ())):
            d = i - p
            if d > 255:
                break
            if d < 3:  # would need len > dist, which the decoder treats as a 1-byte run
                continue
            maxl = min(d, 255, n - i)
            l = 3
            while l < maxl and data[p + l] == data[i + l]:
                l += 1
            if l > best_l:
                best_d, best_l = d, l
                if l == 255:
                    break
        step = best_l if best_l >= 3 else 1
        for j in range(i, min(i + step, n - 2)):
            lst = heads.setdefault(data[j:j + 3], [])
            lst.append(j)
            if len(lst) > 64:
                del lst[:32]
        if best_l >= 3 or (best_d == 1 and best_l >= 2):
            bw.put(1, 1); bw.put(best_d, 8); bw.put(best_l, 8)
            i += best_l
        else:
            bw.put(0, 1); bw.put(data[i], 8)
            i += 1
    bw.put(1, 1); bw.put(0, 8); bw.put(0, 8)  # terminator (dist 0)
    return bw.flush()


def csum(img):
    """Loader check at 0x1784: byte-sum of hdr[0x10] bytes starting at the header."""
    ln = struct.unpack('>I', img[0x10:0x14])[0]
    return sum(img[:ln]) & 0xffffffff


def main():
    cmd, src, dst = sys.argv[1:4]
    raw = open(src, 'rb').read()
    if cmd == 'unpack':
        magic, c1, c2, entry, ln = struct.unpack('>5I', raw[:0x14])
        assert magic == 0x76543211, hex(magic)
        out = decompress(raw[0x200:0x200 + ln])
        open(dst, 'wb').write(out)
        print(f'floppy hdr csum={c1:08x} ~={c2:08x} entry={entry:08x} complen={ln:#x}')
        print(f'unpacked {len(out):#x} bytes, inner magic={out[:4].hex()}')
    elif cmd == 'pack':
        magic, c1, c2, entry, ln = struct.unpack('>5I', raw[:0x14])
        assert magic == 0x76543210 and ln == len(raw), 'need a full 0x76543210 image'
        if csum(raw) != c1 or (c1 ^ 0xffffffff) != c2:
            raise SystemExit(f'header checksum stale ({c1:08x}, actual {csum(raw):08x}); run fixsum first')
        comp = compress(raw)
        assert decompress(comp) == raw, 'round-trip failed'
        # Outer header = inner header with magic ...11 and length = compressed size
        hdr = bytearray(raw[:0x200])
        struct.pack_into('>I', hdr, 0, 0x76543211)
        struct.pack_into('>I', hdr, 0x10, len(comp))
        disk = bytes(hdr) + comp
        cap = 1474560
        if len(disk) > cap:
            raise SystemExit(f'too big for one 1.44MB disk: {len(disk)} > {cap}')
        open(dst, 'wb').write(disk + b'\0' * (cap - len(disk)))
        print(f'compressed {len(raw):#x} -> {len(comp):#x}; disk free {cap - len(disk)} bytes')
    elif cmd == 'fixsum':
        img = bytearray(raw)
        struct.pack_into('>I', img, 0x10, len(img))
        # sum covers its own fields; any (x, ~x) pair contributes 4*255, so normalise first
        struct.pack_into('>II', img, 4, 0, 0xffffffff)
        c = csum(img)
        struct.pack_into('>II', img, 4, c, c ^ 0xffffffff)
        open(dst, 'wb').write(img)
        print(f'checksum {c:08x}')
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main()
