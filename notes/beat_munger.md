# Beat Munger ("Beat Machine") in EOS 4.71-beta2 (static trace, 2026-10-21)

C = confirmed in code, I = inferred. Menu entry and dispatch entry spot-checked.

## Where
- Sample Edit > Cool Tools (Tools4) slot 6: menu entry 0xA4CA8 "Beat Machine" / "BeatM", handler 0xB5150 (checked);
  page title "Beat Munger". Op code 0x20, dispatch entry 0xFBBB6 (prep 0xE483C = rts, exec 0xE4840) (checked).
- Handler: needs >= 4000 frames, rate <= 48 kHz, free sample RAM for audition; runs the first analysis
  (0xB4DD4, no tempo hint), sets the 16 bar-edit steps to on (0x10003EA0..EAF).

## Parameters (descriptor table 0xB6DD2, 34-byte entries)
| parameter | RAM | range | meaning |
|---|---|---|---|
| Tempo | 0x10003ECA (×10) | 55.0–180.0 bpm, starts at the detected tempo | target tempo (time-stretches the slices, I) |
| Swing | 0x10003EC2 | −75..+75 % | swing amount |
| (feel) | 0x10003EC3 | fast / norm / slow | swing feel / rate (I); "xslow" string unreachable |
| Metronome Level | 0x10003EC6 | 0..10 | audition click, 0 = off |
| Process Adj | 0x10003EC4 | 0..50 (×1 ms, clamped 0.2–80 ms) | probably splice/crossfade length (I) |
| (second time) | 0x10003EC5 | 8..80 ms | probably analysis/window length (I) |
| downbeat `<n>` | 0x10003EC9 | 0..10 (≤ candidates − 1) | choose among downbeat candidates |
| Loop … to … | 0x10003ECC / ECE | bars 1..found | bar range looped |
| bar edit | 0x10003EA0..EAF | 16 × x / _ | per-bar 16-step on/off pattern (mutes 16ths, I) |
Soft keys (0xB71F8): Stop, Play (realtime audition), re-Anlyz ("Tempo Estimate?" dialog, hint ≥ 75 bpm), OK (render).
"Use sample length for phrase length?" appears when the sample looks cropped to whole beats (refits the period).

## Analysis (AudioAnalyzer.C, 0xE3E70 -> 0xE7EBC -> analyzer 0xE93A0 / stages 0xE98E4)
- Input: the whole current sample (not the region), stereo mixed to mono; > 24 kHz analysed at half rate.
- FFT per 200-frame hop -> one novelty value per hop (spectral flux, I); onset peaks > 0.09 × max with hysteresis,
  up to 10,000 onsets (frames); tempo/beat search 60–180 bpm (autocorrelation, time signature, downbeat candidates);
  onsets closer than 30 ms merged.
- Results: BeatData (0x278 bytes): +0x254 beat period (frames), +0x258 tempo (float), +0x25C/+0x260 beats per
  bar, +0x264 rate. Slice list in BeatPlayer (0x242 bytes, pointer 0x100042F4): +0x23A count, +0x23E array of
  sample-RAM addresses `(base | 0x40000000) + frame × channels × 2` (transient slices, not a grid). Freed when the
  page is left (0xB6080 -> 0xE4074) or after render.

## Output
- OK renders offline through the same BeatPlayer into a **new sample** (first free slot 1..999, 0xE46C0; header
  copied, start/end/loop = whole, flag 0x4000, commit 0x13DA58). The original is untouched. No SysEx export.

## Slicer from it (not built)
- After analysis and before exit, `*(0x100042F4)` +0x23A/+0x23E gives the slice frames; BeatData +0x254 gives a grid.
- No existing code splits one sample into many; the render path (0xE46C0 / 0xE45F0 / 0x13DA58) is the template for
  "new sample from frames a..b". Preset helpers exist ("Adding Sample Zone" 0xC76C0, "Expand SampleZones"
  0xC7AEA/0xC7C18, "Split Voice" 0xCB246).
- Estimate: per-slice sample creation ~400–700 bytes, plus ~300–600 for an auto-mapped preset. A spare soft-key slot
  in 0xB71F8 could hold "Slice". Needs space freed first (beta2 has ~120 bytes left in scattered pieces).
