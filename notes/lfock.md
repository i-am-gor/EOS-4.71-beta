# LFO clock from a cord (Lfo1Ck / Lfo2Ck)

Build: `tools/build_beta2.py BASE.bin OUT.bin` (header "EOS 4.71-beta2 +LfoCk").
`tools/build_beta2.py --nocord` is EOS 4.71-beta2 build 2 without this patch.
Test: `tools/emu_lfock.py BASE.bin`.

## What it does

**Lfo1Ck** and **Lfo2Ck** are cord destinations. A negative cord sum selects one of the 16 tempo
divisions (the same lengths as Rate 128–143) and overrides Rate. Zero or a positive sum leaves Rate
alone, including a synced Rate.

Full scale is magnitude 4032, which is a controller at CC 127 through panel amount −100
(`(127<<5)*(127<<5)>>12`). That is 1/32. Smaller depths are slower, in 16 even steps. At amount −100
the controller steps are CC 0 idle, then 4 bars through 1/32 across CC 1–127, eight CC values each.

While the sum is negative the LFO restarts on each note (the Sync switch is not consulted). Shape and
Delay still work. The Rate cord, Variation and the LFO trigger are ignored, as they are for a synced
Rate. LFO 1 and LFO 2 are independent. Two cords into the same destination add.

Lfo1Ck is destination 98, listed after Lfo1Trg. Lfo2Ck is destination 107, listed after Lag0in.
Lag0in stays destination 106.

## How

- The cord summer already writes a continuous running sum (flags `0x200`) into the destination word.
  The four bytes between the two LFO blocks, voice+0x1A4, are unused by the LFO tick. Voice init
  stores the long `1` there, so the LFO 2 half (voice+0x1A6) starts at 1 and the running sum keeps
  that +1. The prologue subtracts it before measuring the magnitude.
- Tick hook `0x61BF4` (`jmp lfo_tick`) jumps to `cord_tick` in the port-map hole, after the high-pass
  headroom code. Return address `0x61D70` means this call is LFO 2 (`move.w -2(a5)`); otherwise it is
  LFO 1 (`move.w 0x1C(a5)`, because a5 is the LFO block at voice+0x188).
- A negative sum becomes `d0 = 0xA000|div` (bit 15 sync, bit 13 key sync), plus bit 14 for LFO 2, and
  jumps to the sync body at `0x2040E`. Otherwise it jumps to `lfo_tick` at `0x20400`.
- `FUN_00061BC0` saves only d5–d7/a5. The divide uses d2 and d3, and the sync body saves d2–d4 only
  after its own entry, so the prologue saves d2–d3 itself (`lea -8(sp)` / `movem`; 5206e `movem` has
  no predecrement) and restores them before the jump. `divu.l` into d0 encodes a remainder divide on
  the 5206e; the quotient is taken in d3. `move.w` into a data register does not sign-extend.
