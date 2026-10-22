# "Slice" cord destination (from SLpWav) — design and findings (2026-10-21, not built yet)

## Source recovered from build/eos470_sync6_wt4.bin ("EOS 4.70 Sync6+WaveTbl4")
- sl_shift 0x200E8: stock shift = word(p+0x1C) + (SLoop sum word(p+0x0A) >> 5); with the shared sum
  word(p−0x3E) (voice+0x1C) on a forward loop (header +0x3A >> 6 = 1/2): L = (hdr+0x2C − hdr+0x24)/2,
  low = (hdr+0x14 − hdr+0x24)/2, high = (hdr+0x1C − hdr+0x2C)/2 + 1, R = high (sum ≥ 0) or −low.
  Wavetable (mode word voice+0x1E = 0): F = min(R / L, 65535), j = (sum·F ± 2016) / 4032, shift = j·L.
  Scan (mode 1): shift = sum·R / 4032 (split to avoid overflow). Clamp to [low, high] and ±32767.
- sl_mode 0x200AC (from the LFO init hook, LFO 1 only): scans the 24 preset cords at LFO1 params + 0x26
  ({src, dst, amt, -}); writes 1 to voice+0x1E (LFO struct − 0x16A) if any enabled cord targets 58.
- Destination table 0x6344C (8 bytes: name, accumulator offset, flags): 55 -> "SLpWav", 58 -> "SLpScn", both 0x1C.
  Flags: 0x0100 = note-on-only destinations (names shown with a leading ', e.g. 'SStart), 0x0200 = realtime.

## 4.71 note-on (for Slice)
- Order: 0x5F4A8 allocates the voice, installs the start method 0x614A4 at voice+0x0E, then calls the setup
  0x5F67C (clears the accumulators from voice+0x1C via 0x625CC, then LFO inits). The start method runs later:
  0x614A4 -> 0x60D80 -> 0x5FAE0(pitch = voice+0x5A, channel struct). So a mode flag set in the LFO1 init hook
  is in place when 0x5FAE0 runs.
- 0x5FAE0: SStart offset (scaled by 0x13D5E0), then 0x194600(hdr, note struct = channel+0x4A, side, offset,
  0) fills note +12 = play start, +16 = loop start (8 when not looped), +20 = loop end − 1 (looped) or end
  (one-shot), +25 = reverse flag; word addresses = (hdr[0x3C + 4·side] + *0x100071BC + hdr field) >> 1.
  The loop-shift hook (0x5FBA6) is skipped for one-shot samples (loop-off flag p+0x36 forces shift 0).
  Stereo: right note struct = channel + 0x3FE + 0x4A (second 0x194600 call, side 1). Common exit 0x5FD2C
  (movem.l (sp),d6-d7/a2/a4-a5 ; lea 20(sp),sp ; rts) with a4 = left note, a5 = pitch, a2 = channel.

## Slice (proposed)
- Destination 55 "'Slice", flags 0x0100 (note-on), accumulator voice+0x1C (shared with SLpScn; the only free
  word). Mode flag voice+0x1E = 1 set by a cord scan in lfo_init when a cord targets 55; sl_shift skips the
  SLpScn scan for flagged voices.
- Slice length L = the sample's loop length (set the loop on slice 1). j = round(sum · F / 4032) with F = whole
  slices after (sum > 0) or before (sum < 0) slice 1. At the note-on exit, for each channel (forward types):
  start = loop start + j·L (+ SStart offset limited to L−1); one-shot end = loop end + j·L − 1; looped: loop
  start/end += j·L. Reverse loop types: unchanged.
- Size ~200 bytes (scan ~30, flag check ~8, slice ~150, name 8).

