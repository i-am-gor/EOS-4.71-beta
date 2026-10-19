//! EOS 4.71-beta patch. Contains only the bytes that differ from stock EOS 4.70 (all written for this
//! project); it is applied to the user's own 4.70 image and both ends are checked by SHA-256.
//!
//! Format (big-endian): b"E4PATCH1", sha256(stock) 32, sha256(patched) 32, u32 image length,
//! u8 name length, name, u32 range count, then per range u32 offset, u32 length, bytes.
//! Made by tools/make_patch.py.

use sha2::{Digest, Sha256};

pub const PATCH: &[u8] = include_bytes!("../data/eos471beta.e4p");

pub struct Patch<'a> {
    pub stock_sha: &'a [u8],
    pub out_sha: &'a [u8],
    pub len: usize,
    pub name: String,
    pub ranges: Vec<(usize, &'a [u8])>,
}

fn u32at(b: &[u8], o: usize) -> usize {
    u32::from_be_bytes([b[o], b[o + 1], b[o + 2], b[o + 3]]) as usize
}

pub fn parse(p: &[u8]) -> Result<Patch<'_>, String> {
    if p.len() < 81 || &p[..8] != b"E4PATCH1" {
        return Err("bad patch data".into());
    }
    let len = u32at(p, 72);
    let nl = p[76] as usize;
    let name = String::from_utf8_lossy(&p[77..77 + nl]).to_string();
    let mut o = 77 + nl;
    let count = u32at(p, o);
    o += 4;
    let mut ranges = Vec::with_capacity(count);
    for _ in 0..count {
        let off = u32at(p, o);
        let l = u32at(p, o + 4);
        o += 8;
        if o + l > p.len() || off + l > len {
            return Err("bad patch data".into());
        }
        ranges.push((off, &p[o..o + l]));
        o += l;
    }
    Ok(Patch { stock_sha: &p[8..40], out_sha: &p[40..72], len, name, ranges })
}

pub fn sha256(d: &[u8]) -> Vec<u8> {
    Sha256::digest(d).to_vec()
}

/// Checks that `img` is exactly the stock EOS 4.70 image the patch was made for.
pub fn check_stock(img: &[u8]) -> Result<(), String> {
    let p = parse(PATCH)?;
    if img.len() != p.len || sha256(img) != p.stock_sha {
        return Err("this is not the original E-mu EOS 4.70 image (SHA-256 mismatch)".into());
    }
    Ok(())
}

/// Applies the 4.71-beta patch to stock 4.70 and verifies the result.
pub fn apply(stock: &[u8]) -> Result<Vec<u8>, String> {
    check_stock(stock)?;
    let p = parse(PATCH)?;
    let mut img = stock.to_vec();
    for (off, data) in &p.ranges {
        img[*off..*off + data.len()].copy_from_slice(data);
    }
    if sha256(&img) != p.out_sha {
        return Err("patched image does not match EOS 4.71-beta (SHA-256)".into());
    }
    crate::image::verify(&img)?;
    Ok(img)
}

/// (name, ranges, patched bytes)
pub fn info() -> (String, usize, usize) {
    let p = parse(PATCH).expect("embedded patch");
    let bytes = p.ranges.iter().map(|(_, d)| d.len()).sum();
    (p.name, p.ranges.len(), bytes)
}
