# Interpolated resonance + "4 Pole LP+Fuzz" (test build "EOS 4.71 LPFuzz T", 2026-10-19)

Source `patches/lpfuzz/lpfuzz.s`, builder `tools/build_lpfuzz.py build/eos471_beta.bin OUT`, emulator
`tools/emu_lpfuzz.py`, hardware `tools/hw_lpfuzz_test.py`. Our own code and coefficients only (no E-mu P2K data).

## Space
Filter registry ctor (0x67F98) rewritten as a loop over a word vtable list; 856 / 1,112 bytes used.

## Interpolated resonance (switch bit 0)
The OB-Xa pole tables step every 4 Q values (SVF/LADA, HP/BP table A) or 8 (LADB, HP/BP table B). `lerp` blends
each byte (X/F, both frames) between entries i and i+1: v = a + ((b − a)·f >> shift). Q multiples of 4/8 give the
table values exactly; bit 0 off = stock 4.71. Hooks: OB-Xa LP `words` 0x65E5A, HP/BP/CBP `apply` 0x6684E.
Level compensation was already continuous (packQ returns q·k >> 7); the note-on gain word keeps 16 steps.

## 4 Pole LP+Fuzz (type 0x03, menu index 21, 23 filters)
- Q ("Fuzz") = OB-Xa 4-pole ladder at **Q/2** (half the normal resonance curve; LP4's gain word and level
  compensation at that Q) **plus** a drive stage: pole pair in word 0, the same pair as a zero in word 1
  (cancels: flat when linear; the level between the stages rises with Q and can overload the chip).
  X = 255 − (255 − XMIN)·Q/127, F = FD, both frames equal; ladder in words 4/8, word 5 neutral, word 9 gain.
- Frequency = the ladder cutoff (realtime, FilFreq); Q realtime (FilRes) through packQ.
- Registry: count moved 0x258 → 0x25C (ctor tail 0x6841A, FUN_00068458 0x6846E/0x6848E, FUN_000684A0 0x684B0),
  allocation 0x25C → 0x260 (0x6843A); filter-type descriptors 0x5AC48 / 0x6B58E max 20 → 21.
- Test variants (parameter 195, max raised to 31): bits 1-2 FD 8/40/96/150 (~100 Hz / 200 Hz / 700 Hz /
  2.4 kHz), bit 3 XMIN 0x90/0x60, bit 4 no cancelling zero. To be frozen after the hardware test.

## Verification
Emulator: 16,711 checks / 0 failures — registry (23 objects, stock order, type 3, lookups both ways), every OB-Xa
LP/HP/BP/CBP method identical to 4.71 with interpolation off and equal to the byte model with it on (all Q),
LP+Fuzz in all 32 switch values, display ("Fuzz"), switch range, descriptors, image diff. Mutations caught
(byte mask 4,842 failures, drive F 1,032, type ID 4). OB-Xa 1,158/0, LFO 51,395/0, Transwave 6,011/0,
cords 13,004/0, RFX 12,300/0, HP/BP slot list unchanged from 4.71.
`sysex/EOS471-LPFuzz-test.syx` checksum 088809e9.

## Hardware result (2026-10-20, recordings/lpfuzz)
- Filter type 21 selectable over SysEx (set 21, reads 21); switch 0..31 reads back.
- **Interpolated resonance works**: 4 Pole Low-pass, cutoff 100, Q 0..127 step 1 (801.7 Hz sine):
  interpolation off 91 / 127 flat steps, largest jump 4.8 dB; on 42 / 127 flat steps, largest 2.5 dB
  (remaining flat steps are mostly at levels near the noise floor at this cutoff).
- **LP+Fuzz silent** (−99 dBFS) at every switch value, even at Q 0 where the drive stage is X = 0xFF; LP4
  before/after −56.6 dBFS. Level at Q 0 vs the drive F byte: F 8 / 40: silent; F 96: −96; F 150: −78 with the
  zero, −60 without (≈ LP4). => **X = 0xFF is not a neutral stage on the chip unless F = 0xCF**: 0xFFCF is
  neutral as a pair. The model in tools/eos_filter.py (r from X only, a1 = −2 r cos θ) is wrong here, which
  also explains the poor model/hardware agreement of the 6-pole P2K fits.
