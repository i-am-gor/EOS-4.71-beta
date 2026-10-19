# EOS 4.70 voice filter coefficient format

Status: decoded from the EOS code paths. The field meanings are consistent across all 21 filters and
fit known formant data; absolute Hz scale is approximate (± ~¼ octave) and nothing is yet verified
on hardware. Model + plots: `tools/eos_filter.py`, `notes/filter_model.png`.

## Where it lives
- Registry `FilterRegistry_ctor` @ 0x67F98 builds the 21 filter objects (menu order) at mgr+0x200.
- Each class's `computeFrames` (vtable slot +0x14) writes a 10-word block **directly into sound-chip
  memory** in the CS 0x08000000 window (one 0x80-byte block per voice, 16 blocks per 0x800 page),
  then calls `FUN_0010d3b0` to set the block's mode byte.
- `packQ` (slot +0x18) rewrites only the resonance-dependent words when Q changes.
- Morph filters (Dual EQ, 2EQ+LP, 2EQ+Expr) share the frame builder at 0x6742C; Peak/Shelf uses its own (0x67C6C).

## Block layout (32-bit words)
| word | role |
|---|---|
| 0, 4, 8 | pole-pair stages (2-pole each; 6-pole max) |
| 1, 5 | zero-pair stages |
| 9 | zero-pair stage, or output gain (`DAT_10004d7c` ± compensation) when mode bit 6 set |
| 2, 3, 6, 7 | not written by filter classes (chip/voice state) |
| +0x7B (byte) | mode: `tab_0x10D4F4[n] | flags`. bit 6 = word 9 is gain; bit 7 (written to the *previous* 0x80 block) set by filters with active zeros |

Flags passed: lowpass 0x40, most others 0xC0, vocal filters 0x00.

## Stage word
```
 31      24 23      16 15       8 7        0
[  X_low  ][  F_low  ][  X_high ][  F_high ]
  low morph frame       high morph frame
```
The chip interpolates between the two frames using the voice's morph/frequency control.

- **F = log frequency, 32 steps per octave.** Calibrated from Dual EQ (`F = 7 + p·210/128` vs
  display `10000·(1006/1024)^(255−2p)` Hz): `f ≈ 9824 · 2^((F−215)/32)` Hz.
- **X = log bandwidth, 16 steps per octave of (1−r).** `r ≈ 1 − 2^((X−255)/16)`; X=0xFF puts the
  pole/zero at the origin (no effect). One Swept-EQ gain step (0.75 dB) moves pole and zero X apart by 2.
- Constant-Q designs use `X = F/2 + c` (Swept EQ, Dual EQ: `X = F/2 + 0x74 ± gain`).
- **`0xFFCF` half / `0xFFCFFFCF` word = neutral stage.**

## Per-filter recipes (decompiled)
| filter | poles | zeros | notes |
|---|---|---|---|
| 2/4/6-pole LP | 1/2/3 × `RES16[q>>3]` (table 0x6875C) | neutral | low frame X=0x84 F=0x08 → high X=0xFF F=0xCF; Q lowers X |
| 2nd/4th HP | `0x8004FFCF − (q>>2)·0x01000100` | `0x80048004` | zeros near DC; poles cancel them in low frame |
| 2nd/4th/Contrary BP | fixed `0xFF68FFCF` etc. + Q word | `0xFF04FF90` | |
| Swept EQ | `(0x77−i,0x07 | 0xDF−i,0xD7)` | same with +i | i = (gain−64)/2; constant-Q sweep F 7→215 |
| Phaser 1/2, Bat, Flanger | same F as zeros, X≈0xC0−q | X=0x30 (near unit circle), e.g. `0x309030D0` | sharp notches with resonance from the poles |
| Vocal Ah-Ay-Ee | `0x709570B1`, `0x706F709D`, `0x70547035` (+body>>2 to F) | `0xFFC0FFC0` | X=0x70 = constant formant bandwidth |
| Dual EQ / 2EQ morph | `X=F/2+0x74−g` | `X=F/2+0x74+g` | user Low/High freq per EQ → F bytes |
| Peak/Shelf | F±peak, X from shelf | | builder 0x67C6C |

## Open questions
- Absolute sample rate / F=255 mapping (F=255 ≈ 23.4 kHz with the Dual-EQ calibration).
- Exact morph law in the chip (modelled as linear in X and F).
- Meaning of words 2,3,6,7 and the `0x10D4F4` mode table entries (0x37, 0x01, 0x13, 0x25).
- Units of the gain word and of the `computeFrames` return value (gain compensation).

## Hardware calibration (2026-10-17, stock 4.70, tools/hw_freqresp.py, recordings/fr_stock)
Sine-sweep responses vs a flat Swept-EQ reference, Quantum 19/20 capture:
- F scale: **30.7 F steps per octave**; f(F=215) ≈ 10.4 kHz; F=255 ≈ 25.7 kHz (above Nyquist).
- Gain compensation (computeFrames/packQ return, gain word): ≈ 1 dB per unit
  (Q127 passband −11.5 / −23.5 / −36.5 dB for 2/4/6-pole vs Q0).
- Stock Q127 resonant peak above passband: ≈ +19 dB (2-pole), +36 dB (4-pole), +45 dB (6-pole),
  roughly constant across the range; peak frequency within ~8 % of the display mid-range,
  ~25 % high at the bottom.
- Q0: 12/24/36 dB/oct with a +2…+5 dB bump at the lowest cutoffs (4/6-pole strongest).
