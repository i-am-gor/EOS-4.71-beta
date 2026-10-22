# Stock EOS 4.70 pan bug: every pan control reaches hard L/R at half range (2026-10-18)

## Symptom (measured on the E4, preset 000 voice 0 sine, Quantum 19/20 = L/R, recordings/pan_stock)
| control | hard left at | hard right at | dead range |
|---|---|---|---|
| voice Pan (SysEx id 40) | -32 | +32 | -33..-64, +33..+63 |
| Multimode/mixer channel Pan (id 249) | -32 | +32 | same |
| MIDI CC10 | 32 | 96 | 0..31, 97..127 |
L/R dB (voice Pan / id 249 / CC10 identical): -64/-32 -> L -25.6 R -98; -16 -> L -26.4 R -41.8; 0 -> L -29.6
R -29.4; +16 -> L -42.3 R -26.4; +32/+63 -> L -98 R -25.6. The AmpPan cord works the same way (full swing
at about half the amount). Centre is 0.24 dB right-heavy (see pan law below).

## Cause (FUN_0006092c note-on base, FUN_000609d8 note-on, FUN_00060B7C per tick)
- Amp struct at voice+0x94: +2 AmpPan cord sum, +6 pan base = (pan bytes of three levels) * 0x20,
  +0xA final pan. Multimode (mode byte 0x10004F04 == 2) adds the channel pan word (channel struct +0x62).
- final pan = (cord + base [+ channel]) >> 4  ->  2 units per pan step.
- Chip writer FUN_00060784 (and the RFX path FUN_00060674 stores the same value): index = pan + 64,
  clamped 0..127; left/right gains from the constant-power table 0x61590 (128 entries, sine law,
  -3 dB centre, ~0.153 dB units): table[i] and table[i ^ 0x7F].
- So a pan of +/-32 already gives index 0/128 -> clamped hard. The shift should be >> 5 (1 unit per step:
  +/-64 -> index 0..128 clamped 127; CC10 0..127 -> full sweep).
- Sites: `0x60A50 asr.l #4,d5` (E885, note-on) and `0x60BEA asr.l #4,d1` (E881, tick; the value is also
  the change-detection compare against +0xA, so both must change together). Fix: E885 -> EA85, E881 -> EA81.

## Smaller findings
- Centre imbalance: index 64 reads table[64] (-20) for one side and table[63] (-21) for the other:
  ~0.15 dB by the table, 0.24 dB measured (right louder). Cosmetic.
- Stereo samples: the right voice's pan argument is built with move.w into a register whose upper word
  holds an address (0x60CC8 `move.w $c(a4),d1 ; add.l d1,d5`), but both chip writers read only the low
  word, so it is harmless.
- Voice-level ids 24-26 (preset volume/pan/transpose, standard descriptors at +0x34/+0x35/+0x20) ignore
  remote SysEx sets; ids 39-41 are the voice Volume/Pan/Transpose with custom getter/setter.

## Fixed in Sync8 (verified on hardware 2026-10-18)
Voice Pan, Multimode Pan and CC10 sweep the full range (L-R +72 / +16 / -0.25 / -16 / -72 dB at
-64 / -32 / 0 / +32 / +63), identically on the main outputs and Sub 1-3. The 0.25 dB centre offset remains.

## Centre offset fixed in EOS 4.71-beta2 (2026-10-22, verified in the emulator and on hardware)
The chip writer 0x60784 gives one side table[i] >> 4 and the other table[i ^ 0x7F] >> 4, writing them to chan+113
and chan+115; the table at 0x61590 has no other reader. At centre (pan 0, index 64) that is table[64] = -311 → -20
and table[63] = -322 → -21, one step louder on one side; the user hears it on the right.

**Fix (build_beta2.py PAN_FIX):** entries 63 and 64 both = -316, giving -20/-20. Centre is exactly balanced and
pan -1 is centre too; every other pan is unchanged.

**Check:** `tools/emu_pan.py` runs the real 0x60784 in stock and beta2 for every pan and six levels (768 checks).
Result: centre goes from (108, 107) to (108, 108), and every other setting is identical.

**Hardware (build 0886a24c, preset 000 sine, `hw_pan_test.py`; results in `hw/pan_beta2/`, local):**
- Voice Pan: L − R is 0.00 dB at −1 and 0, +0.77 dB at −2 and −0.79 dB at +1; ±64/63 are hard (±60 dB).
- CC10: 0.00 dB at 63 and 64, −0.78 dB at 65.
