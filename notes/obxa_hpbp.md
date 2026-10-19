# OB-Xa high-pass / band-pass (replacing 2nd/4th Order High-pass and Band-pass)

Build: `tools/build_hpbp.py build/eos470_sync6_transwave.bin build/eos470_sync6_tw_hpbp.bin`
-> `sysex/EOS470_Sync6_TW_HPBP.syx` ("EOS 4.70 Sync6+TW+HPBP"). Tables: `tools/hpbp.py`. Test: `tools/emu_hpbp.py`.

## Stock behaviour (decompiled + measured 2026-10-18, recordings/fr_stock_hpbp)
- Menu 3 2nd HP, 4 4th HP, 5 2nd BP, 6 4th BP, 7 Contrary BP (registry 0x67F98 order).
- HP: zero pair(s) 0x80048004 near DC (word 1, +word 5 for 4th), poles (q>>2 lowers X) word 4 (+8),
  moving from on the zeros (flat) to the origin at the top. 12 dB/oct; corner 25-60 % below the display;
  resonance +13 dB low, +1 dB at the top. Returns 0 (cf) / 1 (pq).
- BP: no effective zeros (all X = 0xFF); one pole pair (word 8) or two identical pairs (words 0, 8) that the
  chip runs as band-pass sections in this filter mode (6 / 12 dB/oct skirts measured). Returns -(q>>3) / -(q>>2).
- Displays: HP 18000*(1003/1024)^(255-v) (69 Hz-18 kHz), BP 10000*(1005/1024)^(255-v) (57 Hz-10 kHz).

## OB-Xa versions
Same pole pairs as the OB-Xa lowpasses, generated for each display (v3c generator, X + 1.5F <= 568,
low-resonance ladder rows blended toward stock RES16 re-aimed at the display):
- 2nd HP: SVF pair (32 steps) in word 4; 4th HP: ladder A (32) word 4 + ladder B (8 steps) word 8.
- 2nd BP: SVF pair in word 8 (CEM3320 SVF band-pass output); 4th BP: ladder A word 0 + ladder B word 8.
- Everything else stock: zero words, chip mode (flags 0xC0), gain word, return values, names, types.

## Code placement
| section | where | bytes |
|---|---|---|
| .hp2 | stock HP2 cf+pq 0x660CC-0x66177 | 172/172 (HP SVF table, entries, descriptor) |
| .hp4 | stock HP4 cf+pq 0x66278-0x6632B | 160/180 (HP ladder A/B tables) |
| .bp2 | stock BP2 cf+pq 0x668A8-0x6697F | 188/216 |
| .bp4 | stock BP4 cf+pq 0x6698C-0x66A6B | 212/224 |
| .fmt | stock HP formatter 0x66178 | 230/244: one Frequency/Q display routine for HP (entry stays 0x66178) and BP |
| .fmt2 | stock BP/Contrary BP formatter 0x667A8 | 224/244: shared computeFrames/packQ |
| .cave2 | vector cave 0x205C4 | 24 (HP4 entries) |
| .hdr2 | header pad 0x20170 | 32 (HP4 descriptor) |
BP2/BP4/Contrary BP display slots repointed to the new BP entry; display text verified identical to stock for
all 768 settings of each filter.

## Verification
Emulator: 5,377 checks / 0 failures (stock vs patched through the vtables: returns, SETMODE, gain and zero
words, pole words = tables, display text, vtable diff); LFO 50,689 / 0; Transwave 6,011 / 0; OB-Xa LP 1,158 / 0.
Hardware: see below.

## Hardware results (2026-10-18, recordings/fr_hpbp vs fr_stock_hpbp, recordings/rescan_hpbp)
| Q 127 | stock | OB-Xa (HPBP) |
|---|---|---|
| 2nd HP peak | 226 -> 7,671 Hz for display 223 -> 13,186; +13 dB fading to +1 dB | 233 -> 13,280 Hz (on the display); +16..+22 dB everywhere |
| 4th HP peak | +25 dB low, +2 dB at the top | +24..+29 dB everywhere, peaks on the display |
| 2nd BP | centre 226 -> 5,424 Hz, +10..+12 dB | 214 -> 7,241 Hz (tracks), +16..+19 dB, 0.17-0.21 oct |
| 4th BP | +13..+21 dB | tracks, +22..+29 dB, 0.08-0.13 oct |
Q 0: HP/2nd BP like stock (12 / 6 dB-oct slopes). 4th BP Q0 was -8..-24 dB and centred low (damped ladder poles
blended toward re-aimed lowpass sections) -> HPBP2 blends the BP ladder rows toward E-mu's own band-pass sections.
Clipping scan (preset 001, key 62 vel 127, Q 96/127, env 0/26, cutoff 48..255): 0 / 160 clips, loudest -9.3 dBFS;
no level trim needed. (The HF-click detector is not meaningful for HP/BP: their passband is high frequencies.)

HPBP2: `sysex/EOS470_Sync6_TW_HPBP2.syx` ("EOS 4.70 Sync6+TW+HPBP2"), differs from HPBP only in the 4th BP ladder
tables; emulator 5,377 / 0, LFO 50,689 / 0, Transwave 6,011 / 0, OB-Xa LP 1,158 / 0.

