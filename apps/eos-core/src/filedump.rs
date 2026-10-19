//! MMA "MIDI File Dump" as accepted by the EOS Primary Loader (receiver 0x17360..0x17C94).
//!
//!   header : F0 7E 00 07 01 <src> 'E''X''E'' ' <len: 4 x 7-bit, LSB first> "EOSLoader" F7
//!   packet : F0 7E 00 07 02 <pkt 0..7F wrap> <nbytes-1> <8-for-7 data> <xor> F7   (<= 112 bytes/packet)
//!   EOF    : F0 7E 00 7B <pkt> F7
//! Device ID must be 00 (the loader checksums with its own ID 0). Payload = the compressed OS stream.

use crate::{image, lz};

pub const DEV: u8 = 0x00;
pub const SRC: u8 = 0x00;

fn enc7(data: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(data.len() * 8 / 7 + 8);
    for grp in data.chunks(7) {
        let mut msb = 0u8;
        for (j, &b) in grp.iter().enumerate() {
            msb |= ((b >> 7) & 1) << (6 - j);
        }
        out.push(msb);
        out.extend(grp.iter().map(|b| b & 0x7f));
    }
    out
}

fn dec7(enc: &[u8]) -> Vec<u8> {
    let mut out = Vec::new();
    let mut msb = 0u8;
    for (i, &b) in enc.iter().enumerate() {
        if i % 8 == 0 {
            msb = b;
        } else {
            msb <<= 1;
            out.push(b | (msb & 0x80));
        }
    }
    out
}

fn xor7(bs: &[u8]) -> u8 {
    bs.iter().fold(0u8, |a, &b| a ^ b) & 0x7f
}

/// All messages (each F0 .. F7) for a compressed payload.
pub fn build_messages(payload: &[u8]) -> Vec<Vec<u8>> {
    let n = payload.len();
    let mut msgs = Vec::new();
    let mut hdr = vec![0xf0, 0x7e, DEV, 0x07, 0x01, SRC];
    hdr.extend_from_slice(b"EXE ");
    hdr.extend((0..4).map(|k| ((n >> (7 * k)) & 0x7f) as u8));
    hdr.extend_from_slice(b"EOSLoader");
    hdr.push(0xf7);
    msgs.push(hdr);
    let mut pkt = 0u8;
    for chunk in payload.chunks(112) {
        let e = enc7(chunk);
        let mut body = vec![0x7e, DEV, 0x07, 0x02, pkt, (e.len() - 1) as u8];
        body.extend_from_slice(&e);
        let x = xor7(&body);
        let mut m = vec![0xf0];
        m.extend_from_slice(&body);
        m.push(x);
        m.push(0xf7);
        msgs.push(m);
        pkt = (pkt + 1) & 0x7f;
    }
    msgs.push(vec![0xf0, 0x7e, DEV, 0x7b, pkt, 0xf7]);
    msgs
}

/// Compresses a raw image and builds the messages; then checks them with the loader simulation.
pub fn messages_for_image(img: &[u8]) -> Result<Vec<Vec<u8>>, String> {
    image::verify(img)?;
    let payload = lz::compress(img);
    let msgs = build_messages(&payload);
    let back = simulate(&msgs)?;
    if back != img {
        return Err("internal check failed: SysEx does not reassemble to the image".into());
    }
    Ok(msgs)
}

/// Applies the loader's acceptance rules and returns the decompressed image.
pub fn simulate(msgs: &[Vec<u8>]) -> Result<Vec<u8>, String> {
    let m = msgs.first().ok_or("no messages")?;
    if m.len() < 15 || m[1] != 0x7e || m[3] != 0x07 || m[4] != 0x01 || &m[6..9] != b"EXE" {
        return Err("bad header".into());
    }
    let length: usize = (0..4).map(|k| ((m[10 + k] & 0x7f) as usize) << (7 * k)).sum();
    let mut out = Vec::new();
    let mut expect = 0u8;
    let mut eof = false;
    for m in &msgs[1..] {
        if m.len() < 6 || m[0] != 0xf0 || *m.last().unwrap() != 0xf7 || m[1] != 0x7e || m[2] != DEV {
            return Err("bad message framing".into());
        }
        let body = &m[3..m.len() - 1];
        if body[0] == 0x7b {
            eof = true;
            break;
        }
        if body.len() < 5 || body[0] != 0x07 || body[1] != 0x02 || body[2] != expect {
            return Err(format!("packet order (expected {expect})"));
        }
        let cnt = body[3] as usize + 1;
        if body.len() != cnt + 5 || (DEV ^ 0x7e ^ xor7(&body[..cnt + 4])) & 0x7f != body[cnt + 4] {
            return Err("packet checksum".into());
        }
        if m[1..m.len() - 1].iter().any(|&b| b >= 0x80) {
            return Err("non 7-bit byte".into());
        }
        out.extend(dec7(&body[4..4 + cnt]));
        expect = (expect + 1) & 0x7f;
    }
    if !eof {
        return Err("no EOF message".into());
    }
    if out.len() != length {
        return Err("payload length mismatch".into());
    }
    let raw = lz::decompress(&out);
    image::verify(&raw)?;
    if raw.len() < length {
        return Err("loader would report Wrong length".into());
    }
    Ok(raw)
}

/// A .syx file: all messages concatenated.
pub fn to_syx(msgs: &[Vec<u8>]) -> Vec<u8> {
    msgs.concat()
}
