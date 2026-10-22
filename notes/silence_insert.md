# Leading silence: pad on WAV/AIFF import and Sample Edit "Insert Silence" (EOS 4.71-beta2, 2026-10-21)

Static analysis only (beta2 image); key points spot-checked. Not yet emulated or built.

## Import path (option 1)
- WAV/AIFF load as banks: disk load ~0xA6A00 -> 0xA7218 -> 0x19A47C(file, 'BANK', slot, append, cb) -> format driver
  `+4` (driver tables in .data, RAM copy at 0x10000400+): WAV-A import 0xF06BC, AIFF 0xF38A4, WAV-B (older per-sample
  loader via the 'SMPL' sub-driver 0xF22AC) 0xF2350. WAV-A refuses non-PCM, > 2 channels, > 16 bit (no 24-bit).
- No malloc: sample RAM is a bump allocator (next free at 0x10004FF0; 0x13EA18 size check). Header 0x5C bytes at
  `*(0x10004FF8) + slot * 0x5C`: +0x14/+0x18 start L/R, +0x1C/+0x20 end, +0x24/+0x28 loop start, +0x2C/+0x30 loop
  end (byte offsets of 16-bit data), +0x34 rate, +0x38 flags (0x200 mono / 0x600 stereo), +0x3C L base, +0x40 R base.
- Frames are written through the sample-RAM port 0x957B0(dst | 0x40000000, src, len). Copiers: WAV-A 0xF053C,
  AIFF 0xF3724 — identical 8-byte prologue `4E56 FFF8 4FEF FFD8` (checked), args d0 = write start, d1 = file,
  a1 = callback, sp+4 = R offset, +8 bytes, +12 channels, +16 bits; one caller each. WAV-B copies inline
  (0xF30A4–0xF33D6).
- Finalise (all importers): 0x13E82C, 0x13D614, 0x13E810, **0x13D8C4 -> 0x13D7E4(slot, ch)**: clamps loops and
  writes zero guards with 0x957B0: 4 bytes at base, 4 at base + end − 2, 8 at base − 8 (checked: pea 4 / 4 / 8).
  => **every import loses its first 2 frames and last frame to zeros**, and for stereo the R pre-guard (R base − 8)
  lands on L's last 4 frames (inferred from the layout). The "Left/Right/Mono Start/End Zero!!" strings belong to a
  diagnostic (0x175494) that checks those guards; it is not part of import.
- Patch: replace both copier prologues with `jmp hook; nop`; the hook zero-fills N words per channel (source: 16 zero
  bytes at 0x13EBCC, N <= 8), moves the write start and R offset by 2N, adds 2N to header +0x1C/+0x20/+0x24/+0x28/
  +0x2C/+0x30/+0x40, then runs the original prologue. 0x13DF14 re-sizes the allocation from the header. Optional: pad
  4 trailing words too (end + 2N + 2) so the end guard does not eat the last frame. WAV-B needs its own hook at 0xF3072.
- Size: shared hook ~140–180 bytes + 16 bytes patched; WAV-B hook ~100 + 6.

## Sample Edit (option 2)
- Menu tree 0xA40B4 (225 × 18-byte entries: name, short name, soft-key handler, arg, level, flags); counts are
  computed at run time. Sample Edit "Utils I" = Cut, Copy, Paste, Truncate, Taper, **empty slot 0xA4AB0** (checked);
  more empty slots at 0xA4B1C, 0xA4B9A, 0xA4C2A. A new item is an in-place rewrite of one 18-byte entry.
- Operation dispatch table 0xFB81E: 24 × 40-byte entries (code, names, undo mode, dialog flags, prep hook, exec), count
  hard-coded (`moveq #24` at 9 sites, base at 5 sites), followed directly by strings: adding an op means relocating
  the table (~1 KB). Paste exec pointer at 0xFB8E2 = 0xF79D4 (checked).
- Paste in Insert mode already does everything needed: 0x13E3C8 free-memory check (mandatory: the gap opener ignores
  failure), 0xF7464(N, pos) opens an N-frame gap per channel (moves the arena up, fixes other samples' block pointers,
  shifts loop/end points at or after pos), 0xF7988(N, pos) zero-fills the gap; undo, voice lock and redraw come from
  the exec wrapper 0xFB564.