## Space problem
- beta2 free code: ~170 bytes in pieces (≤ 48 contiguous). Not enough.
- Correction: the exception vector table is at 0x20200 (initial SSP 0x10800000, PC 0x20602), not 0x20000.
  The "default vector" runs counted from 0x20000 are real vectors: 0x2027C..0x202FF = vectors 31–63 (NMI
  autovector, TRAP #0–15, FPU/reserved), 0x20214 = vectors 5–7 (divide by zero, CHK, TRAPV), 0x20240 = 16–23,
  0x20370 = 92–95 and 0x203D0 = 116–127 (user interrupts, the class earlier builds used). All point at the
  fatal "Gen Trap error" handler in stock and nothing reprograms them, so code there only changes a fatal
  error into a crash — but the Insert Silence build put .silv in vectors 31–61; move it before release.
- Next: free a real block (debug/trace strings of AudioAnalyzer.C and other modules, ~2.4 KB) with every
  reference proven, then place Slice and Insert Silence there.

## Built (2026-10-21): EOS 4.71-beta2 with Slice + Insert Silence, checksum 08882909, sysex/EOS471-beta2.syx
tools/build_beta2.py (LP+Fuzz release + patches/silence/silence.s + patches/slice/slice.s), symbols in
build/eos471_beta2.bin.syms.json.
- Freed (proven: only reference = one pea each for the bare-rts stubs 0xE939C / 0x3A454; pea -> subq.l #4,sp ; nop ;
  nop): A 0xEB306–0xEB414 (11 AudioAnalyzer trace strings + orphan rts/nop, 270 B), B 0x98F86–0x98FD8 (4 graphics
  error strings, 82 B), C 0x9B788–0x9B7A4 ("LCD not ready - timed out", 28 B). Also used: reserved vectors 16–23
  (0x20240) and 48–63 (0x202C0), user vectors 116–127 (0x203D0), the filter-region tail. Vectors 31–47 (NMI, TRAP)
  are default again (Insert Silence moved out).
- Layout: A = slice_exit + one (266/270); B = sl_mode + paste_wrap (82/82); C = Insert Silence strings (21/28);
  F = sil_key + shift_w + "'Slice" (108/124); V48 / U / V16 = sil_exec in three parts (56/64, 44/48, 18/32).
- Hooks: 0x61B9C jmp sl_mode (-> lfo_init), 0x5FBA6 / 0x5FECA jsr shift_w (-> sl_shift unless Slice), 0x5FD2C jmp
  slice_exit (epilogue of 0x5FAE0); destination 55 = "'Slice", 0x1C, 0x0100.
- Emulator: emu_slice.py 3,605 / 0 (model of 3,000 random note-ons incl. stereo, one-shot / looped, reverse, L = 0,
  F > 65535; sl_mode over 400 cord tables; shift_w); mutations caught: end −1 (1,464), side offset (1,192), dest
  code (221), shift_w branch (200), rounding (116), offset clamp (538), LFO 2 check (279), F cap (127).
  emu_silence.py 217 / 0 (image diff limited to the listed places, pea sites, vectors 31–47 default).
  LP+Fuzz release 17,291 / 0; LFO 51,395 / 0; emu_sloop 6,012 / 0 (beta2-aware: shift_w hooks, dst 55 flag);
  emu_cords 13,004 / 0 with destination 55 reset (with it: dst-55 cords now feed 0x1C, by design); RFX 12,300 / 0.
- Hardware assumptions still to confirm on the E4: destination flag 0x0100 sums are ready at 0x5FAE0 (as SStart);
  one-shot end = note +20 (inclusive); EOS keeps loop points of unlooped samples.
- Use: set the sample's loop on slice 1 (loop on or off), cord e.g. Key+ / MidiA / Vel+ -> 'Slice; full scale (+100,
  source at max) reaches the last whole slice.

## Hardware feedback (2026-10-21, beta2 08882909 on the E4)
- Beat Munger (Beat Machine) works with the AudioAnalyzer trace strings removed (user confirmed).
- Slice with the loop OFF plays the selected slice (start and end) — note-on path works.
- Key tracking is not musical: full scale (Key+ +100 = key 127) spreads over all slices, so a 16-slice loop changes
  slice only every ~8 keys. Wanted: one slice per key. Loop-on behaviour still to be re-checked after that change.

## One slice per key (2026-10-21, beta2 checksum 08882a7b)
- j = round(sum · 127 / 4032) − the zone's original key, clamped to the whole slices before (Fb) and after (Fa)
  slice 1. With Key+ → 'Slice +100 the original key plays slice 1, each key up the next one; MidiA etc. map the
  controller value the same way (value − original key).
- Original key: zone byte +12 (zone = *(note request + 96); the pitch init 0x5F8EC adds (key − zone[12]) · 64).
  pit_hook (jsr at 0x5F914, replacing move.w 10(a1),d1 ; move.w 56(a0),d0) stores it at voice+0x1F; the Slice flag
  is now the byte voice+0x1E (sl_mode writes a byte; slice_exit / shift_w test the byte).
- Emulator emu_slice 3,806 / 0 (adds 200 pit_hook cases, random original keys); mutations: key offset 739,
  scale 178, upper clamp 783, zone byte 200, flag word write 223, flag word test 245. emu_silence 217 / 0,
  LFO 51,395 / 0, emu_sloop 6,012 / 0, RFX 12,300 / 0, cords 13,004 / 0 (destination 55 reset).
- Hardware (2026-10-21, beta2 08882a7b): one slice per key from the zone's original key confirmed working by the user.
- Hardware: keys below the original key / above the last slice clamp to the first / last slice, confirmed by the user.