- Next: characterise single stages on hardware (one stage word set over SysEx, others neutral, sine sweep)
  to get the real X/F → response law before designing the drive stage; or keep the drive stage on the
  neutral line (start at 0xFFCF) and move only along measured directions.

## Why LP+Fuzz v1 was silent, and the v2 direction (2026-10-20)
The drive stage at Q 0 was X = 0xFF with a low F: by the measured law (notes/filter_format.md) that is an extremely
overdamped lowpass with its corner far below the audio band (−30…−70 dB), and the "cancelling" zero is normalised
differently, so nothing cancelled. Broadband pre-gain from zero stages is limited to +6.3 dB each (F 0xE0); the
chip clipped nowhere up to +31 dB of resonant gain. A usable fuzz therefore has to be **resonant overdrive**:
the ladder resonance (Q/2) plus an extra sharp pole tuned with the cutoff and the zero-stage boost, with the gain
word bringing the level back, so the chip overloads at the resonance as Q rises.

## LP+Fuzz v2 hardware result (2026-10-20, recordings/lpfuzz2, "EOS 4.71 LPFuzz2 T", 0887fd7c)
Type 21 reads back; switch 0..31 reads back. 801.7 Hz sine, cutoffs 96/128/255, Q 0..127 step 16.
- **Zero boost (bit 1) produces real fuzz**: at cutoff 96/128 the output pins at a fixed ceiling, peak −22.6 dBFS
  (vs −50 dBFS clean), 99.7 % of samples within 3 % of the peak; odd harmonics H3/H5/H7 −8.9/−13.1/−16.2 dB
  (ideal square −9.5/−14.0/−16.9), even harmonics ≤ −61 dB => **symmetric hard saturation, not wraparound**.
  Inharmonic energy −19 dB = aliasing of the clipped square (no band-limiting inside the chip).
- Already saturated from Q ≈ 32 (Q 0: softer, 73 % at peak, H3 −11 dB). **Q is not a drive control**: the boost is
  ~+30 dB regardless of Q, far more than the +6.3 dB per zero stage of the single-stage law (zeros active via
  SETMODE 0xC0 changes more than word 1 — to investigate).
- **Cutoff 255: no boost at all** in every bit-1 variant (−50 dBFS, clean) — ladder F at the top wraps (F ≥ 0xE0).
- Gain compensation (bit 4) only lowers the output after the clip at Q ≥ 112 (clip happens before word 9).
- Tracking pole (bit 2, Qmax 20/50) alone: up to +10 dB resonant peak at cutoff 128, clean (THD −65 dB); no clip.
- Ladder at Q/2 only (bit 0): clean, −52..−70 dBFS.
=> Next (v3): keep the zero boost as the clip engine, add a **pre-attenuation that falls with Q** (drive control,
e.g. an overdamped pole in word 0 whose F rises with Q, or the boost-zero F lowered at low Q), keep the ladder after
the clip for tone, fix the cutoff-255 wrap (cap ladder F < 0xE0), and find what SETMODE 0xC0 does to the other words.

## LP+Fuzz v3 (test build "EOS 4.71 LPFuzz3 T", checksum 088801cc, sysex/EOS471-LPFuzz3-test.syx)
- Words 0/4: LP4 at Q/2, F bytes of both frames capped at 0xDF. Note: the ladder's **high frame at low Q is
  0xFFCF (neutral)** (LADA/LADB entries 0..13), so cutoff 255 = ladder fully neutral; v2's missing fuzz there was
  not an F wrap. The high frame F only exceeds 0xDF at Q >= 112 (LADA 14+: 0xE0..0xE8), where the cap now applies.
- Words 1/5 (bit 1): zero stages X 0xFF, F = FLO + ((0xE0 - FLO) Q >> 7), FLO 0xCF/0x90/0x50/0x10 (bits 2-3):
  pre-attenuation falling as Q rises; SETMODE 0xC0. Word 8 neutral (tracking pole dropped: clean in v2).
