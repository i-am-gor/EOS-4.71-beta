# SLoop wavetable / transwave patch — design

Builds on Sync6 (OB-Xa v3d + LFO sync). Findings in notes/transwave.md.

## What you get
Two new cord destinations next to the stock ones, chosen in the Cords screen like any other:

| Destination | Code | Behaviour |
|---|---|---|
| **SLpWav** | 55 | Wavetable: the loop window steps in whole loop lengths. With a sample made of equal frames (single cycles) and the loop set on one frame, the cord selects frame *n*. Clean switches (each jump is a whole number of cycles). |
| **SLpScn** | 58 | Transwave scan: the loop window slides continuously; full scale sweeps the whole sample. Ensoniq-style, for pads and evolving loops. |
| SLoop | 53 | Unchanged stock behaviour (±100 samples per full cord), so existing presets (e.g. 005) sound the same. |

Range, for either new destination: a full-scale source at amount +100 reaches the end of the sample;
−100 reaches the start. Unipolar sources (Lfo+, Vel+, MidiA, envelopes) with the loop set on the first
frame give 0 → last frame. Updates every 10 ms control tick (as stock SLoop). Stereo samples move both
sides together. The loop is always clamped inside the sample (stock SLoop can run past the end).

## How the stock engine does it (what we hook)
- Note-on, FUN_0005FAE0: `shift = (acc >> 5) + base`; loop start (note +0x5A) and loop end (+0x5E)
  += shift; right channel +0x458/+0x45C; shift kept in pitch-struct word 0x16.
  `acc` = pitch-struct word 5 = voice +0x64 = SLoop accumulator; base = word 0xE (zone value).
- Every tick, FUN_0005FE4C: same expression; if it changed, both loop points move by the delta and
  FUN_00095DD0 rewrites the chip loop registers.
- Cord sum units: amount is stored << 5; `acc += src * amt >> 12`; full-scale source at 100 = 3200.

## Changes
1. **Destination table** (0x6344C, 8 bytes per code: name ptr, accumulator offset, flags):
   codes 55 and 58 are unused (offset 0x1E = dummy, empty name). Set offset 0x64 (the SLoop
   accumulator) and point the names at "SLpWav" / "SLpScn". The Cords UI (FUN_00062C44/62D00/62DC4)
   lists every code whose offset ≠ 0x1E, so they appear automatically; presets store codes, not list
   positions, so nothing else moves.
2. **Mode detection, no new RAM**: the cords of the voice are in the preset voice struct
   (`*(note + 0x5C) + 0xBC`, 24 × {src, dst, amt, -}). A cord with dst 55 or 58, src ≠ 0 and amt ≠ 0
   selects the mode (55 wins over 58; stock otherwise). All three destinations sum into the same
   accumulator, so stock SLoop cords on the same voice add to the new mode's input.
3. **shift(p, note)** replaces `(acc >> 5) + base` at both call sites (one jsr each):
   - S0, S1 = sample start/end in words, from the sample header `*(p + 0x30)` as FUN_00194600
     computes them: `(DAT_100071BC + hdr[0x3C + 4·side] + hdr[0x14 / 0x1C + 4·side]) >> 1`.
   - base loop: `ls0 = note[0x5A] − p[0x16]` (current shift removed), `le0 = note[0x5E] − p[0x16]`,
     `L = le0 − ls0 + 1` (constant).
   - Stock: `(acc >> 5) + base` (unchanged).
   - SLpWav: `j = round(acc · F / 3200)` with `F = (S1 − S0 + 1) / L`, clamped to
     `[−(ls0 − S0) / L, (S1 − le0) / L]`; `shift = j · L`.
   - SLpScn: `shift = acc · (S1 − S0 + 1 − L) / 3200`, clamped to `[S0 − ls0, S1 − le0]`.
   - 32-bit multiply then signed divide (divs.l by a register holding 3200); no overflow for
     |acc| ≤ 32767 and samples up to 2^16 frames·L.
4. **Code space**: image header padding 0x20080–0x201FF (384 bytes). It's zero in 4.70, nothing in the
   OS reads it, and the boot loader only uses header fields up to 0x20041 (magic, checksum, entry,
   length, name at 0x18–0x2F, loader fields 0x30–0x41). It's flashed with the image and covered by the
   checksum. Estimate: shift() ~130 bytes, cord scan ~30, strings 14, two 6-byte jsr hooks.

