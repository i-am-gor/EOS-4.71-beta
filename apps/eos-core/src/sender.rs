//! Handshaked transfer to the EOS loader: wait for its File Dump request, send the header, then every
//! packet waiting for ACK (F0 7E src 7F pkt F7); NAK (7E) or timeout -> resend (4 tries), CANCEL (7D)
//! -> abort. The loader verifies the image and asks "Burn to flash?" after the EOF message.

use midir::MidiOutputConnection;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::Receiver;
use std::sync::Arc;
use std::time::{Duration, Instant};

pub enum Progress {
    Waiting,
    Started,
    Packet(usize, usize),
    Retry(usize, &'static str),
    Done,
    Failed(String),
}

fn wait(rx: &Receiver<Vec<u8>>, kinds: &[u8], timeout: Duration, stop: &AtomicBool) -> Option<u8> {
    let t0 = Instant::now();
    while t0.elapsed() < timeout {
        if stop.load(Ordering::Relaxed) {
            return None;
        }
        if let Ok(m) = rx.recv_timeout(Duration::from_millis(20)) {
            // F0 7E <dev> <sub> ...
            if m.len() >= 4 && m[1] == 0x7e && kinds.contains(&m[3]) {
                return Some(m[3]);
            }
        }
    }
    None
}

/// Sends `msgs` (from filedump) with the loader handshake. `request_timeout` is how long to wait for
/// the sampler to be booted into "Download OS from MIDI?".
pub fn send(
    out: &mut MidiOutputConnection,
    rx: &Receiver<Vec<u8>>,
    msgs: &[Vec<u8>],
    request_timeout: Duration,
    stop: Arc<AtomicBool>,
    mut report: impl FnMut(Progress),
) -> Result<(), String> {
    while rx.try_recv().is_ok() {}
    report(Progress::Waiting);
    let _ = wait(rx, &[0x07], request_timeout, &stop); // File Dump request (07 03); send anyway on timeout
    if stop.load(Ordering::Relaxed) {
        return Err("cancelled".into());
    }
    out.send(&msgs[0]).map_err(|e| e.to_string())?;
    match wait(rx, &[0x7f, 0x7d], Duration::from_secs(5), &stop) {
        Some(0x7f) => {}
        _ => return Err("header not acknowledged: is the E4 at \"Searching for OS...\" and the MIDI input connected?".into()),
    }
    report(Progress::Started);
    let total = msgs.len() - 2;
    for (i, m) in msgs[1..msgs.len() - 1].iter().enumerate() {
        let mut ok = false;
        for _ in 0..4 {
            if stop.load(Ordering::Relaxed) {
                return Err("cancelled".into());
            }
            out.send(m).map_err(|e| e.to_string())?;
            match wait(rx, &[0x7f, 0x7e, 0x7d], Duration::from_secs(2), &stop) {
                Some(0x7f) => {
                    ok = true;
                    break;
                }
                Some(0x7d) => return Err(format!("the loader cancelled at packet {i}")),
                Some(_) => report(Progress::Retry(i, "NAK")),
                None => report(Progress::Retry(i, "timeout")),
            }
        }
        if !ok {
            return Err(format!("packet {i} failed 4 times"));
        }
        if i % 20 == 0 || i + 1 == total {
            report(Progress::Packet(i + 1, total));
        }
    }
    out.send(msgs.last().unwrap()).map_err(|e| e.to_string())?;
    report(Progress::Done);
    Ok(())
}