- Small plan: soft-key handler cloned from Truncate (0xB54B0) with N = region length or a fixed 4/8, pos = region
  start; Paste's exec pointer -> a wrapper that runs the silence path for our handler and falls through to 0xF79D4
  otherwise. Undo/progress text would say "Paste". ~200 bytes. Clean version (own op code, relocated table): ~1.2 KB.

## Space
beta2 free: ~124 bytes in the filter region + unused default vectors (runs of 132/48/32/16) + a 20-byte gap, all
fragmented. Option 1 (WAV-A + AIFF hook) or option 2 (small) fits on its own; both together, or option 2's clean
form, need space freed first (e.g. debug strings ~2.4 KB, RFX help text compression ~9 KB; notes/optimization.md).

## Built: Insert Silence in EOS 4.71-beta2 (2026-10-21, checksum 08881df5, sysex/EOS471-beta2.syx)
`tools/build_beta2.py build/eos471_beta.bin OUT` = LP+Fuzz release + patches/silence/silence.s.
- Sample Edit > Utils I, slot 6 (0xA4AB0): "Insert Silence" (soft key "Silnc"). Inserts N = region length
  (region end − start + 1) zero frames at the region start (at the last frame: appends, as Paste does).
- Operation 3 (Paste's dispatch entry) without a parameter page; Paste's exec pointer 0xFB8E2 -> paste_wrap
  (page pointer 0x10003EE4 == 0 -> sil_exec, else stock 0xF79D4). Undo / progress text read "Paste Section".
- Space: .silv 124/132 bytes in default vectors 159-191 (0x2027C), .silh 92/124 bytes after the LP+Fuzz code
  (0x68374). Left: 8 bytes in the vector run, 32 bytes in the filter region, vector runs of 48/32/16, 20-byte gap.
- Emulator tools/emu_silence.py (stubbed memory check / gap / zero / dispatcher): 200 checks, 0 failures; mutations
  caught (wrapper branch 195, N+1 190, last-frame append 2, memory size 190, op code 3, zero position 95).
  LP+Fuzz release 17,291/0 (emu_lpfuzz_rel), LFO 51,395/0, Transwave 6,011/0, cords 13,004/0, RFX 12,300/0.
- Not emulated: the gap opener / zero fill themselves (Paste's own routines, same register convention).

## Change (2026-10-21): fixed 8 frames
Insert Silence now always inserts NSIL = 8 zero frames at the region start (region end ignored), so only the start
needs setting. emu_silence 217 / 0 (NSIL = 7 mutant: 192 failures). beta2 checksum 08882590.
- Hardware (2026-10-21, beta2 08882a7b): Insert Silence with 8 frames confirmed working by the user (length, undo).
- Changed to NSIL = 4 at the user's request: beta2 checksum 08882a77 (emu_silence 217 / 0, emu_slice 3,806 / 0,
  LFO 51,395 / 0, emu_sloop 6,012 / 0).
- Then NSIL = 2 at the user's request (4-frame build never flashed): beta2 checksum 08882a75; suites as above.
  Two frames = exactly the 4-byte start guard EOS zeroes on every import (0x13D7E4), so padding by 2 keeps the
  first real frames.

## User procedure (confirmed on the E4, 2026-10-21)
1. Sample Edit, then Utils (F1).
2. Silnc (F6).
3. The display shows "Paste Section" (Insert Silence runs as Paste's operation); set Side to Both.
4. OK (F6).
5. The waveform display appears: set the start point with the data wheel, then OK (F6). 2 zero frames are inserted
   there (the chosen point is the region start, 0x10000E14, which sil_exec reads).
Undo reverts it (labelled "Paste Section").
- 2026-10-21: a SCSI drive showing as 7 empty drives after flashing 08882a75 was the drive's configuration, not the
  firmware (user confirmed). The E4 currently runs the 8-frame build 08882a7b (sysex/EOS471-beta2-ins8.syx);
  the 2-frame build 08882a75 is sysex/EOS471-beta2.syx.
- 2 frames not enough on hardware (user); NSIL = 4: beta2 checksum 08882a77 (2-frame kept as sysex/EOS471-beta2-ins2.syx).