## Risks / to verify while implementing
- Exact hook bytes in FUN_0005FAE0 / FUN_0005FE4C (the `>> 5` + add sequence) and register liveness.
- Any code that special-cases destination codes numerically (search for compares with 53/55/58).
- Loop types: forward and alternating loops use +0x24/+0x2C; reverse types (header +0x3A >> 6 = 4–6)
  swap roles. First version: new modes act only on forward/alternating loops; others fall back to stock.
- Loop length 1 or no loop: no-op (the stock flag p+0x36 already disables loop moves for unlooped samples).
- Clicks in SLpScn are inherent (non-integer cycle jumps), as on Ensoniq transwaves; SLpWav is clean if
  frames are single cycles starting at zero crossings.

## Test plan
1. Emulator: run FUN_0005FAE0/FE4C paths with synthetic sample headers; check shift values, clamping,
   stock-mode bit-identity, stereo side.
2. Test sample: 32 frames × 256 samples, frame *j* = sine at harmonic *j+1*, loop on frame 0. Send it
   (MIDI Sample Dump or floppy-less transfer), cord MidiA → SLpWav +100; sweep MidiA over SysEx and check
   the pitch steps through harmonics 1…32. Then Lfo1+ → SLpScn for a continuous sweep, and preset 005
   to confirm stock SLoop is unchanged.

## As built (2026-10-18): `sysex/EOS470_Sync6_Wavetable.syx`, header "EOS 4.70 Sync6+Wavetable"
Differences from the design above, forced by what the engine allows:
- The Cords UI hides any destination whose accumulator offset is 0x1E, and there is only one other free
  word. So SLpWav and SLpScn share one accumulator, **voice+0x1C** (the "zero" source word: read only by
  unselectable source codes and by Off cords, which EOS skips; cleared at every note-on by FUN_000625CC).
- Mode lives in **voice+0x1E** (the destination sink, also cleared at note-on): the LFO1 init hook
  (lfo_init -> sl_mode) scans the preset voice's 24 cords (LFO1 params + 0x26 = voice params + 0xBC) and
  writes 1 if any enabled cord targets SLpScn (58). So on one voice, SLpScn wins over SLpWav; their cords sum.
- sl_shift = stock `(SLoop >> 5) + base`, plus, when the new sum is nonzero and the sample loop type is 1/2:
  frames `round(sum * floor(R / L) / 3200) * L` or scan `sum * R / 3200`, where R is the room to the sample
  end (sum > 0) or start (sum < 0); total clamped inside the sample and to +/-32767 samples (EOS keeps the
  shift in a 16-bit word: loop movement range ~0.74 s at 44.1 kHz).
- Code: image header pad 0x20080-0x201FF (342/384 bytes; also holds the moved LFO Rate formatter);
  hooks jsr sl_shift at 0x5FBA6 and 0x5FECA (16 bytes each); destination table entries 55/58.
- Emulator: tools/emu_sloop.py 6,012 checks / 0 failures (model vs code on random geometries, stock
  bit-identity, register preservation, sl_mode via the real LFO init, table entries); Sync6 regression
  tools/emu_lfosync.py 50,689 / 0. Destinations listed 69 -> 71.
- Test wavetable 32x256 (loop on frame 1): SLpWav sum 0/100/200/1600/3200 (+100 cord at 0/3/6/50/100%) ->
  frames 1/2/3/17/32; SLpScn full scale -> shift 7936 (last loop position).

## Hardware results (2026-10-18, test wavetable 32x256 in preset 002, Mod Wheel -> destination, +100)
- Wavetable (first build, full scale 3200): frames exact integer harmonics (peaks within 0.05%, 12 Hz wide),
  but stepping 1.28x fast: the panel's amount 100 is stored as 127 (<< 5 = 4064). Fixed in Wavetable2.
- Wavetable2: 14/17 mod-wheel steps on the expected frame; the misses were one frame low and frame 32
  was never reached. Cause: EOS stores the sample end as the last sample (inclusive) while the loop end is
  one past the loop, so the upper bound was 1 sample short (30 frames above frame 1 instead of 31).
  Fixed in Wavetable3 (`sysex/EOS470_Sync6_Wavetable3.syx`, "EOS 4.70 Sync6+WaveTbl3"): +1 on the upper bound.
