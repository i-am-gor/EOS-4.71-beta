//! EOS OS image: 0x200-byte big-endian header (magic, checksum, ~checksum, entry, length, name at 0x18).

pub const MAGIC_RAW: u32 = 0x7654_3210;
pub const MAGIC_FLOPPY: u32 = 0x7654_3211;
/// The loader decompresses into RAM 0x10200000..0x10400000.
pub const LOADER_RAM: usize = 0x20_0000;

pub fn be32(b: &[u8], o: usize) -> u32 {
    u32::from_be_bytes([b[o], b[o + 1], b[o + 2], b[o + 3]])
}

pub fn put32(b: &mut [u8], o: usize, v: u32) {
    b[o..o + 4].copy_from_slice(&v.to_be_bytes());
}

/// Loader check: byte sum of the first `len` bytes (header included).
pub fn csum(img: &[u8]) -> u32 {
    let len = be32(img, 0x10) as usize;
    img[..len.min(img.len())].iter().fold(0u32, |a, &b| a.wrapping_add(b as u32))
}

pub fn name(img: &[u8]) -> String {
    let raw = &img[0x18..0x30];
    let end = raw.iter().position(|&b| b == 0).unwrap_or(raw.len());
    String::from_utf8_lossy(&raw[..end]).trim().to_string()
}

/// Verifies a raw image as the loader would.
pub fn verify(img: &[u8]) -> Result<(), String> {
    if img.len() < 0x200 || be32(img, 0) != MAGIC_RAW {
        return Err("not an EOS OS image (magic)".into());
    }
    let c = be32(img, 4);
    if csum(img) != c || c ^ be32(img, 8) != 0xffff_ffff {
        return Err("image checksum wrong".into());
    }
    if img.len() > LOADER_RAM {
        return Err("image too large for the loader".into());
    }
    Ok(())
}

/// Decodes an EOS floppy image (magic 0x76543211, compressed stream at 0x200) to the raw OS image.
pub fn unpack_floppy(floppy: &[u8]) -> Result<Vec<u8>, String> {
    if floppy.len() < 0x200 || be32(floppy, 0) != MAGIC_FLOPPY {
        return Err("not an EOS floppy image".into());
    }
    let ln = be32(floppy, 0x10) as usize;
    if 0x200 + ln > floppy.len() {
        return Err("floppy image truncated".into());
    }
    let raw = crate::lz::decompress(&floppy[0x200..0x200 + ln]);
    verify(&raw)?;
    Ok(raw)
}
