# LFO tempo sync (EOS 4.70 + OB-Xa v3d)

Build: `tools/build_lfosync.py build/eos470_obxa_v3d.bin build/eos470_v3d_lfosync.bin`
→ `sysex/EOS470_OBXa_v3d_LFOsync.syx` (header "EOS 4.70 v3d+LFO Sync"). Test: `tools/emu_lfosync.py`.

## What it does
LFO 1 and LFO 2 **Rate** go past 18.01 Hz (127) into 16 tempo divisions:

| value | 128 | 129 | 130 | 131 | 132 | 133 | 134 | 135 | 136 | 137 | 138 | 139 | 140 | 141 | 142 | 143 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| shown | 4bars | 2bars | 1bar | 1/2. | 1/2 | 1/4. | 1/2T | 1/4 | 1/8. | 1/4T | 1/8 | 1/16. | 1/8T | 1/16 | 1/16T | 1/32 |
| MIDI clocks / cycle | 384 | 192 | 96 | 72 | 48 | 36 | 32 | 24 | 18 | 16 | 12 | 9 | 8 | 6 | 4 | 3 |

- Clock = the master sequencer/arpeggiator clock (Master → MIDI clock source). Internal: follows the
  sequencer/arp tempo. External: follows incoming MIDI clock, phase-locked to MIDI Start/Song Position.
- **Sync = Key Sync**: cycle restarts at note-on, rate locked to tempo.
  **Sync = Free Run**: phase locked to the song grid (tick 0 = Start), all voices in phase.
- In sync mode, Rate cords (Lfo1Rt/Lfo2Rt), Variation and the LFO trigger (Lfo1Trg) are ignored;
  Shape, Delay and all LFO destinations work as before. Random shape steps once per cycle.
- External clock: between MIDI clocks the phase is interpolated from the measured quarter-note time,
  so slow MIDI clock does not stair-step. If the clock stops, synced LFOs hold.
- Values 0..127 run the stock code (emulator: bit-identical struct and random seed vs v3d).

## How (firmware facts)
- LFOs are CPU-computed per voice, 10 ms control ticks: tick FUN_00061BC0 (LFO 2: FUN_00061D5C adds the
  lag processors), init FUN_00061A50 at note-on from preset voice bytes +0x96..0x9A / +0x9E..0xA2
  (rate, shape, delay, variation, sync; sync 0 = key sync: phase 0, 1 = free run: phase from ms timer).
  Struct words: +0 rate-cord sum, +2 out, +4 out+0x800, +0xE delay, +0x10 base rate, +0x12 phase,
  +0x14 wave table (0x6C76E + shape·0x200, 0 = random), +0x18/+0x1A trigger now/previous.
  Rate table 0x61EBC (phase step/2 per 10 ms; 0.076 Hz .. 18.0 Hz).
- Clock: 0x10000428 master ticks (PPQ 0x1000041E = 480 default, PPQ/24 per MIDI clock at 0x10000420),
  0x1000042C = 1 external; MIDI clock handler FUN_000216C0 (0x10000440 clock count in quarter,
  0x10000444 µs per quarter, 0x10000448 quarter time); internal advance FUN_0002172C (ms interrupt);
  tempo → FUN_000217FC(µs per tick). Clock mod sources FUN_000625F8 (relative to note-on tick, voice+0x2E).
- UI field descriptors (0x22 bytes: id, name, min, max, offset, ?, width, scale, fmt, get, set):
  LFO Rate 0x6B5B0 / 0x6B65A (formatter 0x6A880, "%2d.%02d" from tables 0x6E970/0x6E9F0).
  Editor/SysEx voice descriptors: 0x5AC6A (param 105), 0x5AD14 (110). Patch sets max = scale = 143.
- Code space: 0x20400-0x205FF, the unused interrupt vectors 128-255 (zero in 4.70, copied into the
  RAM vector table at 0x10000000 by the startup loop; nothing in the image reads them). 498 / 508 bytes.
  The image cannot simply grow: 0x1F86F0-0x1FFE80 is .data (copied to 0x10000400), and the flash
  above the OS is unmapped territory (Resident FLASH check still pending).

## Hardware results
- Sync (2026-10-18): stock rates exact on hardware (32/64/96 → 1.4879/4.1190/9.1564 Hz vs table
  1.4877/4.1199/9.1553; LFO2 rate 64 → 4.1181 Hz; LFO2 cord source code = 104). Rates 128..143
  accepted over SysEx, but **synced LFOs did not move**: after boot the master clock rate 0x10000434
  stays 0 (FUN_0002191c resets the clock without setting it) until the arp tempo is changed or the
  sequencer sets a tempo, so the master tick and the stock Ck* sources are frozen.
