//! The pan test sequence (same as tools/hw_pan_test.py / hw_lfosync_test.Rig.setup):
//! program change, select the preset/voice for editing, cord amounts 0, filter wide open, then for each
//! value: set voice Pan (editor id 40) / Multimode Pan (id 249) / send CC10, play one note, record, and
//! measure L/R RMS 300..1000 ms after the onset on every selected input pair.

use crate::audio::Recorder;
use eos_core::remote::{id, Remote};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{channel, Receiver, Sender};
use std::sync::Arc;
use std::time::{Duration, Instant};

#[derive(Clone, Copy, PartialEq, Debug)]
pub enum TestKind {
    VoicePan,
    MultiPan,
    Cc10,
}

impl TestKind {
    pub fn label(&self) -> &'static str {
        match self {
            TestKind::VoicePan => "Voice Pan (editor id 40)",
            TestKind::MultiPan => "Multimode Pan (editor id 249)",
            TestKind::Cc10 => "MIDI CC10 pan",
        }
    }
    pub fn short(&self) -> &'static str {
        match self {
            TestKind::VoicePan => "voice_pan",
            TestKind::MultiPan => "multi_pan",
            TestKind::Cc10 => "cc10",
        }
    }
}

#[derive(Clone)]
pub struct Config {
    pub midi_out: String,
    pub midi_in: String,
    pub audio_device: String,
    pub pairs: Vec<(usize, usize)>,
    pub device_id: u8,
    pub channel: u8,
    pub extra_channels: String,
    pub program: u8,
    pub key: u8,
    pub velocity: u8,
    pub prepare: bool,
    pub tests: [bool; 3],
    pub pan_values: String,
    pub cc_values: String,
}

impl Default for Config {
    fn default() -> Self {
        Config {
            midi_out: String::new(),
            midi_in: String::new(),
            audio_device: String::new(),
            pairs: vec![],
            device_id: 1,
            channel: 1,
            extra_channels: String::new(),
            program: 0,
            key: 72,
            velocity: 100,
            prepare: true,
            tests: [true, true, true],
            pan_values: "-64,-48,-40,-32,-24,-16,-8,0,8,16,24,32,40,48,63".into(),
            cc_values: "0,16,32,48,63,64,65,80,96,112,127".into(),
        }
    }
}

#[derive(Clone)]
pub struct Row {
    pub test: TestKind,
    pub value: i32,
    pub pair: (usize, usize),
    pub l_db: f64,
    pub r_db: f64,
}

pub enum Event {
    Log(String),
    Row(Row),
    Take(String, Vec<f32>, usize, u32),
    Progress(f32),
    Done(Result<(), String>),
}

fn parse_list(s: &str) -> Vec<i32> {
    s.split(|c: char| c == ',' || c.is_whitespace()).filter_map(|t| t.trim().parse().ok()).collect()
}

fn db(x: f64) -> f64 {
    20.0 * (x.max(1e-12)).log10()
}

/// Onset (frame index): first 1 ms window whose RMS over the selected channels exceeds 20 % of the max.
fn onset(d: &[f32], ch: usize, sel: &[usize], rate: u32) -> usize {
    let w = (rate as usize / 1000).max(1);
    let frames = d.len() / ch;
    let env: Vec<f64> = (0..frames / w)
        .map(|k| {
            let mut s = 0.0;
            for f in k * w..(k + 1) * w {
                for &c in sel {
                    let v = d[f * ch + c] as f64;
                    s += v * v;
                }
            }
            (s / (w * sel.len()) as f64).sqrt()
        })
        .collect();
    let mx = env.iter().cloned().fold(0.0, f64::max);
    env.iter().position(|&e| e > 0.2 * mx).unwrap_or(0) * w
}

fn rms(d: &[f32], ch: usize, c: usize, a: usize, b: usize) -> f64 {
    let frames = d.len() / ch;
    let (a, b) = (a.min(frames), b.min(frames));
    if b <= a {
        return 0.0;
    }
    let s: f64 = (a..b).map(|f| (d[f * ch + c] as f64).powi(2)).sum();
    (s / (b - a) as f64).sqrt()
}

/// Runs the test on this thread (command-line mode), printing as it goes.
pub fn run_blocking(cfg: &Config) -> Result<Vec<Row>, String> {
    let (tx, rx) = channel();
    let stop = AtomicBool::new(false);
    let r = run(cfg, &stop, &tx);
    drop(tx);
    let mut rows = vec![];
    for ev in rx {
        match ev {
            Event::Log(s) => println!("{s}"),
            Event::Row(row) => {
                println!("{:10} {:5} {:>2}/{:<2} L {:7.2} R {:7.2} L-R {:+7.2}", row.test.short(), row.value,
                         row.pair.0 + 1, row.pair.1 + 1, row.l_db, row.r_db, row.l_db - row.r_db);
                rows.push(row)
            }
            _ => {}
        }
    }
    r.map(|_| rows)
}

pub fn spawn(cfg: Config, stop: Arc<AtomicBool>) -> Receiver<Event> {
    let (tx, rx) = channel();
    std::thread::spawn(move || {
        let r = run(&cfg, &stop, &tx);
        let _ = tx.send(Event::Done(r));
    });
    rx
}

