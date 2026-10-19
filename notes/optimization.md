# EOS 4.70 optimization survey (2026-10-18)

Goal: find code that can be made cheaper without changing the sound. Method: map the real-time paths,
decompile them (notes/voice_tick2-4.c, notes/clock3.c), and count executed instructions in Unicorn
(`tools/emu_cost.py`, synthetic inputs). Sample playback, filtering and mixing run in the sound chip;
the CPU (ColdFire 5206e) only does control, so "optimization" here means CPU time and flash space.

## Where the CPU time goes
- Vector 27 (autovector 3) timer interrupt at **2 kHz** (0x20A50): every 2nd interrupt advances the ms
  counter 0x10000450 and runs the master clock FUN_0002172C; **every** interrupt then runs the scheduler
  FUN_00020ED8 with interrupts re-enabled (skipped while it is still running: flag 0x1030960C).
- Scheduler: buckets (linked from 0x1030961E: +0 next, +4 head, +8 budget), each a circular list of
  timer items (+0 next, +8 task, +0xC arg, +0x1C -> deadline, +0x20 -> time source NOWMS/TICK/TICK2,
  +0x24 pre-callback). Every call walks all items; a due item runs its task, the head rotates past it,
  and the scan restarts from the first bucket. A bucket runs at most 5 due items per call (budget 5).
- Every sounding voice is a timer item: its 10 ms control tick FUN_00060E80 (via 0x614B8) runs in this
  interrupt context: cords FUN_0005F89C, Ck sources FUN_000625F8 (if used), 3 envelopes FUN_00062208,
  pitch FUN_0005FD38, LFOs FUN_00061BC0/61D5C, aux FUN_00062544, key/vel window FUN_00062798, filter
  FUN_0005FFD8, amp FUN_00060B7C, pitch/loop chip update FUN_0005FE4C.
- Already efficient: chip writes for pitch (FUN_00096028), filter, Q, volume/pan and loop points are all
  change-detected; the whole voice-tick tree contains a single divide (Ck sources, only with a Ck cord).