- Sync2: on a synced note-on with the clock never started, call the stock arp tempo setter
  FUN_00193F88(arp tempo 0x1000719C) (= what editing the arp tempo does). Names moved to EXT
  (0x68BF0) to make room. `sysex/EOS470_OBXa_v3d_LFOsync2.syx`, emulator 50,489 checks / 0 failures.

- Sync on hardware, LFO → Pitch (AmpVol only shows the negative half; use Pitch + instantaneous
  frequency): once the clock was running, internal 1/4 = **2.0005 Hz at 120 BPM** (exact). With MIDI
  clock arriving (sequencer Clock Source / Tempo Control = External) EOS's master tick ran at
  internal + external: 60 BPM clock → 180 BPM, 100 → 220, 140 → 260 (generator verified exact).
- Sync3: MIDI clock no longer goes through the master tick. Hooks in the MIDI realtime parser
  FUN_00135DF8: F8 `jsr 0x136B0C` (empty stub, at 0x135F1E) → midi_clk (count, timestamp, period EMA),
  FA `jsr 0x136B10` (0x135F2C) → midi_start (count = 0, then stock). Patch RAM 0x100003F0..FB = RAM
  vector slots 252-254 (EOS never installs vectors at runtime). Any F8 in the last 250 ms → LFO phase
  from the F8 count (+ fraction of the current clock); otherwise the internal tick.
  `sysex/EOS470_OBXa_v3d_LFOsync3.syx`, emulator 50,493 checks / 0 failures.

- Sync3 on hardware (Pitch method): internal exact (stock 64 → 4.1193 Hz; 1/4 → 1.9998 Hz, 1/8T →
  6.0001 Hz at 120 BPM). Under MIDI clock still internal + external on LFO1 and LFO2 (60 → +200%,
  100 → +120%, 140 → +86%), so the F8 hook itself sees an extra 120 BPM stream (48 F8/s) besides the
  828's clock. No clock comes out of the E4 to the computer (no external loop). The parser FUN_00135DF8
  serves 5 port structs (0x102C94EA + n·0x256); the extra stream presumably arrives on one of them.
- Sync4 test (`sysex/EOS470_LFOsync4_test.syx`): F8 counted only from ports in MASK (0x100003EC);
  default ports 0+1; TEST ONLY: a synced LFO's Variation 1..5 selects port 0..4 alone.
  hw_lfosync3_test.py V measures which port carries the 828 clock and which the internal stream.

- Sync4 test on hardware: Variation 0 (ports 0+1) and port 0 alone lock exactly (1/4 at 100 BPM =
  1.6664 / 1.6658 Hz); the 828 clock arrives on port struct 0. With the port filter:
  MIDI clock 60/100/140 BPM, 1/4, 1/8, 1/8T, LFO1 and LFO2: all within ±0.07%.
  Key Sync: phase at note-on 0.99..0.02 cycle for 6 notes at random times (spread 4°).
  Free Run: phase vs the MIDI clock grid identical for all notes (spread 0.2°).
  Clock stopped with Clock Source External: synced LFOs hold (master tick frozen, as stock Ck* sources).
- **Sync5 (final)**: port filter fixed to structs 0/1, Variation test selector removed.
  `sysex/EOS470_OBXa_v3d_LFOsync5.syx` ("EOS 4.70 v3d+LFO Sync5"), emulator 50,497 checks / 0 failures.
  Differs from the hardware-tested Sync4 test only in header, cave layout and the F8 hook target.

- **Sync5 on the E4 (2026-10-18)**: MIDI clock 60/100/140 BPM, 1/4 · 1/8 · 1/8T, LFO1 + LFO2: all within
  ±0.11%. Key Sync phase at note-on spread 3.5°; Free Run phase vs clock grid spread 0.2°.

- User test, preset 006 under DAW clock (2026-10-18): "short truncated notes" = the patch itself
  (voice 0: synced 1/4 sawtooth -> FilFreq into a 2-pole at freq 3; voice 1: Ck8th -> Lfo1Trg). With
  Clock Source External and no clock the LFO holds, so the gating only appears once the clock runs.
  User confirmed it working. Caveat: stock Ck* sources still use the master tick, which runs at
  internal + external tempo under MIDI clock (not patched).

- **Sync6** (`sysex/EOS470_OBXa_v3d_LFOsync6.syx`, "EOS 4.70 v3d+LFO Sync6"), emulator 50,689 checks / 0 failures:
  * Master tick fix: the stock `jsr FUN_000216C0` at 0x135F24 is NOPed; midi_clk2 jumps to it after
    counting, so only F8s from the physical ports advance the master tick. Under MIDI clock the
    sequencer, arpeggiator and the stock CkDwhl..Ck16th sources now follow the real clock (before:
    internal + external). Internal mode unchanged (FUN_000216C0 is a no-op there). In External mode
    with no MIDI clock the master tick now holds instead of running at the internal tempo.
  * LFO shape 16 "saw down": init points the wave at the rising saw table (shape 2, 0x6CB6E) with
    bit 31 set; lookup hook at 0x61C84 (jsr lfo_look) strips the flag and uses index 255 - i.
    Shape name via the stock formatter (masks at 0x6A8E8/0x6A8F2 0x0F -> 0x1F, .data entry 16 at
    0x1FB664 -> "saw down"); Sync formatter (0x6A90C) gets its own table at 0x660B0 (OB-Xa tail).
    Shape max 15 -> 16 in UI fields 0x6B5D2/0x6B67C and SysEx params 106/111 (0x5AC8C/0x5AD36).

