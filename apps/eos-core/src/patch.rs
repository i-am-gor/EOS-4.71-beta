//! EOS 4.71-beta patches. Each contains only the bytes that differ from stock EOS 4.70 (all written for
//! this project); it is applied to the user's own 4.70 image and both ends are checked by SHA-256.
//!
//! Format (big-endian): b"E4PATCH1", sha256(stock) 32, sha256(patched) 32, u32 image length,
//! u8 name length, name, u32 range count, then per range u32 offset, u32 length, bytes.
//! Made by tools/make_patch.py.

use sha2::{Digest, Sha256};

/// EOS 4.71-beta (beta1).
pub const BETA1: &[u8] = include_bytes!("../data/eos471beta.e4p");
/// EOS 4.71-beta2 +LfoCk.
pub const BETA2: &[u8] = include_bytes!("../data/eos471beta2.e4p");

/// Which OS to build from the user's EOS 4.70.
#[derive(PartialEq, Eq, Clone, Copy, Debug)]
pub enum Version {
    Beta2,
    Beta1,
    Original,
}

impl Version {
    /// The embedded patch for this version (none for the original 4.70).
    pub fn patch(self) -> Option<&'static [u8]> {
        match self {
            Version::Beta2 => Some(BETA2),
            Version::Beta1 => Some(BETA1),
            Version::Original => None,
        }
    }
}

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

/// Checks that `img` is exactly the stock EOS 4.70 image the patches were made for.
pub fn check_stock(img: &[u8]) -> Result<(), String> {
    let p = parse(BETA1)?;
    if img.len() != p.len || sha256(img) != p.stock_sha {
        return Err("this is not the original E-mu EOS 4.70 image (SHA-256 mismatch)".into());
    }
    Ok(())
}

/// Applies a patch to stock 4.70 and verifies the result.
pub fn apply(stock: &[u8], patch: &[u8]) -> Result<Vec<u8>, String> {
    check_stock(stock)?;
    let p = parse(patch)?;
    if p.stock_sha != parse(BETA1)?.stock_sha {
        return Err("patch was not made for EOS 4.70".into());
    }
    let mut img = stock.to_vec();
    for (off, data) in &p.ranges {
        img[*off..*off + data.len()].copy_from_slice(data);
    }
    if sha256(&img) != p.out_sha {
        return Err(format!("patched image does not match {} (SHA-256)", p.name));
    }
    crate::image::verify(&img)?;
    Ok(img)
}

/// (name, ranges, patched bytes) of a patch.
pub fn info(patch: &[u8]) -> (String, usize, usize) {
    let p = parse(patch).expect("embedded patch");
    let bytes = p.ranges.iter().map(|(_, d)| d.len()).sum();
    (p.name, p.ranges.len(), bytes)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn embedded_patches() {
        let (a, b) = (parse(BETA1).unwrap(), parse(BETA2).unwrap());
        assert_eq!(a.stock_sha, b.stock_sha, "both patches apply to the same EOS 4.70");
        assert_eq!(a.len, b.len);
        assert_eq!(a.name, "EOS 4.71-beta");
        assert_eq!(b.name, "EOS 4.71-beta2 +LfoCk");
        for p in [&a, &b] {
            let mut last = 0;
            for (off, d) in &p.ranges {
                assert!(*off >= last && !d.is_empty(), "ranges sorted and non-empty");
                last = off + d.len();
            }
        }
    }
}