## Measured costs (instructions executed, stock 4.70)
| path | cost | rate at full polyphony (128 voices) |
|---|---|---|
| scheduler, nothing due | 41 + ~8.3 per timer item (1,068 with 128 voices) | x 2,000/s = ~2.1 M instr/s |
| scheduler, items due | +32 per due item; linear (head rotation), not quadratic | |
| cord processor per voice tick | 152 with no cords active + 16 per active cord (248 with 6) | x 12,800/s = ~3.2 M instr/s |
At roughly 1-3 cycles per instruction these are single-digit-percent shares of the CPU each (the E4's
CPU clock is not confirmed here; 54 MHz is the 5206e's maximum).

## Candidates, ranked (none changes sound)
1. **Cord processor: walk only active cords.** FUN_0005F89C tests all 24 slots every tick (~6.3 instr per
   empty slot). Building a per-voice list (or a last-active index) at note-on cuts a 6-cord voice from 248
   to ~120 instructions: ~1.6 M instr/s saved at 128 voices (~40% of the cord cost). Risk: low-medium;
   live cord edits on sounding voices must refresh the list (find where the enable bytes +0xC are set).
2. **Scheduler: skip calls that cannot find anything new.** Deadlines are ms (NOWMS) or clock ticks that only
   advance with the ms counter or an F8, so every second call (no ms step) can only find newly queued items.
   Skipping it unless the ms counter moved, an item was queued (FUN_00020F94) or an F8 arrived saves ~50% of
   the scan (~1 M instr/s at 128 voices). Timing change: at most 0.5 ms for items queued between ms steps.
   Risk: medium (core scheduler; must keep the re-entrancy flag semantics).
3. **Scheduler budget (5 due items per bucket per call = 10 per ms per bucket).** 128 voices need 12.8
   voice ticks per ms; if the voice timers share one bucket, ticks run late at very high polyphony
   (the tick compensates elapsed time, so modulation continues in coarser steps). This would be an
   improvement, not just a saving. Open: confirm the real bucket layout (voice timer embedded in the voice
   struct: task at voice+0x12, deadline at voice+0x1E) and measure on hardware before touching it.
4. Not worth it: per-stage arithmetic in the voice tick (change-detected, table driven, no divides),
   the 2 kHz interrupt itself (~20 instructions), the master clock routine.

## Flash space
A naive scan finds 1,238 functions (201 KB) with no direct call and no 32-bit pointer anywhere, but it
includes known-live code (e.g. the loop-editor clamp FUN_000B84DC, reached through tables or PC-relative
references), so it is not usable as is. Space must be proven region by region, as done for EXT
(0x68BF0), the interrupt vectors 96-255 and the replaced filter methods.

## Next step
A CPU-load probe would tell whether any of this matters on the E4: count idle-loop passes per second
(or scheduler skips/lateness) into patch RAM and expose it through a readable parameter, then compare
idle vs 64/128 sounding voices.

## Measured on the E4 (LOADPROBE build, 2026-10-19, recordings/load_probe)
Firmware: `sysex/EOS470_Sync8_LOADPROBE.syx` (diagnostic; Sync8 + probe, `tools/build_probe.py`,
`patches/probe/probe.s`, emulator `tools/emu_probe.py`). Counters: main cooperative loop passes (0x321DE
hook), voice ticks and their lateness (0x60E90 hook), read through SysEx parameter 195
(`tools/hw_load_probe.py`; the Master 'Foreign sampler SCSI ID' field shows junk in this build).
Test preset: program 003 (polyphonic, looped sustain), N held keys centred on 64, MIDI channel 1.
| notes | voices | main-loop passes/s | throughput lost | tick lateness mean / worst (incl. note-on burst) |
|---|---|---|---|---|
| 0 | 0 | 9,093 | - | - |
| 8 | 8 | 8,224 | 9.6 % | 0.43 / 2 ms |
| 16 | 16 | 7,655 | 15.8 % | 0.51 / 4 ms |
| 32 | 32 | 6,249 | 31.3 % | 0.68 / 19 ms |
| 48 | 48 | 5,371 | 40.9 % | 1.10 / 38 ms |
| 64 | 64 | 4,219 | 53.6 % | 1.67 / 53 ms |
| 96 / 128 | 64 / 60 | 4,124 / 4,400 | ~53 % | ~1.6 / 55-66 ms |
Steady state only (worst lateness cleared 1 s after the chord): 16 voices 0.53 / 3 ms, 32 voices
0.69 / 4 ms, 64 voices 1.75 / 6 ms. Note-on burst alone: 6 / 21 / 49 ms worst for 16 / 32 / 64 keys at once.
- Voice control costs ~0.85 % of the CPU per sounding voice (~85 us per 10 ms voice tick), close to
  linear. This preset stops at 64 voices (probably stereo samples: two chip channels each), where about
  half the CPU is left and no control tick misses its 10 ms period (worst 6 ms late).
- Extrapolated, 128 mono voices of a similar preset would need ~100 % -> ticks would fall behind and
  modulation would get coarser. That is where the optimizations above would matter.
- The real per-tick cost is ~4x the static instruction estimate, so most of it is outside the parts
  modelled so far (probably chip-register access with bus wait states and the per-stage work of this
  preset's cords/LFOs/filter updates). A per-stage timer probe (5206e timer 1 counter, MBAR 0x20000100)
  would show which stage dominates before choosing what to optimize.
- Big chords: a 64-note chord delays voice ticks by up to ~49 ms while the note-ons are processed.

## Per-stage timing on the E4 (TIMEPROBE build on stock 4.70, 2026-10-19, recordings/timeprobe)
Firmware `sysex/EOS470_TIMEPROBE.syx` (diagnostic, stock base: `tools/build_timeprobe.py`,
`patches/timeprobe/timeprobe.s`, emulator `tools/emu_timeprobe.py` 26/0, measurement `tools/hw_timeprobe.py`).
Each stage call in FUN_00060E80 (and the tick itself) goes through a re-entrant stack-based wrapper that
reads timer 1 (TCN1). Timer 1: TRR1 = 16500 -> 16,501 counts per 0.5 ms = 33 MHz count clock (30.3 ns),
so the CPU most likely runs at 33 MHz (not 54).
Program 003, held keys (identical per tick at 32 and 64 voices):
| stage | us per tick | share |
|---|---|---|
| cords FUN_0005F89C | 23.3 | 23 % |
| amp FUN_00060B7C | 13.0 | 13 % |
| pitch/loop -> chip FUN_0005FE4C | 11.5 | 11.5 % |
| LFO 1 FUN_00061BC0 | 10.2 | 10 % |
| filter FUN_0005FFD8 | 4.8 | 5 % |
| envelopes FUN_00062208 (2 calls) | 4.3 | 4 % |
| key/velocity window FUN_00062798 | 2.2 | 2 % |
| pitch envelope FUN_0005FD38 | 1.6 | 2 % |
| LFO 2 / aux / Ck (unused by this preset) | 0 | 0 |
| tick body + probe wrapper overhead (~9 wrapped calls x ~2.5 us) | 29 | 29 % |
| whole tick (with probe overhead) | ~100 | 32 % CPU at 32 voices, 64 % at 64 |
Without the probe overhead the tick is ~75-80 us, consistent with LOADPROBE (~85 us incl. scheduler).

Conclusions:
1. The cord processor is the largest stage (~30 % of the real tick) -> candidate 1 (walk only the active
   cords, and skip the multiply when the source value has not changed) is the best first optimization.
2. Amp (13 us) and pitch/loop (11.5 us) are next: both recompute every tick; their chip writes are already
   change-detected, so savings there need cached inputs (recompute only when a contributing value moved).
3. LFO 1 at 10 us per tick is a per-voice cost only for presets that use it.
4. The scheduler is a small share at these voice counts (whole voice ticks ~ all of the measured load).

## Cord processor optimization (Sync8c, 2026-10-19)
`patches/cords/cords.s`, `tools/build_cords.py` (layer on Sync8+TW+HPBP6 -> `sysex/EOS470_Sync8c_TW_HPBP6.syx`,
"EOS 4.70 Sync8c+TW+HPBP6", checksum 0887f675). 66 bytes in interrupt vectors 75-95.
- Note-on: FUN_0005F810's epilogue (0x5F892) jumps to count_build, which stores the number of slots up to and
  including the last enabled cord (0..24) in the unused byte 13 of slot 0.
- Tick: the stock loop FUN_0005F89C runs unchanged but for that many slots: its `moveq #24,d7 ; lea $208(a1),a1`
  (0x5F8A4) is a jsr to cnt_hook (count 0: return at once; count > 24 never written: 24 = stock).
- First tried an active-cord linked list: bit-exact too, but ~31 instructions per active cord vs ~16 in stock,
  so slower above ~9 active cords (751 vs 536 at 24); dropped (backups/cords_list_walker.s). "Skip unchanged
  sources" was not done: unchanged sources already skip both writes in stock, and an exact cache would need
  4 spare bytes per slot (there are 3).
- Emulator `tools/emu_cords.py` (stock vs patched, real FUN_0005F810 setup with random preset cord tables,
  0-24 active cords, internal and external source codes, 12 passes each with changing sources): 13,004
  checks, 0 failures (whole voice block identical except the count byte); random count bytes terminate.
  Instructions per pass (cords in slots 1..n): 0 152 -> 13, 3 200 -> 81, 6 248 -> 147, 12 344 -> 279,
  24 536 -> 543. Other suites on Sync8c: LFO 51,395 / 0, HP/BP 5,761 / 0, Transwave 6,011 / 0, OB-Xa 1,158 / 0.
- Hardware (TIMEPROBE+C = stock + cords + timing probe, `sysex/EOS470_TIMEPROBE_C.syx`, program 003):
  cords 23.3 -> 16.8 us per tick (-28 %), whole tick -6.5 us, CPU in voice ticks at 64 voices 63.8 -> 59.7 %;
  all other stages unchanged within 0.1 us.

## Next stages analysed (2026-10-19): amp, pitch/loop, LFO
- The E4 has the RFX card: FUN_0010E1D4 sets 0x10004D88 = 1 at boot when FUN_0002AC4C detects it, and with
  that flag the amp tick FUN_00060B7C bypasses its change test (`tst.l $10004D88 ; beq skip`) and calls the RFX
  writer FUN_00060674 -> FUN_0010E280 on every tick: it copies vol/pan/flag and the four FX sends into the
  voice's RFX block, rewrites the chip volume byte, and re-derives the sends (those writes are change-tested).
  Measured: preset 000 steady note (no amp modulation) amp stage 15.3 us. Emulator, steady voice: 72
  instructions without the RFX flag, 277 with it.
  -> Candidate A (exact): call the RFX writer only when vol, pan, the update flag, one of the four computed
  sends or the global send offset 0x10004D84 differs from the RFX block / cache. Expected ~-11 us per steady
  voice tick (~12-14 %). Only identical-value chip rewrites are dropped (stock's non-RFX path already relies on
  the chip keeping its values). Validate with a hardware null test (stock vs patched recordings). ~100-150 bytes.
- Cord destinations include the cord amounts (C00Amt..C23Amt at amp block 0x210 + 16 n) and the RFX sends
  (SndMain/SndAux1-3 at 0x1FA..0x206).
  -> Candidate B: at note-on drop cords whose amount is 0 unless another enabled cord targets that slot's
  amount; their sources are then not marked used, so e.g. an LFO only reached through zero-amount cords is not
  computed (~11 us per tick on preset 000). Bit-exact except random-shape LFOs (shared seed 0x1000229C):
  exclude those to stay bit-exact.
- Pitch/loop (FUN_0005FE4C, 11 us with constant pitch) and LFO 1 (10 us) are ~60-instruction straight-line
  paths running at several cycles per instruction (voice data in DRAM); an exact early-out would read the same
  inputs it compares, so no worthwhile saving.

## RFX amp-path skip (Sync8d, 2026-10-19)
`patches/rfx/rfx.s`, `tools/build_rfx.py`: FUN_00060674 rewritten in place (272/272 bytes) + vol_only (36 bytes,
vectors 116-127). Same computation and block writes as stock; when called from the amp tick with flag 0 and
vol, pan, the four sends and the send offset 0x10004D84 (low word, cached in cord-slot spare bytes voice+0x28C /
0x29C) unchanged, FUN_0010E280 is replaced by its one unconditional write, the chip volume byte (+0x71).
- Stock detail (capstone does not print index scale): the Multimode channel sends are read with
  `move.w $30(a4,d7.l*2)` (ext word 0x7A30, scale 2) = channel + 0x50 + 2 i. The first build read 0x40 + i and
  the emulator test caught it.
- First hardware null test (TIMEPROBE+C+R, version without the volume write): steady and FX-send takes
  jumped between -45.08 and -44.74 dB (both channels, +0.34 dB) where stock holds -45.08: something else
  nudges the chip volume byte by one step and stock's per-tick rewrite restores it. Fixed by keeping that write
  (vol_only); the emulator test now also requires every stock volume-byte write to be made (it fails the
  first version immediately).
- Emulator `tools/emu_rfx.py` (real FUN_000609D8 note-on and FUN_00060B7C ticks, mono/stereo, random changing
  inputs incl. Multimode sends, mode, offset): 12,300 calls, 0 failures; RAM and chip state identical, every
  stock chip-volume write made, stock-only writes are value-preserving; 72 % of chip-writer calls reduced to the
  volume write. All other suites 0 failures on Sync8d.
- Second hardware null test (TIMEPROBE+C+R2, volume byte rewritten every tick, pan/send work skipped):
  steady/send takes constant -47.56 dB vs stock -45.08 (-2.5 dB), trem/pan off by 2-4 dB; residual vs stock
  -12 dB against a -45..-48 dB same-firmware floor (recordings/rfx_null, null_ref_vs_rfx2.json).
  Conclusion: on the RFX hardware chip-register writes have side effects; the chip output depends on stock's
  per-tick write sequence (volume byte plus the send words it re-sends), not just on final register values.
  The emulator models the chip as plain memory and cannot see this. **Candidate A is rejected**; Sync8d is not
  for use (sysex/EOS470_Sync8d_TW_HPBP6.syx kept only as a record). Any further optimization must keep every
  chip write stock makes, in order; only pure RAM computation can be saved.
- Third null test (plain stock TIMEPROBE vs the cord build's references): stock steady/send -49.5 dB vs -45.08
  (cord build) and -47.56 (RFX v3 build); trem peaks identical (-24.8 dBFS) on every build; stock takes show the
  same one-step jumps (-49.20/-49.24) as the RFX v1 build. So the steady level of an RFX voice appears to vary
  from boot to boot independently of the firmware, and every comparison so far crossed a reboot. The RFX
  rejection above is therefore NOT established; neither is the cord patch confirmed. Next: same-firmware
  power-cycle test; if boots differ, compare builds inside one boot with a runtime A/B switch.
- Power-cycle test (stock TIMEPROBE, two boots): -49.5 dB both times (with the same 0.3 dB jumps) -> boot-to-boot
  variation is small. The cord build (TIMEPROBE+C, image differs from stock only by the 66-byte patch and its two
  hook sites) measured -45.08 in an earlier session. No mechanism found: the cord count byte (slot 0 byte 13) is
  not touched by the RFX voice setup FUN_00060334 (it writes only amp block + 0x1F8..0x207 and the RFX block),
  and the caller of FUN_0005F810 reloads all registers it uses. The sessions differed in history (the cord-build
  session ran program-003 timing sweeps, program changes and all-notes-off before the takes), so all
  cross-session comparisons are confounded. Next: runtime on/off switch (SysEx param 195) and alternating
  on/off takes in one session.

## In-session A/B verdict (2026-10-19, `sysex/EOS470_AB_switch.syx`, `tools/build_ab.py`, `tools/hw_ab_null.py`)
A/B build: stock + timing probe + cord patch + RFX skip (v3, with the volume write), each switchable at runtime
(switch byte 0x100003F0, SysEx parameter 195 = 32 + bits; OFF = stock code paths: 24-slot cord loop and no count
byte, stock FUN_00060674 body via an 8-byte jump to a dispatcher). Emulator: switch 0 byte-identical to stock
(cords 13,004 / 0, RFX 12,300 / 0 without masks), switches 1/2/3 exact as before; probe 26 / 0.
Null test in one session, modes off/cords/rfx/both cycled 3 times per scenario (recordings/ab_null):
- send: all 12 takes -50.28 / -49.96 dB (identical to 0.001 dB); residuals at the OFF-vs-OFF floor.
- steady: all modes -49.96 dB; the only outlier is an OFF take (-50.27): the 0.3 dB step is stock behaviour.
- trem / pan: mode differences (+-0.2 dB) inside the OFF-vs-OFF spread (0.4 dB); residuals at the floor.
=> Both patches are sound-neutral. The earlier cross-session level differences (-45 / -47.6 / -49.5 dB) were
   session history, not firmware.
Timing in the same session:
- program 003, 64 voices: cords 24.1 -> 17.05 us (-29 %), whole tick 100.3 -> 93.6 us, CPU in voice ticks
  64.3 -> 59.9 %; amp unchanged (12.86 / 12.87 us: its voices change every tick).
- steady single voice (preset 000): amp 15.30-15.37 -> 14.88-15.05 us, whole tick -2.7 us (~2 %): the kept chip
  volume write costs most of the time, so the emulator's instruction-count estimate (-11 us) does not hold.
Decision: adopt the cord optimization (Sync8c); do not adopt the RFX skip (neutral, but ~2 % for steady voices
only, for a 272-byte rewrite).
