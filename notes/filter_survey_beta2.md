# Filter survey: EOS 4.71-beta2 measured, stock EOS 4.70 simulated (2026-10-22)

## Data

**Hardware (beta2)**
- **Grid:** 9 filters × 16 cutoffs (0–240 step 16) × 16 Q (0–112 step 8, plus 127) = 2,304 settings.
- **Sweeps:** the 6 s sine sweep (key 81), plus 20 s retakes at cutoff ≤ 16 with Q ≥ 64 (144 settings). The A/B
  comparison of the two sweeps is in `recordings/ab_sweep.png`.
- **Files:** `recordings/fr_beta2_merged/`: `<type>_response.png`, `<type>_thd.png`, `bands.json`, `targeted.txt`.

**Stock**
- **Simulation:** `tools/sim_filters.py` runs the image's own filter code in the emulator and applies the chip's measured
  stage law.
  - Against the beta2 hardware the shapes agree to a median of 0.3 dB (90 % within 0.9–1.5 dB).
  - It is linear only, and absolute level versus Q is not modelled.
- **Hardware:** `recordings/fr_stock*` (2026-10-17, 20 s, cutoffs 48–255, Q 0 and 127). These takes are about 8.6 dB
  hotter than beta2's.
- **Comparison:** `recordings/stock_vs_beta2/`: `<type>_stock_vs_beta2.png`, `stock_vs_beta2.txt`, `peaks_fine.txt`.

**Limits**
- OB-Xa resonances at high Q are about 1 Hz wide at low cutoffs. Band levels and fast sweeps under-read them, so peak
  heights come from the fine-grid simulation.
- Real OB-Xa: no measured response has been published. The references are the CEM3320 datasheet (20–30 dB of
  resonance before oscillation) and the circuit (2-pole SVF, 4-pole cascade, no HP or BP modes).

## Findings

| # | Filter | Finding | Evidence | Verdict |
|---|---|---|---|---|
| 1 | HP2, HP4, Contrary BP | Headroom: outputs reach −12.7 to −13.9 dBFS from a −12 dBFS input, within 1.5–3 dB of the chip clip ceiling | Output peak re reference at Q 127: HP2 +18.5…19.6 dB (stock +7.5…13), HP4 up to +26.8 (stock +15.8…25.8); 16 HP4 and 48 Contrary BP settings above −15 dBFS | Real problem: a hot sample will clip |
| 2 | LP+Fuzz | 0.7–2 dB passband dip from Q 104 to Q 112 at cutoffs 176–240; smaller dips at Q 48 and 64 | Q-step table | Real problem: the level word steps in 16 Q steps while the resonance is interpolated |
| 3 | LP+Fuzz | Level rises 28–42 dB from Q 0 to full drive at cutoffs ≤ 160 | Level rise | Design; a very large jump for one knob |
| 4 | LP+Fuzz | Bass loss when driven: 50 Hz is 13 dB below 101 Hz at Q 127 (1.4–3.3 dB at Q 0) | Every cutoff ≤ 128 | Design; the drive stage's ~100 Hz corner |
| 5 | LP+Fuzz | No fuzz above cutoff ~160 | THD −70 dB, peak −19 to −32 dBFS at cutoff ≥ 192 | Design limit |
| 6 | BP4 | Resonance not constant across cutoff: +4.3 dB at 201 Hz rising to +19.3 dB at 14 kHz | Stock goes the other way, +18.3 → +9.0 | Real problem: uneven across the keyboard |
| 7 | BP2, BP4, Contrary BP | Centre sits below the displayed cutoff, by more at higher cutoffs: −0.55…−0.65 octave at 1.25 kHz, −1.1…−1.4 at 14 kHz | Fine-grid simulation, confirmed on hardware (806 Hz at a displayed 1,248 Hz) | Stock does the same (−1.4 octave at 14 kHz). The beta1 changelog's "centre follows the display" is wrong |
| 8 | 4 and 6-pole LP | Q 127 resonance 4–14 dB below stock at medium and high cutoffs (4-pole +30…35 against +35…38 dB; 6-pole +30…41 against +42…48); at Q 64 about half of stock | Fine-grid simulation | Character. The 4-pole is close to the CEM3320's 20–30 dB. The beta1 changelog claim "matched to the stock maxima" is wrong |
| 9 | All OB-Xa models | Clean (THD below −40 dB in the loud part of the response); Q steps 2–3× smoother than stock (largest step 0.6–2.6 dB against 2–5.5) | `targeted.txt`, `peaks_fine.txt` | Good |
| 10 | HP4 | +6 dB bump at Q 0 at the lowest cutoffs (stock +2) | Simulation, seen on hardware | Minor |

## Recommendations (ranked by benefit against risk)

1. **High-pass and Contrary BP headroom.**
   - **Change:** lower their level word with Q, about 6–10 dB at Q 127 for HP2/HP4 and about 3–6 dB for Contrary BP. As
     an alternative, cap the HP resonance near the stock envelope.
   - **Cost:** table values only (`tools/hpbp.py` tables), no code space.
   - **Risk:** beta2 high-pass presets get quieter at high Q.
   - **Test:** hardware grid with a 0 dBFS sweep, checking the clip peak.
