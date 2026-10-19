//! E-mu editor SysEx for a running EOS (decoded from EOS 4.70):
//!   request : F0 18 21 <dev> 55 02 <n> (<id lo> <id hi>)*n F7
//!   value / edit : F0 18 21 <dev> 55 01 02 <id lo> <id hi> <val lo> <val hi> 7F F7
//! Values are 14-bit, >= 0x2000 negative. Voice parameters act on the preset/voice selected on the
//! front panel.

use midir::MidiOutputConnection;
use std::sync::mpsc::Receiver;
use std::time::{Duration, Instant};

/// Parameter ids used by the tests.
pub mod id {
    pub const VOICE_PAN: u16 = 40;
    pub const MULTI_PAN: u16 = 249;
    pub const FILTER_TYPE: u16 = 82;
    pub const FILTER_FREQ: u16 = 83;
    pub const FILTER_Q: u16 = 84;
    /// cord n (0..17): source, destination, amount
    pub fn cord(n: u16) -> (u16, u16, u16) {
        (129 + 3 * n, 130 + 3 * n, 131 + 3 * n)
    }
}

pub fn set_msg(dev: u8, pid: u16, value: i32) -> Vec<u8> {
    let v = (value as u32) & 0x3fff;
    vec![0xf0, 0x18, 0x21, dev & 0x7f, 0x55, 0x01, 0x02, (pid & 0x7f) as u8, ((pid >> 7) & 0x7f) as u8,
         (v & 0x7f) as u8, ((v >> 7) & 0x7f) as u8, 0x7f, 0xf7]
}

pub fn request_msg(dev: u8, ids: &[u16]) -> Vec<u8> {
    let mut m = vec![0xf0, 0x18, 0x21, dev & 0x7f, 0x55, 0x02, ids.len() as u8];
    for &i in ids {
        m.push((i & 0x7f) as u8);
        m.push(((i >> 7) & 0x7f) as u8);
    }
    m.push(0xf7);
    m
}

fn s14(v: u32) -> i32 {
    if v >= 0x2000 { v as i32 - 0x4000 } else { v as i32 }
}

pub struct Remote<'a> {
    pub out: &'a mut MidiOutputConnection,
    pub rx: &'a Receiver<Vec<u8>>,
    pub dev: u8,
}

impl Remote<'_> {
    pub fn set(&mut self, pid: u16, value: i32) -> Result<(), String> {
        self.out.send(&set_msg(self.dev, pid, value)).map_err(|e| e.to_string())
    }

    /// Reads one parameter; None if the sampler does not answer.
    pub fn get(&mut self, pid: u16) -> Option<i32> {
        while self.rx.try_recv().is_ok() {}
        self.out.send(&request_msg(self.dev, &[pid])).ok()?;
        let t0 = Instant::now();
        while t0.elapsed() < Duration::from_millis(800) {
            if let Ok(m) = self.rx.recv_timeout(Duration::from_millis(20)) {
                if m.len() >= 12 && m[1] == 0x18 && m[2] == 0x21 && m[4] == 0x55 && m[5] == 0x01 {
                    let p = m[7] as u16 | ((m[8] as u16) << 7);
                    if p == pid {
                        return Some(s14(m[9] as u32 | ((m[10] as u32) << 7)));
                    }
                }
            }
        }
        None
    }

    pub fn short(&mut self, bytes: &[u8]) -> Result<(), String> {
        self.out.send(bytes).map_err(|e| e.to_string())
    }
}