fn sleep(ms: u64) {
    std::thread::sleep(Duration::from_millis(ms));
}

fn run(cfg: &Config, stop: &AtomicBool, tx: &Sender<Event>) -> Result<(), String> {
    let mut out = eos_core::midi::open_output(&cfg.midi_out)?;
    let (_conn, mrx) = eos_core::midi::open_input(&cfg.midi_in)?;
    let rec = Recorder::open(&cfg.audio_device)?;
    let log = |s: String| {
        let _ = tx.send(Event::Log(s));
    };
    log(format!("Audio: {} channels at {} Hz.", rec.channels, rec.rate));
    for &(l, r) in &cfg.pairs {
        if l >= rec.channels || r >= rec.channels {
            return Err(format!("input pair {}/{} not available on this device", l + 1, r + 1));
        }
    }
    let ch0 = (cfg.channel - 1) & 15;
    let mut chans = vec![ch0];
    for c in parse_list(&cfg.extra_channels) {
        if (1..=16).contains(&c) && !chans.contains(&((c - 1) as u8)) {
            chans.push((c - 1) as u8);
        }
    }
    let mut rm = Remote { out: &mut out, rx: &mrx, dev: cfg.device_id };
    // Program change on every playing channel, then the editor's current preset/voice.
    for &c in &chans {
        rm.short(&[0xC0 | c, cfg.program & 0x7f])?;
    }
    sleep(500);
    if cfg.prepare {
        rm.set(223, cfg.program as i32)?; // current preset (editor)
        rm.set(225, 0)?; // current voice
        sleep(100);
        for n in 0..18 {
            rm.set(id::cord(n).2, 0)?;
        }
        rm.set(id::FILTER_TYPE, 0)?;
        sleep(150);
        rm.set(id::FILTER_FREQ, 255)?;
        rm.set(id::FILTER_Q, 0)?;
        sleep(300);
    }
    match rm.get(id::VOICE_PAN) {
        Some(v) => log(format!("E4 answers on device ID {} (voice Pan reads {v}).", cfg.device_id)),
        None => log(format!(
            "No answer from the E4 on device ID {} (check the MIDI input and the E4's MIDI device ID). Continuing.",
            cfg.device_id
        )),
    }

    let pans = parse_list(&cfg.pan_values);
    let ccs = parse_list(&cfg.cc_values);
    let kinds = [TestKind::VoicePan, TestKind::MultiPan, TestKind::Cc10];
    let jobs: Vec<(TestKind, i32)> = kinds
        .iter()
        .zip(cfg.tests.iter())
        .filter(|(_, &on)| on)
        .flat_map(|(&k, _)| {
            let vals = if k == TestKind::Cc10 { ccs.clone() } else { pans.clone() };
            vals.into_iter().map(move |v| (k, v))
        })
        .collect();
    let rate = rec.rate as usize;
    let mut prev: Option<TestKind> = None;
    for (n, &(kind, v)) in jobs.iter().enumerate() {
        if stop.load(Ordering::Relaxed) {
            return Err("stopped".into());
        }
        // Pans add up: centre voice Pan, Multimode Pan and CC10 before each test so only one moves.
        if prev != Some(kind) {
            centre(&mut rm, &chans)?;
            sleep(150);
            prev = Some(kind);
        }
        match kind {
            TestKind::VoicePan => rm.set(id::VOICE_PAN, v)?,
            TestKind::MultiPan => rm.set(id::MULTI_PAN, v)?,
            TestKind::Cc10 => {
                for &c in &chans {
                    rm.short(&[0xB0 | c, 10, v.clamp(0, 127) as u8])?;
                }
            }
        }
        sleep(250);
        rec.clear();
        let t0 = Instant::now();
        sleep(200);
        for &c in &chans {
            rm.short(&[0x90 | c, cfg.key, cfg.velocity])?;
        }
        sleep(1000);
        for &c in &chans {
            rm.short(&[0x80 | c, cfg.key, 0])?;
        }
        while t0.elapsed() < Duration::from_millis(1400) {
            sleep(10);
        }
        let d = rec.take();
        let chn = rec.channels;
        let sel: Vec<usize> = cfg.pairs.iter().flat_map(|p| [p.0, p.1]).collect();
        let on = onset(&d, chn, &sel, rec.rate);
        let (a, b) = (on + rate * 300 / 1000, on + rate * 1000 / 1000);
        for &(l, r) in &cfg.pairs {
            let row = Row { test: kind, value: v, pair: (l, r), l_db: db(rms(&d, chn, l, a, b)), r_db: db(rms(&d, chn, r, a, b)) };
            let _ = tx.send(Event::Row(row));
        }
        let _ = tx.send(Event::Take(format!("{}_{v}", kind.short()), d, chn, rec.rate));
        let _ = tx.send(Event::Progress((n + 1) as f32 / jobs.len() as f32));
    }
    // leave everything centred
    centre(&mut rm, &chans)?;
    Ok(())
}

fn centre(rm: &mut Remote, chans: &[u8]) -> Result<(), String> {
    for &c in chans {
        rm.short(&[0xB0 | c, 10, 64])?;
    }
    rm.set(id::MULTI_PAN, 0)?;
    rm.set(id::VOICE_PAN, 0)?;
    Ok(())
}