- SLpScn on Wavetable2: smooth, monotonic scan blending neighbouring frames, within ~0.5 frame of the
  expected position, ending between frames 31 and 32 (same 1-sample bound).
- Build-script guard added: header name must fit 24 bytes and the image size must not change (a 25-byte
  name had shifted a test build by one byte; caught by the emulator before any flash).

## Loop page check (2026-10-18)
The E4 shows the imported wavetable's loop as Start 2, End 258, Size 256: the loop sits 2 samples after the
frame grid. Each frame window then includes 2 samples of the next frame, and frame 32's window (7938..8193)
overruns the 8192-sample sample, so the clamp (correctly) stops one frame short. Earlier "252-sample stride"
and "top bound 7863" readings were spectral-fit artefacts; the purity loss at high frames is the E4's
interpolation (44.1 kHz sample on the 48 kHz clock, plus tuning), largest for frame 32 (8 samples/cycle).
Fix on the sample side: loop start 0 / end 256, or use testsignals/wavetable/wt32x256_harmonics_pad2.wav
(2 leading zero samples, frames at 2 + 256n, loop 2..257 in its smpl chunk, 8194 samples).

## Wavetable3 + padded table (2026-10-18): working
wt32x256_harmonics_pad2.wav (frames at 2 + 256n, loop Start 2 / End 258 / Size 256; the E4 will not start a
loop before sample 2) in preset 002, Mod Wheel -> SLpWav +100: frame 1 at CC 0 ... frame 32 at CC 127, each
step 20-66 dB above the other harmonics. 15/17 steps match round(CC/127*31)+1; the two others are
rounding: the Mod Wheel source is CC*32 (4064 at CC 127), so the cord sum is 31.75 per CC step.
Rule for user wavetables: 2 lead-in samples, equal frames of exactly the loop length, loop on frame 1.

## Wavetable4: full scale 4032
Full scale changed from 4064 to 4032 (= CC 127 x 32 through a +100 cord, (127<<5)(127<<5)>>12), rounding 2016.
MIDI controllers now divide frames exactly: emulator checks all 128 Mod Wheel values on the padded table ->
128/128 on round(CC/127*31)+1. Continuous sources at full 0x1000 (LFO, envelopes) reach the last frame ~1%
before their peak. Emulator 6,140 / 0 (SLoop), 50,689 / 0 (LFO regression). `sysex/EOS470_Sync6_Wavetable4.syx`.

## Transwave-only build (2026-10-18): `sysex/EOS470_Sync6_Transwave.syx`, "EOS 4.70 Sync6+Transwave"
SLpWav removed at the user's request: destination 55 back to stock (unused), no mode flag (voice+0x1E is the
plain sink again; LFO init identical to Sync6), frame-stepping code removed. SLpScn (58) always scans:
shift = stock + sum * R / 4032 (R = room to the sample end/start), clamped inside the sample and to +/-32767.
Mod Wheel 0..127 through +100 sweeps the loop start 0..7936 on the padded 32x256 table (steps 61-63 samples).
Header code 225/384 bytes. Emulator 6,011 / 0 (SLoop), 50,689 / 0 (LFO regression).

## Transwave build on the E4 (2026-10-18)
Preset 002 (padded 32x256 table, loop 2..258), Mod Wheel -> SLpScn +100, CC 0..127 in steps of 8: the loop
window moves monotonically from frame 1.00 to 31.98 (frame 32 at CC 127), tracking CC/127*31+1 within 0.47
frames (energy-weighted estimate of a blended window). Firmware "EOS 4.70 Sync6+Transwave" is the current build.

## User guidelines
Sample-building rules and the frame-size / max-frames table are in `sysex/README.md`
("Transwave samples (SLpScn): size guidelines"): 2 lead-in samples, equal frames = loop length, loop on
frame 1, frames x frame size <= 32,768 (travel limit 32,767 samples from the 16-bit shift word).

