//! MIDI port helpers (midir). Incoming SysEx messages are forwarded to a channel.

use midir::{Ignore, MidiInput, MidiInputConnection, MidiOutput, MidiOutputConnection};
use std::sync::mpsc::{channel, Receiver};

pub fn output_names() -> Vec<String> {
    let Ok(m) = MidiOutput::new("eos-out-list") else { return vec![] };
    m.ports().iter().filter_map(|p| m.port_name(p).ok()).collect()
}

pub fn input_names() -> Vec<String> {
    let Ok(m) = MidiInput::new("eos-in-list") else { return vec![] };
    m.ports().iter().filter_map(|p| m.port_name(p).ok()).collect()
}

pub fn open_output(name: &str) -> Result<MidiOutputConnection, String> {
    let m = MidiOutput::new("eos-out").map_err(|e| e.to_string())?;
    let port = m
        .ports()
        .into_iter()
        .find(|p| m.port_name(p).map(|n| n == name).unwrap_or(false))
        .ok_or(format!("MIDI output '{name}' not found"))?;
    m.connect(&port, "eos-out").map_err(|e| e.to_string())
}

/// Opens an input; every complete SysEx message (F0..F7) arrives on the returned receiver.
pub fn open_input(name: &str) -> Result<(MidiInputConnection<()>, Receiver<Vec<u8>>), String> {
    let mut m = MidiInput::new("eos-in").map_err(|e| e.to_string())?;
    m.ignore(Ignore::TimeAndActiveSense);
    let port = m
        .ports()
        .into_iter()
        .find(|p| m.port_name(p).map(|n| n == name).unwrap_or(false))
        .ok_or(format!("MIDI input '{name}' not found"))?;
    let (tx, rx) = channel();
    let mut partial: Vec<u8> = Vec::new();
    let conn = m
        .connect(
            &port,
            "eos-in",
            move |_, msg, _| {
                // assemble SysEx that some drivers deliver in pieces
                if msg.first() == Some(&0xf0) {
                    partial.clear();
                }
                if msg.first() == Some(&0xf0) || !partial.is_empty() {
                    partial.extend_from_slice(msg);
                    if partial.last() == Some(&0xf7) {
                        let _ = tx.send(std::mem::take(&mut partial));
                    }
                }
            },
            (),
        )
        .map_err(|e| e.to_string())?;
    Ok((conn, rx))
}
