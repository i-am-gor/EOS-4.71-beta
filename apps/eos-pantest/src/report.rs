//! Verdicts, saving (CSV + WAV) and the GitHub issue report.

use crate::audio::DeviceInfo;
use crate::test::{Config, Row, TestKind};

pub const REPO: &str = "rfidmusic/EOS-4.71-beta";
const HARD_DB: f64 = 60.0; // one side more than 60 dB down = hard panned
const CENTRE_OK_DB: f64 = 0.1; // |L - R| at centre within this = balanced (4.70 / 4.71-beta: about -0.24 dB)

/// Per test: where the sweep first reaches hard left / hard right, and what that means.
pub fn verdicts(rows: &[Row]) -> Vec<String> {
    let mut out = vec![];
    for kind in [TestKind::VoicePan, TestKind::MultiPan, TestKind::Cc10] {
        let rs: Vec<&Row> = rows.iter().filter(|r| r.test == kind).collect();
        if rs.is_empty() {
            continue;
        }
        let pair = rs[0].pair;
        let main: Vec<&&Row> = rs.iter().filter(|r| r.pair == pair).collect();
        let centre = if kind == TestKind::Cc10 { 64 } else { 0 };
        let hard_l = main.iter().filter(|r| r.l_db - r.r_db > HARD_DB).map(|r| r.value).max();
        let hard_r = main.iter().filter(|r| r.r_db - r.l_db > HARD_DB).map(|r| r.value).min();
        let (lo, hi) = if kind == TestKind::Cc10 { (0, 127) } else { (-64, 63) };
        let text = match (hard_l, hard_r) {
            (Some(l), Some(r)) => {
                let reach = (centre - l).max(r - centre);
                if (centre - l) <= 32 && (r - centre) <= 32 {
                    format!("{}: hard left already at {l}, hard right at {r} -> pan reaches the ends at half range (EOS 4.70 pan bug present)", kind.label())
                } else if l <= lo + 1 && r >= hi - 1 {
                    format!("{}: hard left only at {l}, hard right only at {r} -> full pan range (fixed, as in EOS 4.71-beta)", kind.label())
                } else {
                    format!("{}: hard left at {l}, hard right at {r} (reach {reach} steps from centre)", kind.label())
                }
            }
            _ => format!("{}: did not reach hard left/right in the measured values (check the outputs and levels)", kind.label()),
        };
        out.push(text);
        if let Some(c) = main.iter().find(|r| r.value == centre) {
            let d = c.l_db - c.r_db;
            out.push(if d.abs() <= CENTRE_OK_DB {
                format!("{}: centre ({centre}) balanced, L-R {d:+.2} dB (as in EOS 4.71-beta2)", kind.label())
            } else {
                format!(
                    "{}: centre ({centre}) L-R {d:+.2} dB ({} louder; EOS 4.70 and 4.71-beta are about 0.24 dB right-heavy)",
                    kind.label(),
                    if d < 0.0 { "right" } else { "left" }
                )
            });
        }
    }
    out
}

pub fn csv(rows: &[Row]) -> String {
    let mut s = String::from("test,value,input_l,input_r,l_db,r_db,l_minus_r_db\n");
    for r in rows {
        s += &format!(
            "{},{},{},{},{:.2},{:.2},{:.2}\n",
            r.test.short(),
            r.value,
            r.pair.0 + 1,
            r.pair.1 + 1,
            r.l_db,
            r.r_db,
            r.l_db - r.r_db
        );
    }
    s
}

pub fn save(dir: &std::path::Path, rows: &[Row], takes: &[(String, Vec<f32>, usize, u32)], fw: &str, notes: &str) -> Result<usize, String> {
    let mut n = 0;
    std::fs::write(dir.join("pan_test.csv"), csv(rows)).map_err(|e| e.to_string())?;
    n += 1;
    std::fs::write(dir.join("pan_test_summary.txt"), format!("firmware: {fw}\n{}\n\nnotes:\n{notes}\n", verdicts(rows).join("\n")))
        .map_err(|e| e.to_string())?;
    n += 1;
    for (name, data, ch, rate) in takes {
        let spec = hound::WavSpec { channels: *ch as u16, sample_rate: *rate, bits_per_sample: 32, sample_format: hound::SampleFormat::Float };
        let mut w = hound::WavWriter::create(dir.join(format!("{name}.wav")), spec).map_err(|e| e.to_string())?;
        for &s in data {
            w.write_sample(s).map_err(|e| e.to_string())?;
        }
        w.finalize().map_err(|e| e.to_string())?;
        n += 1;
    }
    Ok(n)
}

fn enc(s: &str) -> String {
    let mut o = String::with_capacity(s.len() * 3);
    for b in s.bytes() {
        match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => o.push(b as char),
            _ => o += &format!("%{b:02X}"),
        }
    }
    o
}

/// URL of a pre-filled "Pan test report" issue in the project repository.
pub fn issue_url(rows: &[Row], fw: &str, notes: &str, cfg: &Config, dev: Option<&DeviceInfo>) -> String {
    let mut body = String::new();
    body += &format!("### Pan test report\n\n**Firmware:** {fw}\n**App:** eos-pantest {}\n**OS:** {}\n",
        env!("CARGO_PKG_VERSION"), std::env::consts::OS);
    body += &format!("**Program/key/velocity:** {}/{}/{}  **E4 device ID:** {}  **MIDI channel:** {}{}\n",
        cfg.program, cfg.key, cfg.velocity, cfg.device_id, cfg.channel,
        if cfg.extra_channels.trim().is_empty() { String::new() } else { format!(" (+{})", cfg.extra_channels.trim()) });
    if let Some(d) = dev {
        body += &format!("**Audio input:** {}\n", d.label());
    }
    body += "\n#### Verdict\n";
    for v in verdicts(rows) {
        body += &format!("- {v}\n");
    }
    body += "\n#### Measurements (L/R RMS 300-1000 ms after the onset)\n\n| test | value | inputs | L dB | R dB | L-R dB |\n|---|---|---|---|---|---|\n";
    for r in rows {
        body += &format!("| {} | {} | {}/{} | {:.2} | {:.2} | {:+.2} |\n", r.test.short(), r.value, r.pair.0 + 1, r.pair.1 + 1, r.l_db, r.r_db, r.l_db - r.r_db);
    }
    body += &format!("\n#### Notes\n{}\n", if notes.trim().is_empty() { "(none)" } else { notes.trim() });
    // keep the URL within what browsers and GitHub accept
    if body.len() > 6000 {
        body.truncate(6000);
        body += "\n… (table truncated: attach pan_test.csv)\n";
    }
    let title = format!("Pan test report: {fw}");
    format!("https://github.com/{REPO}/issues/new?template=pan-test-report.md&labels=pan-test-report&title={}&body={}", enc(&title), enc(&body))
}

pub fn open_browser(url: &str) -> Result<(), String> {
    #[cfg(target_os = "macos")]
    let r = std::process::Command::new("open").arg(url).spawn();
    #[cfg(target_os = "windows")]
    let r = std::process::Command::new("rundll32").args(["url.dll,FileProtocolHandler", url]).spawn();
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    let r = std::process::Command::new("xdg-open").arg(url).spawn();
    r.map(|_| ()).map_err(|e| e.to_string())
}
