//! E-mu's EOS470.EXE is a DOS self-extracting disk writer (LZEXE stub, 5,668 bytes) followed by the raw
//! 1.44 MB EOS floppy image. Any file that contains an EOS floppy header is accepted (the .EXE or a
//! plain floppy image).

use crate::image::{be32, MAGIC_FLOPPY};

/// Finds the EOS floppy image: header magic 0x76543211 with the EOS entry point 0x00020602.
pub fn find_floppy(data: &[u8]) -> Option<&[u8]> {
    let magic = MAGIC_FLOPPY.to_be_bytes();
    let mut i = 0usize;
    while i + 0x200 <= data.len() {
        let at = i + data[i..].windows(4).position(|w| w == magic)?;
        if at + 0x200 <= data.len() && be32(data, at + 0x0C) == 0x0002_0602 {
            let ln = be32(data, at + 0x10) as usize;
            if at + 0x200 + ln <= data.len() {
                return Some(&data[at..]);
            }
        }
        i = at + 1;
    }
    None
}
