# Noise bursts on OB-Xa lowpasses (hardware report 2026-10-17)

Report: bursts of noise at maximum resonance with LFO on cutoff, around 3502 Hz (2-pole),
915 Hz (4-pole), 801 Hz (6-pole).

## Simulation results (`tools/sweep_test.py`, real coefficient blocks from each image via Unicorn)
Static sine sweep, max resonance, highest internal stage level over all cutoffs:

| filter | stock | OB-Xa |
|---|---|---|
| 2-pole | 21.0 dB | 23.7 dB |
| 4-pole | 41.9 dB | 44.5 dB |
| 6-pole | 50.2 dB | 54.6 dB |
Other stock filters reach similar internal levels (Phaser 2 51 dB, 4th-order BP 45 dB, Vocal 45 dB).

Per-sample LFO (2 Hz, full range) at the reported cutoffs, peak level, section Q:

| filter | stock Q / sine / saw | OB-Xa Q / sine / saw |
|---|---|---|
| 2-pole @3502 | 8 / 18.2 / 15.6 dB | 10 / 19.9 / 13.3 dB |
| 4-pole @915 | 10,10 / 36.1 / 34.0 dB | **132**, 0 / 33.9 / 19.3 dB |
| 6-pole @801 | 6,6,6 / 45.5 / 44.1 dB | **42**, 0, 7 / 45.5 / 32.9 dB |

Conclusions so far:
- In an ideal (floating-point) model the OB-Xa filters are not louder than stock, even with LFO.
- Pole closeness to the unit circle alone is not the limit: stock Contrary Band-pass uses sharper poles.
- What is unprecedented is **section Q**: the ladder's resonant pair reaches Q ≈ 130 (4-pole) and 40 (6-pole);
  stock lowpass sections never exceed Q ≈ 12. A fixed-point resonator with Q in the hundreds, modulated
  per sample, is the most likely source (limit cycles / state overflow inside the chip).
- The 2-pole (Q 10 vs stock 8) does not fit that pattern as well: a stock control test is needed.

## Hardware test signals (`testsignals/`)
- `sweep_20Hz-20kHz_20s_-12dBFS.wav`, `..._-24dBFS.wav`: log sine sweep.
- `sine_801Hz / 915Hz / 3502Hz_10s_-12dBFS.wav`: steady tones at the reported cutoffs.

Procedure, for each of 2/4/6 Pole Low-pass, **first on stock 4.70, then on the OB-Xa build**:
1. Max resonance, LFO off. Play the sweep with the cutoff at the reported value. Note any noise.
2. Same with the steady tone at that frequency, LFO on cutoff (same depth/rate as before).
3. Repeat at -24 dBFS: if bursts disappear at the lower level it is overflow (headroom);
   if they stay, it is instability / limit cycles (precision).

## Hardware results (2026-10-17, OB-Xa build v1, MOTU rig, tools/hw_burst_test.py / hw_p001_test.py)
- Sine tests: no broadband noise; strong resonant ringing/pings with LFO on 4/6-pole; one ~2 ms
  internal-overload click (4-pole, 801 Hz tone, LFO +30).
- User preset 001 (sample root D2, 19.5 dB crest): full-scale clipping (0.0 dBFS) on 2/4/6-pole
  when the cutoff, statically or via filter envelope / LFO, reaches the top of the range.
- Static boundary (4-pole, no modulation): clean at F <= ~213-219 for every Q tested; clipping at
  F >= ~210-225 even for mildly resonant poles. Not a pure Q limit: the top frame frequencies
  (F 234-238) are unsafe on this chip unless heavily damped (stock uses X >= 212 there).
- True self-oscillation is not possible: the filter stages are linear with no amplitude limiting.

## v2 (`sysex/EOS470_OBXa_LP_v2.syx`, header "EOS 4.70 OB-Xa LP v2")
Each pole line is truncated at F = 210 (tools/obxa.py HI_MODE='truncate'): full constant Q kept
across the sweep (ladder Q ~130), resonant top of the filter ~9 kHz instead of ~16 kHz.
Fallback HI_MODE='stock' clamps the high frame to stock sharpness (Q tapers: 61/29/14 at 25/50/75 %).
Emulator diff test: 1158 calls, 0 failures. Open question: does the chip clamp or extrapolate when
envelope/LFO push the cutoff above 255? To be answered by the hardware rescan.

## v2 hardware results (2026-10-17, `tools/hw_rescan.py`, recordings/v2_rescan)
| test | v1 clips | v2 clips | v2 loudest |
|---|---|---|---|
| static 2/4-pole, Q127, freq 160-255, env 0/26 | 9/44 | 0/44 | -20.6 dBFS |
| static 6-pole | 7/22 | 0/22 | -27.1 dBFS |
| 4-pole boundary Q48-127, freq 184-255 | 10/40 | 0/40 | -18.8 dBFS |
| 6-pole 3208 Hz (171), env 26, LFO 0/-28, keys 62/74/86 | 17/24 (Q>=64) | 0/12 | -23.6 dBFS |
Sine + LFO +30 test (4/6-pole, 801/915 Hz): no HF events (v1 had a ~2 ms overload click).
Side effect: cutoff range compressed (top F 210), so the displayed Hz is ~10 % (log) above the real
cutoff; mid-range tones sit lower relative to cutoff than on v1.

