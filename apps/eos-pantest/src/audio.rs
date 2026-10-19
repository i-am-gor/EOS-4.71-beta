//! Audio input via cpal: device listing and multi-channel recording of selected channels.

use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use std::sync::{Arc, Mutex};

#[derive(Clone)]
pub struct DeviceInfo {
    pub name: String,
    pub channels: u16,
    pub rate: u32,
}

impl DeviceInfo {
    pub fn label(&self) -> String {
        format!("{} ({} ch, {} Hz)", self.name, self.channels, self.rate)
    }
}

pub fn input_devices() -> Vec<DeviceInfo> {
    let host = cpal::default_host();
    let Ok(devs) = host.input_devices() else { return vec![] };
    devs.filter_map(|d| {
        let name = d.name().ok()?;
        let c = d.default_input_config().ok()?;
        Some(DeviceInfo { name, channels: c.channels(), rate: c.sample_rate().0 })
    })
    .collect()
}

/// A running input stream that appends every frame's channels to a shared buffer.
pub struct Recorder {
    _stream: cpal::Stream,
    pub buf: Arc<Mutex<Vec<f32>>>,
    pub channels: usize,
    pub rate: u32,
}

impl Recorder {
    pub fn open(name: &str) -> Result<Recorder, String> {
        let host = cpal::default_host();
        let dev = host
            .input_devices()
            .map_err(|e| e.to_string())?
            .find(|d| d.name().map(|n| n == name).unwrap_or(false))
            .ok_or(format!("audio input '{name}' not found"))?;
        let sc = dev.default_input_config().map_err(|e| e.to_string())?;
        let channels = sc.channels() as usize;
        let rate = sc.sample_rate().0;
        let cfg: cpal::StreamConfig = sc.clone().into();
        let buf = Arc::new(Mutex::new(Vec::<f32>::new()));
        let err = |e| eprintln!("audio error: {e}");
        let stream = match sc.sample_format() {
            cpal::SampleFormat::F32 => {
                let b = buf.clone();
                dev.build_input_stream(&cfg, move |d: &[f32], _| b.lock().unwrap().extend_from_slice(d), err, None)
            }
            cpal::SampleFormat::I16 => {
                let b = buf.clone();
                dev.build_input_stream(
                    &cfg,
                    move |d: &[i16], _| b.lock().unwrap().extend(d.iter().map(|&s| s as f32 / 32768.0)),
                    err,
                    None,
                )
            }
            cpal::SampleFormat::I32 => {
                let b = buf.clone();
                dev.build_input_stream(
                    &cfg,
                    move |d: &[i32], _| b.lock().unwrap().extend(d.iter().map(|&s| s as f32 / 2147483648.0)),
                    err,
                    None,
                )
            }
            f => return Err(format!("unsupported sample format {f:?}")),
        }
        .map_err(|e| e.to_string())?;
        stream.play().map_err(|e| e.to_string())?;
        Ok(Recorder { _stream: stream, buf, channels, rate })
    }

    /// Clears the buffer (start of a take).
    pub fn clear(&self) {
        self.buf.lock().unwrap().clear();
    }

    /// Interleaved samples recorded since the last clear.
    pub fn take(&self) -> Vec<f32> {
        std::mem::take(&mut *self.buf.lock().unwrap())
    }
}