- **Sync6 on the E4 (2026-10-18, preset 000)**: shape 16 accepted; saw down 98% falling ramp steps vs
  sawtooth 98% rising (both 4.12 Hz at rate 64). CkQtr -> Pitch under 100 BPM MIDI clock 1.670 Hz
  (expect 1.667; Sync5/stock ran internal + external), holds with the clock stopped. Synced rates
  60/100/140 BPM, LFO1/LFO2: all within ±0.06%. Key Sync spread 5.7°, Free Run vs grid 0.2°.

## Hardware test plan
1. Master: set the sequencer/arp tempo (e.g. 120), voice LFO1 Rate = 1/4, Shape sine, cord Lfo1~ → AmpVol
   (or FilFreq). Hold a note: 2 Hz tremolo. Change tempo: rate follows.
2. Clock source External, play MIDI clock from the DAW at 100 BPM: tremolo locks to the DAW grid;
   Free Run: in phase across notes and with the DAW bar; Key Sync: restarts per note.
3. LFO2 the same (1/8T). Rates 0..127 must sound exactly as before.

## Sync7: tempo flywheel when MIDI clock stops (2026-10-18)
Problem: with Clock Source External, synced LFOs (rates 128..143) froze when the MIDI clock stopped
(no F8 for 250 ms -> master tick path, and the master tick holds in External mode).
- lfo_tick: when the clock is gone and Clock Source = External (0x1000042C == 1), the phase keeps coming
  from the MIDI clock count, extrapolated with the last smoothed period (flyfrac): dt <= 1 period:
  interpolate as before; 1..2 periods: hold at the next clock (late-clock tolerance); > 2 periods: run
  on at the last tempo, continuous (the LFO ends up one clock behind). Internal mode: master tick as before.
- midi_clk2: dropped clocks (gap < 250 ms) catch the count up by round(elapsed clocks), so the LFO does
  not jump back. After a real stop (gap >= 250 ms) the count continues from the stop: the sender's song
  position did not move, so the flywheeling LFOs snap back onto its grid on resume. MIDI Start still
  resets to 0. First measured period is taken as is (was smoothed up from 0).
- Not changed: the master tick (sequencer, arp, stock Ck* sources) still holds while the clock is stopped.
  Song Position Pointer is not followed (Continue resumes from the count at the stop).
- Space: midi_start/midi_clk2 moved from EXT to the header pad, lfo_fmt from the header to EXT;
  HPBP's 4th-HP thunks/descriptor and BP boost moved into its own free method tails, its .hdr2 to 0x201C0.
  Cave 488/496, EXT 138/176, header 308/320.
- Emulator: LFO 51,089 / 0 (flywheel phase incl. 1-hour stops and internal-mode fallback, catch-up
  model, Start), Transwave 6,011 / 0, HP/BP 5,761 / 0, OB-Xa LP 1,158 / 0. 120 BPM stop/resume
  simulation: one-clock hold at the stop, then constant rate; no jump on dropouts.
`sysex/EOS470_Sync7_TW_HPBP6.syx` ("EOS 4.70 Sync7+TW+HPBP6", checksum 0887ca8a) = HPBP6 + Sync7.

### Sync7 on the E4 (2026-10-18, preset 000, LFO1 sine 1/4 Free Run -> Pitch, 100 BPM, Clock Source External)
- First run invalid: the DAW was also sending MIDI clock (~95 BPM) to the 828 port; CoreMIDI merges it with
  ours, so every synced rate read ours + 95 BPM (60/100/140 BPM: +1.585 quarter/s each). Keep other
  clock senders off the 828 port during tests.
- Clean run (recordings/flywheel_sync7b): running 1.663 Hz, phase flat within 0.4 deg. Stop (FC): holds
  one clock (-13 deg; 1 clock = 15 deg at 1/4), then runs on at 1.678 Hz (100.7 BPM, +0.7%) with no
  jump. Continue (FB) after 4 s: back on the sender's grid (-4 deg vs the clock count).
- Dropouts of 4 and 8 clocks: rate unchanged, but each left the LFO exactly one clock (-15 deg) behind:
  the catch-up counted the flywheel's virtual position (which includes the one-clock hold).