## HPBP2 measured (recordings/fr_hpbp2) and HPBP3
- 4th BP Q0 improved to -7..-13 dB (was -8..-24) but still ~12 dB under stock with the same shape. Emulator: the only
  difference from stock at Q0 was section B's X (0x83 vs 0x88) because the 8-step LADB row 0 was sampled at q=10:
  in the chip's band-pass mode, level is very sensitive to X (5 steps ~ 12 dB).
- HPBP3: BP ladder B is 16 steps (q>>3) sampled at the low end of each step (header pad), per-descriptor step mask;
  Q0 sections now 0x8708F7C8 / 0x8708F7C8 vs stock 0x8808F8C8. HP tables unchanged. Q64: ~0 dB, Q127 +22..+29 dB
  (centres on the display). `sysex/EOS470_Sync6_TW_HPBP3.syx`; emulator suites all 0 failures.

## Stock Contrary BP (measured on HPBP2, menu 7, unchanged stock)
cf: word 0 = (0x88-q, 0x08 | 0xD0-q, 0xC8) (full q, not halved), word 5 = 0xFFD0FF20 (zero F moves *against* the
cutoff: 0xD0 at the bottom, 0x20 at the top), return 0 / pq 1.
| Q | f48 | f96 | f144 | f192 | f240 |
|---|---|---|---|---|---|
| 0 level | -5.3 (lowpass-like) | -13.3 | -6.9 | +1.9 | +10.4 |
| 64 level | +17.6 | +9.9 | +16.2 | +24.4 | +30.9 |
| 127 level | +34.1 | +24.3 | +25.4 | +30.3 | +32.8 |
Low cutoffs: nearly flat below the centre (1-3 dB/oct), 9-14 dB/oct above; high cutoffs: symmetric 8 dB/oct.
Centre 196..5747 Hz for display 182..7545 (low at the top). Q127 bandwidth 0.08 oct. The X=0xFF zero word is
therefore NOT inert in this mode.

## HPBP4: OB-Xa Contrary Band-pass
Contrary BP cf/pq body 0x66A78-0x66B37 -> .cbp (44 bytes): descriptor = BP SVF table (shared with 2nd BP) in word 0,
stock contrary zero 0xFFD0FF20 in word 5, other words neutral, returns 0 / 1 as stock; display already on bp_fmt.
Emulator: HP/BP/CBP 5,761 / 0, LFO 50,689 / 0, Transwave 6,011 / 0, OB-Xa LP 1,158 / 0.
`sysex/EOS470_Sync6_TW_HPBP4.syx` ("EOS 4.70 Sync6+TW+HPBP4").

## HPBP4 measured (recordings/fr_hpbp4, 2026-10-18)
4th BP level dB (stock / HPBP2 / HPBP4), cutoff 48..240:
- Q0: stock +3.8 +1.1 -1.2 -2.8 +2.7 | HPBP2 -6.8 -8.8 -11.2 -13.3 -8.8 | HPBP4 -8.7 -10.5 -13.0 -14.6 -9.4
- Q127: stock +21.2 +18.3 +16.6 +14.7 +12.8 | HPBP4 +22.5 +22.8 +23.2 +22.0 +29.0 (centres on the display)
The HPBP3 change (Q0 sections within one X step of stock) did NOT restore the level: the X hypothesis was wrong.
Same shape as stock, uniform ~12 dB lower; HP passbands match stock exactly through the same shared code, so the
cause is specific to the band-pass words/mode and still unexplained. All OB-Xa BP filters show a steeper level-vs-Q
than stock (quieter at Q0, louder at Q127): 2nd BP -5 / +6 dB, 4th BP -12 / +7..+16 dB.
Contrary BP (OB-Xa): centre tracks the display (214..7241 Hz vs stock 226..5270), lowpass-like at low cutoffs kept,
Q127 bandwidth 0.17-0.21 oct (stock 0.08), levels well below stock (Q127 +2.7..+21.7 vs +24..+34; Q0 -0..-19 vs -13..+10).
Next: diagnostic build with byte-exact stock BP words through the new code path, to separate words from code path.

## Root cause of the band-pass level error (diagnostic build, 2026-10-18)
Diagnostic "EOS 4.70 HPBP diag BP4": 4th BP with byte-exact stock words through the new code was still ~13 dB
quiet (bp4 q0 f48 peak -44 dBFS vs stock -30) -> not the pole words. Bug: common_cf read the descriptor (a1) and
q (d1) after calling SETMODE, which is C code (d0/d1/a0/a1 scratch), so the band-pass computeFrames returned a
garbage gain-compensation value on hardware. HP and Contrary BP return a constant 0 and were unaffected (HP
passbands matched stock). The emulator missed it because SETMODE was stubbed as a bare rts.
Fixes: emu_obxa's SETMODE hook now trashes d0/d1/a0/a1 (HPBP4 crashes under it); HPBP5 keeps q in d3 and the
descriptor in a4 across the call. `sysex/EOS470_Sync6_TW_HPBP5.syx` ("EOS 4.70 Sync6+TW+HPBP5"): all suites 0 failures.

