# On-board slicer: Beat Munger "Slice" key (EOS 4.71-beta2)

Builds: `tools/build_beta2.py build/eos471_beta.bin build/eos471_beta2_slc.bin` → `sysex/EOS471-beta2-slicer.syx`
(checksum 0886a24e, with zero-crossing snap; not yet on hardware). Earlier builds: 0886aa77 cut every attack, and 0886a8c0 (pre-roll) is confirmed working (below).

## Use

1. Sample Edit → Beat Munger on a drum loop; set the sensitivity until the slices are right (re-Anlyz).
2. Press **Slice** (the soft key between Cancel and Stop).
3. The E4 makes one new sample per slice, named `<first 12 characters of the name> 01`, `02`, …, in the first
   free sample slots. It also makes a new preset in the first free preset number, named after the sample: slice 1
   on key 36 (C1), each next slice one key up, each zone's original key = its own key, so every slice plays at its
   own pitch. Then it leaves Beat Munger and selects the new preset. The status line reports
   "Sliced: N samples, preset P".
- The source sample is not changed. The clipboard is kept, and the Sample Edit region is put back.
- Each cut is 512 frames (about 11 ms) before Beat Munger's onset. Slice 1 starts at the sample start (anything
  before the first cut is part of it), and the last slice runs to the end. Cuts less than 1,024 frames (about 23 ms)
  apart, or less than 1,024 frames from the end, are dropped.
- Each cut then moves back to the last zero crossing of the first channel within 256 frames (about 6 ms), so a slice
  never starts mid-waveform. Cuts only move earlier, never into the attack; with no crossing in range, a cut stays
  where it is. Samples are read through the sample port the way the Beat Munger analyser reads them (0x956D4 sets
  the address, the chip register +0x1C returns the next sample, 0x95BA4 afterwards), after the memory check, using
  the current base. At most 92 slices
  (keys 36–127).
- If it can't do it, nothing is changed and the status line says why: no slices, no free sample slots or preset, or
  not enough sample memory. After "not enough sample memory" Beat Munger is left as well (the memory check can move
  sample data).

## Space

`patches/portmap/portmap.s` replaces the two plugin port-map builders at 0x15EF5C/0x15F3E0:

- **Stock:** 2,236 B of unrolled `pea` rows, 29 calls to 0x15D50C.
- **Replacement:** a 196 B table-driven loop. Rows of (idx, first value, count) come from stock (`rows.inc`).

A stays at its entry; the member-pointer longword 0x15FAD4 → pm_B. That frees 2,040 B at 0x15F020–0x15F818.
`tools/emu_portmap.py` checks it: in 400 random runs the call logs, d0, the callee-saved registers and sp all match
stock, and 23/24 mutations are caught.

The slicer code takes 1,154 B of that block, leaving 882 B free.

## How it works (`patches/slicer/slicer.s`)

**Inputs**
- **Slice list:** BeatPlayer `*(0x100042F4)`: +0x23A count, +0x23E entries.
- **Entry format:** the analyser builds it at 0xE9AA6 as `(0x40000000 | channel base) + 2·nch·frame`.
- **Analysis frames:** they count from the channel base. The analyser reads `base + 2·(block·hop)` per channel,
  0xE9F34.

**Region mapping.** Copy Section's region frame r reads `base + start + 4 + 2r` (0xF6F78). So
r = frame − 2 − start/2, clamped to 0 … len − 5, which is Sample Edit's own region limit
(0x48D88: 0x13D5E0 − 5).

**Order of operations**
1. **Checks (no side effects):**
   - stop the audition; if it is still playing, defer through 0x10003EE8, as OK does;
   - pass 1 counts the slices and the memory needed;
   - check free slots 1–999 and a free preset 0–999.
2. **Memory:** voices off (0x23E84) and 0x13DF14, as the op wrapper 0xFB564 does. Then call 0x13E3C8 with the sum of
   Copy Section's own size formula (0xF72F2) over all slices. Entries are converted against the base saved before
   this call, because it may compact sample memory.