- Word 9: LP4 gain minus DTAB[Q >> 3] (bit 4, 96 steps at Q 0 -> 0 at Q 120+): gain-word drive before the clip.
- Emulator 16,711/0; mutations caught (cap 480, FLO 504, F shift 2,004, drive bit 1,920); OB-Xa 1,158/0,
  LFO 51,395/0, Transwave 6,011/0, cords 13,004/0, RFX 12,300/0. LM Studio review: 3 findings, all false positives.
- Hardware test: tools/hw_lpfuzz_test.py OUT 1,3 (8 variants, cutoffs 96/128/200/255).

## LP+Fuzz v3 hardware result (2026-10-20, recordings/lpfuzz3)
Type 21 and switch 0..31 read back. Peak dBFS vs Q (801.7 Hz sine); clip ceiling −23.3 dBFS (THD −7.4 = near-square).
- **Q now controls the drive.** Best: **sw7 (zeros FLO 0x90, no gain drive)**: at cutoff 96/128 Q 0 = the plain
  LP level (−53 dBFS, same as the ladder alone), then +5..7 dB per 16 Q, clean up to −25 dBFS (THD −80), clip onset
  at Q 80 (cut 128) / 96 (cut 96), near-square by Q 112..127. FLO 0x50 / 0x10 move the onset to Q 96..112 / 112..127.
- Gain drive (bit 4) gives a wider ramp (~10 dB per 16 Q) but Q 0 is 25..30 dB quieter than the plain filter
  (−80 dBFS): worse as a single knob. FLO 0xCF (v2-like) clips from Q 0..32.
- **Cutoff dependence:** no variant clips at cutoff 200 (max −33.8 dBFS at Q 127, clean) or 255. The large boost
  only exists at the ladder's low frame (zeros active + low-frame ladder words); at the high frame (neutral ladder) the
  zero stages give only their broadband law (≤ +6.3 dB each, and attenuation at low F: sw7 cut 255 Q 0 −83 dBFS).
  So with a −50 dBFS test sine the fuzz works up to cutoff ~128..200; hotter samples will clip at higher cutoffs.
- Quiet cells (≤ −80 dBFS) show THD near 0 dB: noise floor, not distortion.
=> Recommended freeze: sw7 behaviour (FLO 0x90, interpolation on, no gain drive, F cap), as "4 Pole LP+Fuzz".

## Boost mechanism and LP+Fuzz v4 (test build "EOS 4.71 LPFuzz4 T", checksum 088802af)
SETMODE (0x10D3B0) writes flags bit 0x80 into the **previous block's** mode byte (+0x7B, bit 7) and
table[n & 3] | (flags & 0x7F) into the own block's. Model that fits v3: with zeros active, a pole word and its
zero word form one section poly_zero / poly_pole (no w0^2 normalisation of the pole), i.e. relative to the
single-stage law an extra (8060 Hz / f_pole)^2 per section. Check against v3 sw7: Q ramp +20.2 / +27.8 dB predicted
at Q 64 / 80 (measured +20.8 / +27.6); extra gain ~+38 dB at cutoff 96..128, +18 at 200, ~+6 at 255 (pole high
frame 0xFFCF ~ 7.9 kHz). So an open filter can only get ~(11.6 kHz / f_corner)^2 per section: fuzz at cutoff 255
needs the ladder high frame lower. v4: high-frame F capped FH 0xDF/0xB8/0xA0/0x90 (bits 2-3), zero FLO 0x90 /
0x50 (bit 4), gain drive and dtab removed. Emulator 16,807/0 (Q 127 added); mutations FH 1,056, FLO 960, wrong byte
3,312 caught; the low-frame cap is never active (low-frame F <= 0x08), so its mutation is equivalent. OB-Xa, LFO,
Transwave, cords, RFX all 0 failures. Trade-off: the cutoff range of LP+Fuzz tops out at ~FH.

## LP+Fuzz v4 hardware result (2026-10-20, recordings/lpfuzz4)
Type 21 / switch read back. Clip onset Q (peak −23.3 dBFS, 801.7 Hz test sine at ~−50 dBFS clean):

| variant | cut 96 | cut 128 | cut 200 | cut 255 |
|---|---|---|---|---|
| FH DF, FLO 90 (= v3 sw7) | 96 | 80 | none (−33.8 at 127) | none (−50.8) |
| FH B8, FLO 90 | 112 | 48 | 127 | none (−39.2) |
| FH A0, FLO 90 | 127 | 80..96 | 96 | none (−28.8) |
| **FH 90, FLO 90** | 127 | 96..112 | **64** | **127** |
| FH A0, FLO 50 | 127 | 112 | 112 | none (−29.3) |