2. **LP+Fuzz level word.**
   - **Change:** interpolate it like the resonance; this removes the Q 104→112 dip.
   - **Cost:** a few instructions in the LP+Fuzz packQ (216 bytes free in the filter area).
   - **Risk:** none, since this filter is new in beta2.
3. **LP+Fuzz loudness.**
   - **Change:** reduce output as drive rises, aiming for ≤ 10 dB between Q 0 and full fuzz.
   - **Caveat:** the attenuation must come after the clipping stage, otherwise it would also remove the fuzz. Needs a
     test build to confirm where the gain applies.
4. **LP+Fuzz bass.**
   - **Change:** lower the drive-stage corner from ~100 Hz to 30–40 Hz.
   - **Risk:** this changes the character; A/B it on hardware first.
5. **BP4 resonance across cutoff.**
   - **Change:** rebalance the low and high frame damping so resonance stays roughly constant (+12…15 dB at Q 127).
   - **Risk:** existing BP4 presets change at the extremes.
6. **Documentation (beta1/beta2 changelog and addendum).**
   - Correct the 4/6-pole "matched to stock maxima" claim and the band-pass "centre follows the display" claim.
7. **Optional.**
   - Band-pass centre calibration: remap the frame F values. It changes every band-pass preset relative to stock, and
     the chip's F law wraps above about 0xE0, so the top octave may not be reachable.
   - Cutoff-dependent drive, so LP+Fuzz also fuzzes at high cutoffs.
   - Faster 4/6-pole resonance build-up, if you want them closer to stock.

## Cross-check

Gemini (OpenRouter) and Groq agreed on 1, 2 and 6 as real problems.
- **Band-pass centre:** Gemini would keep it for stock compatibility; Groq would fix it. I've made it optional.
- **Groq's error:** it claimed the level-word fix would also restore the LP+Fuzz bass. That's wrong: the bass loss comes
  from the drive stage's corner (item 4).
- **Other models:** LM Studio's answer misread the columns, and AnythingLLM dropped the connection, so neither was used.

## Fixes 1 and 2: build 0886947c, re-measured 2026-10-22

Build: `patches/hpgain/hpgain.s` plus the LP+Fuzz note-on return. Emulator: `tools/emu_filterfix.py`, 2,560 checks, 0
failures; two planted bugs caught (84 and 56 failures). Same grid on the E4 (`recordings/fr_fix_merged`,
`compare.txt`). Levels are corrected for a 1.3 dB lower session reference.

**Word-9 scale (measured):** 31 units = 5.9 dB, so about 5.3 units per dB (I assumed 4).

| Filter | Level vs Q 0 at Q 127 | Output peak at Q 127 | Settings within 3 dB of the clip ceiling | Loud-band THD |
|---|---|---|---|---|
| HP2 | −5.9 dB (smooth from Q 0) | −4.9 dB | 0 → 0 | −50.8 dB |
| HP4 | −5.8 dB | −2.6 dB | 16 → 10 | −47.1 (was −37.5) |
| Contrary BP | −2.3 dB | −1.0 dB | 48 → 48 | — |
| LP+Fuzz | — | unchanged | — | unchanged |

**HP4:** partly fixed.

**Contrary BP:** not fixed.
- Its hot settings sit at high cutoffs and medium Q.
- At cutoff 224 it still clips: THD −18.7 dB at Q 127, −34 dB at Q 112 (was −26), output pinned at the ceiling.
- A Q-only cut can't reach it.

**LP+Fuzz:**
- The Q 104→112 dip is gone at cutoffs 176–240.
- Q 96–104 now sit 1–2 dB lower, on the continuous curve that packQ already used. Q 32 sits about 1.5 dB lower too, for
  the same reason.
- Fuzz, the clip ceiling and THD are unchanged.

**Follow-up options:**
- HP4: K 32 → 48 (about −8.6 dB at Q 127).
- Contrary BP: lower the high-frame half of word 9 (cutoff-dependent) by about 6 dB, keeping the Q term.

## HP4 with K 48 (build 0886948c, re-measured 2026-10-23)

**Level against Q, relative to K 0:**

| Q | K 32 | K 48 |
|---|---|---|
| 64 | −1.2 dB | −1.8 dB |
| 96 | −2.9 | −4.9 |
| 112 | −4.2 | −7.4 |
| 127 | −5.8 | −11.8 |

**Q 127 peaks at cutoffs 48 / 96 / 144** (re reference): +11.8 / +17.3 / +21.7 dB, against stock's +25.8 / +23.2 / +19.8.

**Settings within 3 dB of the clip limit:** 15 (K 0) → 9 (K 32) → 5 (K 48).

**Problem at cutoff 240, Q 127 only:**
- A spurious ~3.2 kHz component at +22.5 dB, with THD −4 dB. It reproduces on a re-take (`recordings/fr_fix2_check`).
- Clean with K 32 (−47 dB) and clean at Q 124, at cutoff 248, and at cutoffs 224 and 232.
- The word-9 byte there is 0xCF (off 47). Off 42 (byte 0xD4) is measured clean at cutoff 240, Q 120.

**Decision (2026-10-23):** keep K 48 as built, including the distortion at cutoff 240 / Q 127. The cap at 42
units and the revert to K 32 were both rejected. Build 0886948c (`sysex/EOS471-beta2-filterfix2.syx`) is the HP4
final.
