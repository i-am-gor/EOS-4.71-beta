# Transwave / wavetable capability of the EOS 4.70 sample engine

## Realtime loop-window modulation exists: cord destination SLoop (code 53)
- Note-on, FUN_0005FAE0: start offset = (SStart mod + zone start) scaled by the sample length
  (FUN_0013D5E0) -> SStart covers the whole sample, but only at note-on.
  Loop shift = (SLoop mod >> 5) + base (zone/sample param, pitch struct word 0xE), added in **samples**
  to loop start (voice +0x5A) and loop end (+0x5E); stereo right side +0x458/+0x45C.
- Every 10 ms control tick, FUN_0005FE4C: if the shift changed, both loop points move by the delta and
  FUN_00095DD0 -> FUN_00095CA8 rewrites the chip's loop registers (+0x14 start, +0x08 ~end) while the
  voice plays. Loop length stays constant: the window slides through the sample = transwave.
  Active only for looped samples (sample header +0x3A bits 6-7 = loop type; else the voice flag
  +0x36 disables it) and when voice byte +100 is 0.
- Range: cord amount is stored as amount << 5; dest += src * amt >> 12; src full scale 0x1000.
  So a full-scale source at amount 100 moves the loop by 100 samples. The destination sum is a
  16-bit short -> at most about +/-1023 samples (stacking cords; overflow wraps).
- No bounds check: FUN_00095CA8 writes the addresses as given; pushing the loop past the sample end
  plays whatever memory follows.
- No crossfade: the new loop takes effect when the play pointer next wraps; jumps are clean only if
  the loop length is a whole number of cycles and the material is phase-aligned.

## Preset 005
Uses 4 cords source 167 -> SLoop (amount 100, 100, 100, 50) plus others: stacking cords to get
~350-450 samples of loop offset, i.e. working around the +/-100 samples-per-cord range.

## What a patch could add
- Wavetable mode: quantise the SLoop shift to whole loop lengths (shift = round(m * N) * loop_len),
  so SLoop selects frame N of a sample made of equal single-cycle frames.
- Transwave mode: scale SLoop by the sample length (like SStart) so one cord sweeps the whole sample.
- Clamp the moved loop to [sample start, sample end].
Hooks: FUN_0005FAE0 (note-on shift) and FUN_0005FE4C (realtime). Needs ~100 bytes; the vector cave
and EXT are full after Sync6, so space has to be found first.