## SLpScn whole-frame stepping (2026-10-21, EOS 4.71-beta2 checksum 08882940)
A/B on P001 (recordings/slpscn_ab2, tools/hw_slpscn_ab.py; same preset, only loop cords changed): the user's
smooth reference (AEnv+ -> Gain4X +100 -> SLoop +100 x4) holds clean frames and moves in whole-frame jumps
(clipped envelope); SLpScn (Gain4X -> SLpScn +6, AEnv+ -> SLpScn +100) drifts continuously, each 10 ms tick landing
mid-cycle -> smeared, inharmonic spectra ("noise"). Also AEnv+ is 0 at note-on, so an envelope at 100 with 0 attack
makes the first tick jump the whole range.
Fix: sl_shift's 22-byte scan block 0x200EC (shift = sum * R / 4032) replaced in place by whole-frame stepping
(patches/slpscn/snap.s): shift = round(sum * floor(R / L) / 4032) * L (exact rounding for sum >= 0; negative sums
round half a frame toward zero; sum * F can overflow only with > 65k frames). Use envelope -> SLpScn directly
(no Gain4X: it multiplies the range by 4). Cord amount sets the range (+100 = whole table).
emu_sloop 6,012 / 0 (model snaps; Mod Wheel sweep 0..7936 in 256-sample steps); mutations rounding 209,
multiply 866 caught. emu_silence 217 / 0 (allow-list + 0x200EC), emu_slice 3,806 / 0, LFO 51,395 / 0, RFX 12,300 / 0.

## Loop-shift glide instead of frame stepping (2026-10-21, beta2 checksum 08882a2b)
The user wants continuous (interpolating) movement, only without the noise burst on fast moves. Frame stepping
(snap.s) is NOT applied. Instead the 10 ms tick applies at most LIM = 64 samples of loop movement per tick
(patches/slpscn/slew.s in place at 0x5FED0..0x5FEED + shift_t in slice.s; tick call 0x5FECA -> shift_t):
slow moves unchanged, fast wheel / envelope moves and the note-on jump glide (32 frames x 256 at 64/tick ≈ 1.3 s).
Applies to SLoop and SLpScn. Emulator: tools/emu_slew.py 4,000 / 0 (real tick 0x5FE4C vs a no-glide build;
2,344 clamped, 1,621 within the limit; mutations LIM 48 → 2,754, wrong negation → 2,532); emu_sloop 6,012 / 0,
emu_silence 217 / 0, emu_slice 3,806 / 0, LFO 51,395 / 0, RFX 12,300 / 0.
Before take on 08882a77 (no glide): recordings/fastmove/before_08882a77.wav (P000, key 89, wheel slammed 0/127).

## The note-start burst: playback ran through the table before reaching the loop (2026-10-22)
Hardware on beta2 08882a2b, P002 (test table, AEnv+ -> SLpScn +100, key 89): the loop sits at frames ~29-30 from the
first 100 ms (the amp envelope is already at full at note-on; earlier statement "AEnv+ is 0 at note-on" was wrong),
but the dominant frame in the first 40 ms runs 6, 8, 12, 15, 19, 22, 25, 30, 32: playback starts at the sample start
and runs through the frames until it reaches the shifted loop = the noise burst (recordings/glide_p002).
Fix (beta2 checksum 08882e66): scan_start (slice.s, section .slS) — non-Slice voices leave the note-on exit through it;
with a non-zero SLpScn sum, each forward looped channel starts at its (shifted) loop start (+0x0C = +0x10); one-shot,
reverse and plain SLoop voices unchanged. Space: LP+Fuzz release streamlined (RELEASE-only paths without the test
switch and the never-active low-frame cap): .ctor 988 -> 896 bytes, equal to the tested build (emu_lpfuzz_rel
17,291 / 0; test build byte-identical). Glide (64 samples / tick) kept.
Emulator: emu_slice 3,806 / 0 (start-at-loop mutations 160 / 69), emu_slew 4,000 / 0, emu_silence 217 / 0,
emu_sloop 6,012 / 0, LFO 51,395 / 0, cords 13,004 / 0 (dest 55 reset), RFX 12,300 / 0.
- Hardware (2026-10-22, beta2 08882e66, P002): notes start on frames 31-32 (was a 6 -> 32 run-through in the first
  40 ms); user confirms it sounds clean with a fast envelope and fast Mod Wheel moves.
