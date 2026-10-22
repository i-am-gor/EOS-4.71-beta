# Filter slots: what limits adding a new filter type (EOS 4.70 / 4.71-beta)

Decoded from the stock image (2026-10-19). 4.71-beta replaced existing classes in place, so the same holds.

## Filter manager (`DAT_1000262c`)
- Allocated once by 0x6842C: `pea $25c` → malloc 0x2AFDC, then the registry ctor 0x67F98.
- Layout (0x25C bytes):
  | offset | contents |
  |---|---|
  | +0x000 | 128 × object pointer, indexed by **type ID** (0..127) |
  | +0x200 | 22 × object pointer, the **menu list** (menu order) |
  | +0x258 | menu count (22) |
- The ctor allocates 4-byte objects (vtable pointer only), appends them to the menu list, then fills all
  128 type slots with the last object (type 0x7F, empty name: the default) and finally stores each
  object at its own type ID.
- **Menu list: 22 / 22 used → no free slot.** Type IDs: 22 / 128 used → 106 free.

| type ID | menu | filter |
|---|---|---|
| 0x01 | 0 | 2 Pole Low-pass |
| 0x00 | 1 | 4 Pole Low-pass |
| 0x02 | 2 | 6 Pole Low-pass |
| 0x08, 0x09 | 3, 4 | 2nd / 4th Order High-pass |
| 0x10, 0x11, 0x12 | 5, 6, 7 | 2nd / 4th Order Band-pass, Contrary Band-pass |
| 0x20, 0x21, 0x22 | 8, 9, 10 | Swept EQ 1 octave, 2->1 oct, 3->1 oct |
| 0x40, 0x41, 0x42, 0x48 | 11–14 | Phaser 1, Phaser 2, Bat-Phaser, Flanger Lite |
| 0x50, 0x51 | 15, 16 | Vocal Ah-Ay-Ee, Vocal Oo-Ah |
| 0x60, 0x61, 0x62, 0x68 | 17–20 | Dual EQ Morph, 2EQ+Lowpass Morph, 2EQMorph+Exprssn, Peak/Shelf Morph |
| 0x7F | 21 | (default, unnamed; also fills every unused type ID) |

Vtables (in ctor order): 0x68878, 0x688A4, 0x688D0, 0x688FC, 0x68928, 0x689D8, 0x68A04, 0x68A30, 0x68954,
0x68980, 0x689AC, 0x68A5C, 0x68A88, 0x68AB4, 0x68AE0, 0x68B0C, 0x68B38, 0x687DC, 0x68B64, 0x68B94,
0x68BC4, 0x6884C. Slots: +0x0C type ID, +0x10 name, +0x14 computeFrames, +0x18 packQ, +0x1C/+0x20/+0x24/+0x28 others.

## Who uses the menu list / count
Only three routines (all other accessors 0x684D0–0x686xx index the type table at +0):
- ctor 0x67F98 (every `$258(a3)` append),
- 0x68458 type ID → menu index (linear search; returns 0 if not found),
- 0x684A0 menu index → type ID (returns 0 if out of range).

Callers of the two lookups: 0x59F88 / 0x59FC8 (voice filter-type getter/setter), 0x6A68C / 0x6A6D0 / 0x6A704
(second filter-type parameter: getter, setter, name formatter), 0xCCC14 (redraw when the type changes, caches
it in 0x1000416C).

## Parameter ranges (hard-coded max 20)
| descriptor | group id | min | max | fmt / get / set | used by |
|---|---|---|---|---|---|
| 0x5AC48 | 0x0A8F | 0 | **20** | 0x59034 / 0x59F88 / 0x59FC8 | editor param 82 (table entry @0x640EA) |
| 0x6B58E | 0x053B | 0 | **20** | 0x6A704 / 0x6A68C / 0x6A6D0 | second filter-type parameter (refs 0x6A4A0, 0xCFACC), probably the front-panel filter page |

Descriptor: +6 min (u32), +0x0A max (u32), +0x16 formatter, +0x1A getter, +0x1E setter.
SysEx and the panel use the **menu index**; presets store the **type ID** byte (getter converts).

## Sound chip
- `FUN_0010D3B0(block, n, flags)`: the table at 0x10D4F4 is only 4 bytes (`37 01 13 25`), indexed by `n & 3`,
  a per-voice value the voice code passes through every computeFrames call unchanged. **It does not depend on the
  filter type and does not limit the number of filters.**
- The only per-filter chip inputs are the coefficient words and the flags: 0x40 (word 9 = output gain),
  0x80 (zeros active, written to the previous block), 0x00 for the vocal filters.
- So a new filter is just coefficients: up to 3 pole pairs (words 0/4/8) and 2 zero pairs (words 1/5) plus the
  gain word, or 3 zero pairs if word 9 is a zero (flags without 0x40).

## Recipe for adding a filter
1. Enlarge the manager: `pea $25c` @0x6843A → e.g. `$300`, and move the count from +0x258 to the new end
   (ctor, 0x6846C, 0x6848C, 0x684AE) so the menu list can grow (0x300 → up to 63 entries before the count).
2. Add the class: a vtable (type, name, computeFrames, packQ; other slots can reuse an existing filter's) and code in free
   space; append one more `alloc + store vtable + append` block in the ctor before the default (0x7F) object.
3. Raise max 20 → 20+n in descriptors 0x5AC48 and 0x6B58E. The default stays last in the list, so its menu index
   moves up but stays out of range.
4. Pick a free type ID in the right family gap (e.g. 0x03–0x07 lowpass, 0x0A–0x0F high-pass).
5. Stock 4.70 loading such a preset: the unknown type ID maps to the default 0x7F object (and 0x68458 returns
   menu index 21, outside the 0..20 range). The default's computeFrames (0x65CDC) writes all-neutral stages and the
   stock gain word: **the voice plays unfiltered**, no crash.

## Space (feasibility)
- No usable gap inside the image: the 1,132 zero bytes at 0x1FF8B0 are part of `.data` (0x1F86F0–0x1FFE80 is
  copied to RAM 0x10000400), and the 2 MB flash lets the image grow only ~384 bytes (notes/TODO.md).
- The registry ctor 0x67F98–0x68428 (1,168 bytes) is 22 unrolled `alloc + store vtable + append` blocks.
  Rewritten as a loop over a vtable list (~60 bytes code + 4 bytes per filter) it frees **~1,000 bytes** in the
  filter region itself, enough for several new classes that reuse existing computeFrames code with new tables
  (vtable 0x2C + name ~20 + table 64–128 + small thunk ≈ 150–250 bytes each).

## Multi-parameter filters and real-time (2026-10-20, not pursued)
- Vtable +0x20 = parameter count: 2 for all filters except the four morph filters (Dual EQ Morph, 2EQ+Lowpass Morph,
  2EQMorph+Exprssn, Peak/Shelf Morph) = 8. +0x24 fills three page headings ("initial offset", "EQ section 1/2" or
  "low/high morph frame"); +0x1C formats indexes 0..7; morph vtables have a 12th slot +0x2C = frame builder.
- Real time: voice mod code (~0x6006C) recomputes Q = (base + cords) >> 5, and only when it changes calls 0x194E80 ->
  dispatcher 0x68680 -> packQ(blk, q, struct). Morph packQ calls +0x2C with the struct, rebuilding frames from all
  8 params. Cord destinations exist only for FilFreq / FilRes, so params 3..8 are applied at note-on and on Q changes,
  not modulated directly. computeFrames dispatcher: 0x68644 (callers 0x601BE, 0x6023E).
