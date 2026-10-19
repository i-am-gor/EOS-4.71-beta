# EOS 4.70 editor SysEx (decoded from the OS, confirmed live on the E4)

Connection here: MOTU 828mk3 Hybrid MIDI Port; E4 MIDI Device ID 1; audio on MOTU inputs 17/18.

## Header
`F0 18 21 <dev> 55 <cmd> … F7` — E-mu (0x18), EOS product 0x21, editor designator 0x55.
Handler: key 0x55 registered at 0x53372 → dispatcher 0x5870C (commands 0x00–0x74).
A second family `F0 18 7F <dev> <prod> <cmd>` (handler 0x348E8) carries remote note on/off
(cmd 1/0) and dumps (0x10/0x14, LCD screen dump 0x50).

## Parameters (table 0x63E58, 271 entries, 8 bytes: u16 group id, ptr descriptor)
- Request (read-only): `F0 18 21 dd 55 02 <n> (<id lo> <id hi>)×n F7`
- Value / edit:        `F0 18 21 dd 55 01 02 <id lo> <id hi> <val lo> <val hi> 7F F7`
- Values are 14-bit; ≥ 0x2000 is negative. Descriptor: +6 min, +10 max, +0x1A getter, +0x1E setter.
- Voice parameters act on the preset/voice currently selected on the front panel.

| id | parameter | notes |
|---|---|---|
| 82 | filter type | menu index 0..20 (0 = 2 Pole LP, 1 = 4 Pole LP, 2 = 6 Pole LP, …) |
| 83 | filter frequency | 0..255 |
| 84 | filter Q | 0..127 (per filter) |
| 70–81 | amp envelope (rate/level ×6) | |
| 93–104 | filter envelope | |
| 105–109 | LFO 1 rate, shape, delay, variation, sync | |
| 110–114 | LFO 2 | |
| 129+3c / 130+3c / 131+3c | cord c+1: source, destination, amount (±100) | c = 0..17 |
| 183–270 | globals with names in descriptors (MIDI, SCSI, FX, clocks…) | |

Cord codes follow the Proteus-family numbering (checked against the default cords
Vel< 12 → AmpVol 64, PitWl 16 → Pitch 48): Lfo1~ 96, Lfo1+ 97, FilFreq 56, FilRes 57.

Tool: `tools/eos_remote.py get <ids>`.