## Sequence clicks, preset 001 (2026-10-17, recordings/seq)
Three one-sample steps per bar at note retriggers, ~30-45 dB of >8 kHz energy above floor; no clipping.
Same with a stock filter (type 18: 14 clicks vs 13), so not the OB-Xa firmware. Cause: amp envelope
attack rate 0 with the filter envelope opening the cutoff at note-on. Amp attack 1: 19 clicks,
2: 2 clicks, 3: 0 clicks. Recommendation: amp attack rate >= 3 (left at the user's 0).

## Random digital noise bursts (2026-10-17) — test-rig artefact, not the E4
Signature: trains of single-sample spikes (~1 per 1.25 ms) for 50-150 ms at random, both channels,
also seen by the user on a scope. E4 Word Clock In = ADAT (fallback Default clock 44.1 kHz).
The MOTU 828mk3 is the AD/DA for the Quantum 2626 over ADAT; opening the MOTU's audio device from
this Mac disturbed its clock and the ADAT-slaved E4 produced the bursts.
Evidence: MOTU capture 33-137 strong bursts per 30 s; Quantum 19/20 capture with the MOTU audio
untouched: 0 bursts for 4.5 min after a 30 s settle. User confirmed by ear.
Rig rule: record the E4 from Quantum inputs 19/20; never open the MOTU audio device
(hw_burst_test.DEVICE/CH). MIDI via the MOTU MIDI port is fine.

## Stock 4.70 baseline (2026-10-17, recordings/stock_rescan, Quantum 19/20)
Same 118 takes as the v2 rescan: 0 clips (v2: 0, v1: 43 of comparable takes).
Level differences at Q 127 (peak dBFS, stock vs v2): 2-pole v2 ~5-7 dB louder (constant-Q SVF keeps
its peak across the range); 4/6-pole with the cutoff at the top: stock -18 (pole fully damped, filter
effectively open) vs v2 -27 (resonant pole held at F 210, ~9 kHz, so the filter never fully opens at
high Q). 6-pole 3208 Hz + LFO: v2 louder at Q 64 (+3-7 dB), quieter at Q 127 except key 86.

## Measured frequency responses, stock vs OB-Xa v2 (2026-10-17, notes/hw_stock_vs_v2.png)
- 2-pole: v2 ≈ stock low/mid; no low-cutoff bump at Q0; resonant top capped ~9 kHz (stock ~14 kHz).
- 4/6-pole Q127: v2 peaks much narrower (ladder), peak height rises with cutoff (+27 → +41 dB vs stock
  flat ~+36), peak frequency ~0.5 oct below display mid-range.
- 4/6-pole Q0: v2 much darker than stock (4-pole −3 dB at 320 Hz for display 1776 Hz; never opens past
  ~5-7 kHz). Causes: ladder −3 dB at 0.435·ωs at k=0, plus v2 F-cap compression and uncalibrated frames.
- v3 plan: frames placed with the measured F scale so cutoff tracks the display; per-resonance-row ωs
  scaling (−3 dB = display at Q0, peak = display at max Q); allow the high frame up to stock's F_hi for
  rows no sharper than stock, cap only sharp rows at ~F 210.

## v3 hardware result (2026-10-17): clipped (47/118). Root cause found.
v3 placed frames with the measured F scale and per-row ladder correction (tracking good mid-range), but
allowed damped poles to reach high F ("top opens fully"). Stock RES16 top frames all lie on
X + 1.5*F ~ 566-570; every clipping case in v1 and v3 has a damped pole (X ~240-255) above that line
(v1/v3 pair B at (255, 222-244), v3 low-Q rows at (251-254, 229-230)). Sharp poles inside the line were
fine (v1 2-pole (204,238)). v2 was clean because its F<=210 cap kept everything on/below the line.
v3b: every stage-word half constrained to X + 1.5F <= 568 (F lowered for damped poles only); no resonance
taper, so sharp rows keep full Q and exact tracking. sysex/EOS470_OBXa_LP_v3b.syx (emulator 0 failures).

## v3b hardware result (2026-10-17, recordings/fr_v3b, recordings/v3b_rescan, notes/hw_stock_v2_v3b.png)
- Clipping rescan: 0 / 118 (boundary rule X + 1.5F <= 568 holds).
- 2-pole: tracks stock/display at Q0 and Q127; peaks +19..+21 dB.
- 4/6-pole Q127: peak frequencies on the display (1759 @ 1776, 4833 @ 5075, 13669 @ 14433), narrow ladder
  peaks (heights under-read by 1/24-oct smoothing).
- 4/6-pole Q0: much darker than stock low/mid (-3 dB 427 Hz @ display 1776; stock 1076), brighter at top.
  Model predicted ~1320 Hz: the X->r model is wrong for heavily damped / near-real poles.
- Next (v3c): calibrate damped-pole behaviour on hardware, re-place only low-resonance ladder rows.

## v3c hardware results (2026-10-18)
- Clipping rescan 0/118. Q0 4-pole identical to stock (-3 dB 285/587/1076/1709 Hz at freq 48/96/144/192),
  6-pole within a few %; Q127 identical to v3b (peaks on the display, narrow ladder peaks).
- Drive (filter parameter 3 = editor SysEx id 87, struct+6, gain word += drive<<14): no saturation at any
  setting (THD stays -74…-84 dB); level rises only +0.4…+3 dB, then the gain field wraps (2-pole open at
  127, resonant 2-pole from 80): level collapses ~35 dB into distorted noise. Stock's base gain already
  sits near the top of the field; the chip's filter stage cannot be driven into saturation this way.
  UI: "Drive" label overlapped by long Frequency values ("20000Hz") on the filter page.
- v3d = v3c without Drive (stock formatParam/numParams, dormant tables untouched):
  sysex/EOS470_OBXa_LP_v3d.syx, emulator 1158 calls / 0 failures.
- v3d on hardware (2026-10-18): clipping rescan 0/118, max peak -23.3 dBFS, within 1.9 dB of v3c per take
  (LFO/sample phase); filter page shows Frequency and Q only. Current recommended build.