- **Sync7b**: catch-up = round(dt / period) clocks when that is >= 3 (a gap of >= 2.5 periods), else 1
  (jitter never adds counts: emulator stream with dt 1..30 ms around 15 ms counts 400 of 400).
  After a dropout the LFO jumps forward by the held clock and stays on the grid.
  `sysex/EOS470_Sync7b_TW_HPBP6.syx` ("EOS 4.70 Sync7b+TW+HPBP6", checksum 0887c905); emulator LFO
  51,089 / 0, Transwave 6,011 / 0, HP/BP 5,761 / 0, OB-Xa LP 1,158 / 0.

### Sync7b on the E4 (2026-10-18, recordings/flywheel_sync7c, same setup, DAW clock off)
- Stop/resume: running 1.663 Hz, phase flat within 1 deg; at the stop one held clock (-15 deg), then the
  flywheel runs at 1.671 Hz (+0.2%, drift ~+1 deg/s) with no jump; after Continue back on the sender's grid
  (0.0 deg vs the clock count at 8.9 s).
- Dropouts of 4 and 8 clocks: phase within +/-2.4 deg of the wall-clock grid throughout (Sync7: -15 deg
  per dropout). Rate 1.663 Hz in every segment.
- Windows after ~9.5 s are past where preset 000's tone breaks up (also in the stock-era takes); ignored.

## Sync8: whole master clock flywheel, boot clock start, pan fix (2026-10-18)
Master tick 0x10000428 consumers: Ck sources (FUN_000625F8), arpeggiator (0x193xxx, timing 0x1000718C),
Beats/riffs (FUN_00196324), note-on tick stamps (FUN_0005E56C), timer-queue events (FUN_0002118C).
Song tick 0x10000424 (runs only while the transport flag 0x1000041C is set): sequencer 0x17F5xx-0x1874xx.
- Master flywheel (user choice: whole master clock): hook at 0x21732 in FUN_0002172C (1 ms) replaces
  `tst.l $10(a0) ; bne.b rts` with `jsr mclk_hook`. Internal clock: returns into the stock code (a0 kept).
  External: when the MIDI clock is > 2 periods late, TICK += TPC*256/PER per ms (16.16 accumulator in
  RAM vector slot 255, 0x100003FC); otherwise nothing (stock). Ck sources, arp, Beats and timer events
  keep running at the last MIDI tempo; the sequencer still stops with the DAW (song tick untouched).
  On resume the stock F8 handler continues from the flywheel position (no jump for Ck/arp).
- Code in interrupt vectors 96-127 (0x20380-0x203FF): all the default "Fatal: Gen Trap error" handler;
  no code reads RAM vector slots 64-251 (only the startup copy); EOS programs vectors 64-74. 80/128 bytes.
- Boot fix: lfo_init starts a never-started master clock (CLKRATE 0) at the arp tempo on every note-on,
  not only synced ones -> Ck sources/arp/Beats run after power-on without touching the tempo.
- Pan fix (notes/pan_bug.md): 0x60A50 E885 -> EA85, 0x60BEA E881 -> EA81.
- Emulator: LFO suite 51,395 / 0 (new: flywheel model incl. 1-hour stops and 4 TPC values, internal mode
  bit-identical to stock, boot start, pan words; negative control on Sync7 fails all five), Transwave
  6,011 / 0, HP/BP 5,761 / 0, OB-Xa LP 1,158 / 0.
`sysex/EOS470_Sync8_TW_HPBP6.syx` ("EOS 4.70 Sync8+TW+HPBP6", checksum 0887e3d7).

### Sync8 on the E4 (2026-10-18, preset 000, Clock Source External, DAW clock off)
- Pan fix (recordings/pan_sync8): voice Pan (id 40), Multimode Pan (id 249) and CC10 now sweep the whole
  range; L-R dB: -64/CC0 +72.2, -32/CC32 +15.9, -16/CC48 +6.4, 0/CC64 -0.25, +16/CC80 -6.9, +32/CC96 -16.2,
  +63/CC127 -72.2 (stock: hard at +/-32). Same on Sub 1-3 (same preset on MIDI channels 2-4, Quantum
  21-26): identical curve, subs ~0.7 dB hotter.
- CkQtr -> Pitch (recordings/flywheel_sync8/C_short): edges every 300 ms with the clock; at Stop one
  351 ms interval (the 2-clock wait), then CkQtr keeps running through the stop at ~294 ms (~2% fast,
  within the 10 ms control-tick granularity of a 9-interval average); Continue: no jump.
  Note: preset 000's sine is not looped (~10 s at the root pitch); CkQtr's +pitch half makes it end at
  ~8.2 s, which first looked like the voice dying at Continue (same with clocks through the stop and
  with a gap and no Stop/Continue).
- LFO stop/resume unchanged from Sync7b (1.663 Hz, one held clock, back on the grid after Continue).