3. **Commit:** pass 2 writes the region starts over the entry list.
4. **Samples, per slice:**
   - set region E14/E18/E0E;
   - 0xF7050 copies the region into slot 0;
   - register the next free slot (0x13E854), copy the 0x5C header into it, unregister slot 0 (0x13E8C8);
   - name the sample (0x13D48C).

   The clipboard header is saved before the loop and registered again after it. Its data is never touched, because
   nothing compacts memory between the check and the end.
5. **Preset:**
   - 0x13C52C makes the default preset;
   - zone 1 is voice 0's first zone, and further zones come from 0x50E40 (the voice is re-fetched every time);
   - set zone fields +0/+3 key range, +1/+2 fades 0, +8 sample, +12 original key;
   - 0x13CD68 names it, 0x13A484 selects it.
6. **Finish:** 0x13DF14, voices on (0x23F14), 0xB6080 (Beat Munger exit), status 0x1A20D8.

**Emulator test.** `tools/emu_slicer.py` replaces every routine above with a Python model. Results: 600 random cases
with 0 failures, and all 6 planted mutations caught. See its docstring.

## Not verified yet (hardware)

- Stereo: the entry ↔ frame mapping is taken from the analyser's own formula and is exact either way. Whether Beat
  Munger's onsets land on the transients in stereo should be checked by ear.
- The new samples get Copy Section's loop points (loop start 12, loop end = end − 10) and the source's loop mode.
  With a looped source, every slice loops.
- Selecting the new preset from inside Sample Edit (0x13A484) without the Preset Manage screen refresh (0xB16E0).
- Default-preset details: the voice key range and other voice parameters stay as 0x13C52C makes them.

## Hardware result 1 (2026-10-22, build 0886aa77, MINF 16, no pre-roll)

The user's stereo 2-bar loop became P005 with 13 slices.

- **Measurement:** `hw/slicer/raw.wav` (the raw sample) and `p005_k36..48.wav`.
- **Slice positions:** each slice matches the raw audio (correlation 0.99–1.00), so the onset-to-frame mapping
  (stereo /4) is right.
- **The problem:** every cut came 5–8 ms after the attack began, because Beat Munger's onsets lag the attack (about
  one analysis block). That clipped every hit, and the loop's first 7 ms became a slice of its own (key 36).
- **Plot:** `hw/slicer/p005_cuts.png`.

**Fix:** cut PRE = 512 frames before each onset, and raise MINF to 1,024 frames.

## Hardware result 2 (2026-10-22, build 0886a8c0, PRE 512, MINF 1024)

Same loop; it now makes 12 slices, and the 7 ms sliver is gone. Recordings are in `hw/slicer/fix/`; the plot is
`p005_cuts_fixed.png`. The user confirmed a second loop also works.

- Every cut moved exactly 11.6 ms earlier, which is 512 frames at 44.1 kHz.
- Each slice matches the raw take (correlation 0.98–1.00).
- Each attack now starts after its cut: 4–8 ms after on the strong hits, 0–2 ms after on the hi-hats (keys 38, 41,
  43 and 47).
- **Remaining:** a cut can fall mid-waveform in the previous hit's tail (keys 43 and 46), which may click at the slice
  start. Possible next step: snap each cut to the nearest zero crossing, or add a short fade-in.

## Hardware result 3 (2026-10-22, build 0886a24e, zero-crossing snap)

Same loop, P005, 12 slices. The recordings are in `hw/slicer/zc/` and the plot is `p005_starts.png`.

- Cuts moved 0–2.5 ms earlier, never later, as designed.
- **Start clicks:** the high-frequency burst at the slice start fell by 1.3 dB on average, and by 4–6 dB on keys 36, 38
  and 45, which now start near zero.
- **Keys 40, 46 and 47 are unchanged:** there is no crossing within 6 ms (a low-frequency kick tail under the hats),
  or the crossing is steep and noisy, so the first sample is still large.
- **Conclusion:** a snap alone can't guarantee a click-free start. A short fade-in on each new sample (read the first
  frames through the port, ramp them, write back with 0x957B0) would.
- **Decision (user, 2026-10-22):** keep the slicer as it is (pre-roll plus zero-crossing snap, no fade-in).