## HPBP5 measured (recordings/fr_hpbp5, 2026-10-18) - gain bug confirmed fixed
Level dB vs stock, cutoff 48 / 96 / 144 / 192 / 240 (centres track the display: 202..8366 Hz):
- 2nd BP Q0: +3.8 +3.4 +2.9 +2.7 +5.3 (stock +3.0 +1.9 +1.5 +1.3 +4.6) -> +0.7..+1.5
- 2nd BP Q64: +1.6 +0.4 -0.2 -0.4 +0.3 (stock not measured at Q64)
- 2nd BP Q127: +10.5 +9.0 +8.7 +7.4 +7.1 (stock +11.9 +10.7 +10.5 +10.2 +9.8) -> -1.4..-2.8
- 4th BP Q0: +4.4 +2.0 -0.4 -2.2 +3.0 (stock +3.8 +1.1 -1.2 -2.8 +2.7) -> +0.3..+0.9 (HPBP4 was -12)
- 4th BP Q64: +1.2 +0.1 -1.6 -3.0 -2.0 (stock +3.2 +1.7 0.0 -1.1 +0.4) -> -1.6..-2.4
- 4th BP Q127: +6.0 +6.0 +6.4 +5.0 +12.2 (stock +21.2 +18.3 +16.6 +14.7 +12.8) -> flat ~+6 dB, 10-15 dB less
  resonant boost than stock at low/mid cutoffs (HPBP4's +22..+29 was the bug); bandwidth 0.08 oct as stock.
- Contrary BP: identical to HPBP4 within 0.5 dB (its return value is a constant 0, so the bug never touched it):
  Q0 -7.5 -18.5 -16.3 -9.5 -0.1, Q64 -2.7 -13.2 -8.8 -2.0 +7.0, Q127 +12.9 +2.7 +7.6 +13.7 +21.7; still 10-25 dB
  below stock (stock's +24..+34 dB at Q127 comes from its full-q pole X sweep, 0x88-q).

## HPBP6: band-pass levels toward stock (2026-10-18)
- Gain path: caller FUN_0006013c sets voice+0x66 = ((r>>1) + 2r + 0xF8) << 8 | 0x7F from the computeFrames return r
  (~1 dB per unit). r > +3 overflows the byte, so Contrary BP (stock r = 0) cannot be raised by its return value.
- 4th BP: return = -(q>>2) + (q*q*11 >> 14) (descriptor byte 15 = boost 11; bp_boost in the header pad .hdr2):
  0 / -14 / -21 at Q0 / Q64 / Q127 (stock 0 / -16 / -31). Expected Q127 level ~+16 dB (stock +13..+21).
- Contrary BP: cbp_tab = OB-Xa SVF F bytes (centres on the BP display) with the stock contrary X law
  (0x88-q low frame, 0xD0-q high frame), 32 steps q>>2 (j = 31 uses q 127): 0x8800D0C6 .. 0x090051D5.
- Emulator (base = Sync6+Transwave): HP/BP/CBP 5,761 / 0, LFO 50,689 / 0, Transwave 6,011 / 0, OB-Xa LP 1,158 / 0.
`sysex/EOS470_Sync6_TW_HPBP6.syx` ("EOS 4.70 Sync6+TW+HPBP6", checksum 0887c126).

## HPBP6 measured (recordings/fr_hpbp6, 2026-10-18)
Level dB, cutoff 48 / 96 / 144 / 192 / 240 (HPBP6 vs stock):
- 4th BP Q0: +4.2 +2.0 -0.5 -2.3 +3.0 (stock +3.8 +1.1 -1.2 -2.8 +2.7) -> +0.3..+0.9, unchanged from HPBP5
- 4th BP Q64: +3.5 +2.1 +0.4 -1.0 0.0 (HPBP5 +1.2 +0.1 -1.6 -3.0 -2.0) -> now on stock's Q64 level
- 4th BP Q127: +14.9 +15.0 +15.3 +14.0 +21.2 (stock +21.2 +18.3 +16.6 +14.7 +12.8; HPBP5 ~+6): flat ~+15,
  -6 at the bottom, +8 at the top (stock falls with cutoff; ours does not). Bandwidth 0.08 oct as stock.
- Contrary BP Q0: -6.6 -15.1 -9.3 +0.2 +9.3 (stock -5.3 -13.3 -6.9 +1.9 +10.4) -> -1..-2.4
- Contrary BP Q64: +16.5 +9.3 +15.9 +24.8 +32.8 (stock +17.6 +9.9 +16.2 +24.4 +30.9) -> -1.1..+1.9
- Contrary BP Q127: +33.1 +23.9 +25.2 +30.9 +35.1 (stock +34.1 +24.3 +25.4 +30.3 +32.8) -> -1.0..+2.3
  Centres follow the display (214..7035 Hz at Q127 vs stock 226..5270); bandwidth 0.08 oct as stock.
Loudest take -2.4 dBFS (Contrary BP Q127 f192/f240; stock -3.2 there); no clipping.
