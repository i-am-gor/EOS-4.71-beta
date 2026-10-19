//! EOS floppy / MIDI-download codec ("Lz77", floppy magic 0x76543211).
//!
//! Stream: MSB-first bits. flag 0 -> literal (8 bits); flag 1 -> distance (8), length (8).
//! Distance 0 ends the stream. 256-byte ring. If length > distance the loader repeats the single byte
//! at `distance` back (RLE quirk), so the encoder only uses overlapping copies for 1-byte runs.

use std::collections::HashMap;

const WIN: usize = 256;

struct BitReader<'a> {
    d: &'a [u8],
    p: usize,
    buf: u8,
    cnt: u32,
}

impl BitReader<'_> {
    fn get(&mut self, n: u32) -> Option<u32> {
        let mut v = 0u32;
        for _ in 0..n {
            if self.cnt == 0 {
                if self.p >= self.d.len() {
                    return None;
                }
                self.buf = self.d[self.p];
                self.p += 1;
                self.cnt = 8;
            }
            self.cnt -= 1;
            v = (v << 1) | ((self.buf >> self.cnt) & 1) as u32;
        }
        Some(v)
    }
}

/// Decodes a compressed stream exactly like the loader.
pub fn decompress(comp: &[u8]) -> Vec<u8> {
    let mut br = BitReader { d: comp, p: 0, buf: 0, cnt: 0 };
    let mut ring = [0u8; WIN];
    let mut pos = 0usize;
    let mut out = Vec::with_capacity(comp.len() * 2);
    let mut chunk: Vec<u8> = Vec::with_capacity(256);
    loop {
        let Some(f) = br.get(1) else { break };
        chunk.clear();
        if f == 1 {
            let (Some(dist), Some(len)) = (br.get(8), br.get(8)) else { break };
            if dist == 0 {
                break;
            }
            let (dist, len) = (dist as usize, len as usize);
            let s = (pos + WIN - dist) % WIN;
            if len > dist {
                chunk.extend(std::iter::repeat(ring[s]).take(len));
            } else {
                chunk.extend((0..len).map(|i| ring[(s + i) % WIN]));
            }
        } else {
            let Some(b) = br.get(8) else { break };
            chunk.push(b as u8);
        }
        for &b in &chunk {
            ring[pos] = b;
            pos = (pos + 1) % WIN;
            out.push(b);
        }
    }
    out
}

struct BitWriter {
    out: Vec<u8>,
    acc: u32,
    n: u32,
}

impl BitWriter {
    fn put(&mut self, v: u32, n: u32) {
        for i in (0..n).rev() {
            self.acc = (self.acc << 1) | ((v >> i) & 1);
            self.n += 1;
            if self.n == 8 {
                self.out.push(self.acc as u8);
                self.acc = 0;
                self.n = 0;
            }
        }
    }

    fn flush(mut self) -> Vec<u8> {
        if self.n > 0 {
            self.out.push((self.acc << (8 - self.n)) as u8);
        }
        self.out
    }
}

/// Greedy encoder producing streams the loader accepts (same algorithm as tools/eos_lz.py).
pub fn compress(data: &[u8]) -> Vec<u8> {
    let mut bw = BitWriter { out: Vec::with_capacity(data.len()), acc: 0, n: 0 };
    let n = data.len();
    let mut heads: HashMap<[u8; 3], Vec<usize>> = HashMap::new();
    let mut i = 0usize;
    while i < n {
        let (mut best_d, mut best_l) = (0usize, 0usize);
        if i >= 1 {
            let c = data[i - 1];
            let mut r = 0usize;
            while r < 255.min(n - i) && data[i + r] == c {
                r += 1;
            }
            if r >= 2 {
                best_d = 1;
                best_l = r;
            }
        }
        if i + 3 <= n {
            if let Some(lst) = heads.get(&[data[i], data[i + 1], data[i + 2]]) {
                for &p in lst.iter().rev() {
                    let d = i - p;
                    if d > 255 {
                        break;
                    }
                    if d < 3 {
                        continue;
                    }
                    let maxl = d.min(255).min(n - i);
                    let mut l = 3usize;
                    while l < maxl && data[p + l] == data[i + l] {
                        l += 1;
                    }
                    if l > best_l {
                        best_d = d;
                        best_l = l;
                        if l == 255 {
                            break;
                        }
                    }
                }
            }
        }
        let step = if best_l >= 3 { best_l } else { 1 };
        let end = (i + step).min(n.saturating_sub(2));
        for j in i..end {
            let lst = heads.entry([data[j], data[j + 1], data[j + 2]]).or_default();
            lst.push(j);
            if lst.len() > 64 {
                lst.drain(..32);
            }
        }
        if best_l >= 3 || (best_d == 1 && best_l >= 2) {
            bw.put(1, 1);
            bw.put(best_d as u32, 8);
            bw.put(best_l as u32, 8);
            i += best_l;
        } else {
            bw.put(0, 1);
            bw.put(data[i] as u32, 8);
            i += 1;
        }
    }
    bw.put(1, 1);
    bw.put(0, 8);
    bw.put(0, 8);
    bw.flush()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn roundtrip() {
        let mut v = Vec::new();
        for i in 0..20000u32 {
            v.push(((i * 7 + i / 13) % 251) as u8);
            if i % 97 == 0 {
                v.extend(std::iter::repeat(0u8).take((i % 300) as usize));
            }
        }
        assert_eq!(decompress(&compress(&v)), v);
    }
}
