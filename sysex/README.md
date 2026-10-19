# Firmware (MIDI File Dump SysEx)

| file | header | checksum | |
|---|---|---|---|
| `EOS470-original.syx` | EOS v4.70 | 08860e57 | Original E-mu EOS 4.70 (identical to the image in E-mu's EOS470.EXE). Use to go back. |
| `EOS471-beta.syx` | EOS 4.71-beta | 0887f4e6 | EOS 4.71-beta: see `docs/CHANGELOG.md` and the 4.71-beta Operation Manual Addendum. |

Not distributed: E-mu's firmware is copyrighted. Build these locally from your own EOS470.EXE with the
flasher app (`apps/eos-flasher`) or `tools/` (see the top-level README).

Flash: send over MIDI with `tools/eos_midi.py send FILE --port "<MIDI port>"` (or the flasher app), power the
E4 on holding [Enter], answer Yes to "Download OS from MIDI?", and confirm "Burn to flash?" at the end
(about 9 minutes at MIDI speed). The E4 MIDI device ID must be the one the loader expects (handshake).

## Transwave samples (SLpScn): size guidelines
SLpScn slides the sample's loop window through the sample while the note plays. How you build the sample
decides how far it can travel and how many waveforms (frames) it can reach.

**Rules**
- **Minimum 2 samples of silence first.** Every transwave sample must begin with at least 2 samples of
  silence before frame 1: the E4 does not allow a loop to start before sample 2 (the loop editor stops
  at Start 2). Without this lead-in, frame 1 cannot be the loop, and the frame grid is off by 2 samples.
  With it, the loop sits on frame 1 at Start 2, End 2 + frame size.
- **Equal frames.** Make every frame exactly the loop (window) length. For click-free single-cycle frames,
  start each one at a zero crossing.
- **Loop on the first frame**, forward or alternating loop type. Other loop types are left alone.
- **Travel limit: 32,767 samples.** EOS keeps the loop shift in a 16-bit value, so the window can move at
  most 32,767 samples from where the loop is set (about 0.74 s at 44.1 kHz, 0.68 s at 48 kHz). The patch
  also keeps the loop inside the sample.
- **Keep the whole sample within reach**: sample length ≤ 2 + 32,768 samples (with the loop on frame 1).
  Longer samples still play, but SLpScn's range is scaled to the whole sample, so the part of the
  controller travel aimed beyond the reachable area just holds at the limit.

**Maximum number of frames** (loop on frame 1; frames × frame size ≤ 32,768)

| Frame size (samples) | Max frames | Sample length | Frame-1 pitch at 44.1 kHz |
|---|---|---|---|
| 64 | 512 | 32,770 | 689.1 Hz |
| 128 | 256 | 32,770 | 344.5 Hz |
| 256 | 128 | 32,770 | 172.3 Hz |
| 512 | 64 | 32,770 | 86.1 Hz |
| 1,024 | 32 | 32,770 | 43.1 Hz |
| 2,048 | 16 | 32,770 | 21.5 Hz |
| 4,096 | 8 | 32,770 | 10.8 Hz |

Sample length = 2 + frames × frame size. Fewer frames are fine; the scan always spans the whole sample.
Frame-1 pitch is just the loop's natural pitch (sample rate ÷ frame size); set the root key so it plays
in tune. Bigger frames suit lower pitches and hold more detail. Smaller frames give more frames, but the
E4's resampling dulls high harmonics more when a frame has few samples per cycle.

**Control**
- **Range:** one cord at **+100** from a full-scale source (mod wheel at 127, Lfo1+ at peak, an envelope
  at full) moves the window from frame 1 to the end of the sample; **−100** moves it towards the start.
  Smaller amounts cover proportionally less, and extra cords add together.
- **Resolution:** the window position updates every 10 ms. A MIDI controller has 128 steps, so on a
  128 × 256 table each mod-wheel step moves about one frame (≈ 256 samples); on 32 × 256 it's about
  62 samples per step.
- **Character:** positions between frames blend the two neighbours, with the slightly gritty,
  Ensoniq-like sound of a moving loop. There's no crossfade.
- **Other loop cords:** stock SLoop cords on the same voice still add their small fine offset
  (about 127 samples per full cord).

**Example:** `testsignals/wavetable/wt32x256_harmonics_pad2.wav` has 2 lead-in samples and 32 frames of
256 samples (8,194 samples total), with the loop at 2–258. Use Mod Wheel → SLpScn +100.