- Lowering the high frame moves the overload up the cutoff range as the model predicted; FH 0x90 (~2 kHz top corner)
  is the only one that clips at 255 (just, at Q 127) with this quiet test sine; hotter samples clip earlier.
- Cutoff 255 is quieter than 200 in every capped variant: the high frame is the heavily damped X 0xFF pole at FH
  (corner ~w0^2/b), while mid-morph frames have less damping. Lowering the high-frame X (e.g. 0xD0) would add
  ~+6..8 dB per section at 255 without lowering FH further (adds a mild resonance at FH) — untested.
- FLO 0x50 delays the onset (flat until Q 64) and is otherwise similar.

## v4 FH 0x90 (sw15) with the sine-sweep sample (2026-10-20, recordings/lpfuzz4_fr, tools/hw_lpfuzz_fr.py +
## tools/lpfuzz_fr_analyze.py)
Key 77 sweep (−12 dBFS, much hotter than the 801.7 Hz test sine) held 20 s, one sweep per cutoff/Q (96/128/200/255 ×
Q 0..127 step 16). Every take reaches the −23.6 dBFS ceiling somewhere. Per frequency:
- **A narrow overload peak sits at the morphed pole frequency at every Q, including Q 0**: ~250 Hz (cut 96),
  ~500 Hz (128), ~1 kHz (200), ~2 kHz (255 = FH). THD there −3..−8 dB even at Q 0. This is the section
  poly_zero / poly_pole at w = w0: |poly_pole| ~ b·w0 is small, so the peak ~ |poly_zero(w0)| / (b w0) is huge.
- Below the cutoff the passband saturates as Q rises: cut 96 from Q 32..48, cut 128 from Q 64..80, cut 200 from
  Q 112, cut 255 never (63 Hz peak −24.4 at Q 127). Above the cutoff: clean lowpass roll-off.
- So v4 is a "screaming" resonant LP: never clean at Q 0. Note: the flat reference (menu 8) read back type 0 in this
  23-filter build, so ref_start/ref_end are a lowpass, not flat; the analysis uses absolute levels.
- v5 idea: make section 0/1 transparent at Q 0 by setting the zero word = the ladder pole word (poly/poly = 1), and
  interpolate its bytes (both frames) toward X 0xFF / F 0xE0 as Q rises (controlled peak + passband boost); keep
  word 5 neutral so section 4/5 is the normal LADB 2-pole; optionally a pole copy in word 8 to restore 4 poles.

## LP+Fuzz v5 (test build "EOS 4.71 LPFuzz5 T", checksum 08880064, sysex/EOS471-LPFuzz5-test.syx)
Section 0/1 transparent at Q 0: word 1 = word 0 + (0xFFE0FFE0 − word 0)·Q/127 per byte (zlerp), zeros active
(SETMODE 0xC0) with bit 1. Word 5 neutral or (bit 2) = word 4; word 8 neutral or (bit 3) = word 4 (normal pole pair,
no zero partner); bit 4 high-frame cap 0x90 (else 0xDF). Note: with zeros active a neutral word 5 is expected to give
section 4/5 the same (wn/w0)^2 peak as v4 (no normalisation), hence the bit-2 alternative. Emulator 16,807/0;
mutations target 1,104, divisor 1,728, word-5 source 1,824, word-8 bit 2,112, FH 2,112 caught; OB-Xa, LFO, Transwave,
cords, RFX 0 failures. Hardware: hw_lpfuzz_fr.py OUT SW for SW 15 (5 = copy, 8 = pole), 11 (5 neutral, 8 pole),
31 (15 + FH 0x90).

## Decision (2026-10-21): menu position
LP+Fuzz stays **last in the filter menu (menu index 21, after Peak/Shelf Morph) in the release too**, so the menu
indexes of all stock filters (0..20) stay unchanged for SysEx editors and existing setups. Type ID 0x03.

