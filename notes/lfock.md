# LFO clock from a cord (Lfo1Ck / Lfo2Ck)

Build: `tools/build_beta2.py BASE.bin OUT.bin`. The About name is `LfoCk` plus the build time
(`LfoCk YYYYMMDD HH:MM:SS`), so the startup screen identifies the image.
`tools/build_beta2.py --nocord` is the EOS 4.71-beta2 release, checksum `0886a24c`, without this patch.
Test: `tools/emu_lfock.py BASE.bin`, `tools/emu_listorder.py BASE.bin`.

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

Lfo1Ck is destination 98, listed after Lfo1Trg. Lfo2Ck is destination 107. In the list it is
shown after Lfo2Trg and before Lag0in, so the LFO 2 destinations sit together. Lag0in stays
destination 106. Presets store the id, not the list position.

## How

- The cord summer already writes a continuous running sum (flags `0x200`) into the destination word.
  The four bytes between the two LFO blocks, voice+0x1A4, are unused by the LFO tick. Voice init
  stores the long `1` there, so the LFO 2 half (voice+0x1A6) starts at 1 and the running sum keeps
  that +1. The prologue subtracts it before measuring the magnitude.
- Tick hook `0x61BF4` (`jmp lfo_tick`) jumps to `cord_tick` in the port-map hole. Return address
  `0x61D70` means this call is LFO 2 (`move.w -2(a5)`); otherwise it is LFO 1 (`move.w 0x1C(a5)`,
  because a5 is the LFO block at voice+0x188).
- A negative sum becomes `d0 = 0xA000|div` (bit 15 sync, bit 13 key sync), plus bit 14 for LFO 2, and
  jumps to the sync body at `0x2040E`. Otherwise it jumps to `lfo_tick` at `0x20400`.
- `FUN_00061BC0` saves only d5–d7/a5. The divide uses d2 and d3, and the sync body saves d2–d4 only
  after its own entry, so the prologue saves d2–d3 itself (`lea -8(sp)` / `movem`; 5206e `movem` has
  no predecrement) and restores them before the jump. `divu.l` into d0 encodes a remainder divide on
  the 5206e; the quotient is taken in d3. `move.w` into a data register does not sign-extend.

## List order

The cord screen skips entries whose voice offset is `0x1E` and shows the rest in id order.
Id 106 was already `Lag0in`, so `Lfo2Ck` (107) would have been listed after it. The list
walkers are retargeted (`patches/lfock/list_order.s`):

- `0x62D00` (display index in d1) and `0x62D60` (display index on the stack) return the id.
  Visit position 106 yields id 107, and position 107 yields id 106.
- `0x62C98` (stored id → display index) counts a limit of 106 as 107 and a limit of 107 as 106,
  then joins the stock loop at `0x62CA4`.

`0x62D00` and `0x62D60` agree on every index, and each id round-trips through `0x62C98`.
Test: `tools/emu_listorder.py`.

## Rate field

The LFO page shows the Rate byte on the preset screen's voice (`0x100040AC`). It does not call the
descriptor getter while the controller moves, so a getter alone leaves the name where it was.
`rate_publish`, called from the tick, writes `128 + division` into that byte while the cord is
negative and writes the previous byte back when the cord lets go. The two original bytes are kept at
`0x100003EC` (nothing in the image reads that long). The page paints the byte when it opens. When the
byte changes and the open page is an LFO page (`0x1000415C` is `0x12` or `0x13`), `rate_show` calls
`0xCC1CC`, the same refresh as opening that page again. The saved object is at cache index
`page - 11`: the opener's `moveq #-11` sign-extends, so page `0x12` is slot 7 and page `0x13` is
slot 8. Treating that `moveq` as unsigned 245 looks up slot 263 and the value stays frozen until
the page is opened again. Hardware on `LfoCk 20261025 21:22:39` (checksum `0886630e`) follows the
controller while the page stays open.

The descriptor getter stays the stock zero. The panel reads the Rate byte, and a nonzero getter is
not what paints the field. `rate_set` returns without calling `0x69F80` while the gap word is
negative, so the jog dial and the inc/dec buttons do nothing until the cord sends 0. That is the
behaviour confirmed on the unit. The editor and SysEx Rate descriptors are left stock.

Grey is the field widget's enable byte, `+0x3A`. Tempo uses the same byte: with Clock Source set
to External, Seq Setup calls vtable `+0xE4` (`0x19F078`), which calls `0x1A1594` to store the
enable byte and clear the focus byte `+0x24`. The paint (`0x1A032C`) then uses solid pattern
`0x98D52` or checkerboard `0x98D62`. Pen 2, widget `+0x24` on its own, is the selection highlight,
not the grey. The cached object is the field list (vtable `0xB2D1C`). Its container is the long at
`+0x30` (vtable `0x10D300`), and Rate is that container's first child, the long at `+0x0C`. The
page pointer is the long at `+0x38`. Reading `+0x3A` takes the middle of that pointer. Image
`088653c8` (`LfoCk 20261025 22:54:50`) did that from the LFO tick: the UI froze and the note that
was sounding stayed where it was. The tick now checks the list vtable, writes the enable byte only
when it is wrong, clears `+0x24` when disabling, and then calls the same refresh. Opening the page
while the cord is already held greys on the next tick. A steady cord does not redraw.

Hardware on `LfoCk 20261025 23:18:03` (checksum `08865332`): the Rate value follows the cord, the
field is grey while the sum is negative, and the jog dial and the inc/dec buttons edit Rate again
after the cord sends 0. The port-map hole is 2236 bytes; this image uses 2232. `cord_tick` stays
at `0x15F524`. The list walker `ord_d1` follows the larger patch at `0x15F770`.

Saving the preset while a cord is held stores the division as Rate. Letting the cord go restores the
previous Rate in the voice. The EOS Flasher patch `apps/eos-core/data/eos471beta2.e4p` is still the
previous image (startup name `EOS 4.71-beta2 +LfoCk`). `tools/make_patch.py` rebuilds it from a
chosen `build/eos471_beta2.bin`. The About name includes the build time, so that patch changes
every time it is made.