## LP+Fuzz v5 sweep results (2026-10-21, recordings/lpfuzz5_fr_sw{15,11,31}, hw_lpfuzz_fr.py + lpfuzz_fr_analyze.py)
Clip ceiling −23.6 dBFS; THD at clip −5.5..−7.5 dB.
- **sw15** (word 1 moving zero, word 5 = word 4, word 8 = pole, FH 0xDF): **clean at Q 0 at every cutoff**
  (peak ~−51 dBFS, THD ≤ −40). Cut 96: clips from Q 64 near the cutoff (~500 Hz), whole passband from Q 96.
  Cut 128: clean to Q 80, cutoff region from Q 96, passband from Q 112. Cut 200 / 255: never clips (max −32.9 / −51).
- **sw11** (word 5 neutral, the original spec): screams at Q 0 at cut 96/128 (passband pinned at the ceiling), as
  predicted by the no-normalisation model; clean at 200/255. Rejected.
- **sw31** (sw15 + high frame 0x90): Q 0 clean; a narrow clipping spot at the cutoff from Q 16..32 at every cutoff
  (250 Hz / 500 Hz / 1 kHz / 2 kHz for 96 / 128 / 200 / 255); whole passband clips from Q 80 (cut 96/128), Q 127
  (cut 200), never at 255. Fuzz over the full cutoff range, but early "screaming" spot and a ~2 kHz top end.

## Release: "EOS 4.71-beta2" (2026-10-21, build/eos471_beta2.bin, sysex/EOS471-beta2.syx, checksum 088802e2)
`tools/build_lpfuzz.py build/eos471_beta.bin OUT --release`: the same lpfuzz.s assembled with RELEASE=1, so every
switch read is the constant 15 (interpolation on, moving zero, word 5 = word 4, word 8 pole, high-frame cap 0xDF);
parameter-195 handlers left out and descriptor 195 stock. LP+Fuzz last in the menu (index 21, type 0x03).
.ctor 988 / 1,112 bytes. Verification: tools/emu_lpfuzz_rel.py (release == test build "LPFuzz5 T" at switch 15 for
every OB-Xa LP/HP/BP/CBP and LP+Fuzz computeFrames/packQ, all Q, modes 0..3, with garbage in the switch RAM; registry,
display, descriptors, image diff) 17,291 / 0; freezing at 11 / 31 / 14 instead is caught (1,920 / 1,920 / 13,545).
LFO 51,395/0, Transwave 6,011/0, cords 13,004/0, RFX 12,300/0. emu_obxa (stock tables) now differs only at Q values
between table steps (Q mod 4 = 1..3), i.e. the always-on interpolation, which emu_lpfuzz checks against the model.
More features may follow before the beta2 release is published.

## Bug found on hardware (2026-10-21): filter types 5..20 stored wrongly in every LP+Fuzz build
The filter-type descriptors 0x5AC48 / 0x6B58E have a stored-range byte at +0x15 (20 in stock = max). The voice
parameter store 0x596B4 rescales the value from 0..max to 0..(+0x15) via 0x19DC5C when the two differ; the getter
0x59F88 and the voice engine read the byte raw. Raising only max to 21 made every stored type ID ×20/21: menu 5..20
stored 0x0F, BP2, BP4, 0x1E, 0x1F, SEQ1, 0x3D.. (readback 5->0, 6->5, 7->6, 10->8, others 0; matches the model
exactly). LP2..HP4 and LP+Fuzz (type 3) were unaffected, so the LP+Fuzz measurements stand; the "Swept EQ"
reference sweeps actually played the default (unfiltered) object. Presets whose filter type was edited and saved
on an LP+Fuzz test build or the first beta2 (088802e2) may carry a bad type byte and play unfiltered.
Fix: +0x15 = 21 as well (build_lpfuzz.py; both emulator suites now check it). Corrected beta2: checksum 088802e4.
Corrected beta2 on hardware (2026-10-21): all 22 filter menu entries read back (0..21; 22 clamps to 21); param 195
stock (-1). Sweep test (recordings/beta2_fr, 36 sweeps + Swept-EQ reference, now really type 8, flat within 2.1 dB
100 Hz–10 kHz): LP+Fuzz matches the LPFuzz5 T switch-15 recordings within 0.30 dB over 828 band levels.
