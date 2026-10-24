# PC-AT (ASCII) keyboard support in EOS 4.70 (traced 2026-10-23)

**Hardware:** a keyboard controller at chip-select `0x03700000`.
- Init `0x1421A8` (state at `0x10005058`, 1 KB receive buffer at `0x1030A460`) resets it.
- Probe `0x14220C` sends `0xFF` (PS/2 keyboard reset) and retries up to 10 times.
- At boot, `0x2A172` calls `0x142FF0`. If it returns 0, the boot screen prints **"PC-AT Keyboard Enabled"**.

**Driver:** `0x143000`–`0x143560`, PS/2 scan code set 2.
- **Key-down table:** 0x84 bytes at `0x102D16C8`, one per scan code.
- **Modifier byte:** `0x10005084`.
  - bit 0 Shift
  - bit 1 Ctrl
  - bit 2 Alt
  - bit 4 Caps Lock
  - bit 5 Num Lock
- **Prefix states:** a state table at `0x1443CC` handles the `0xE0`/`0xE1` prefixes and key-up (`0xF0`).
- **Per-key table:** `0x14355C`, 0x1C bytes per scan code.
  - Each entry is a handler, then 4 records of 6 bytes (u32 type, u8 value): plain, Shift, Ctrl, Alt.
  - The layer is picked by `0x143130`: Ctrl wins over Alt, and Shift/Caps applies to letters.
- **Handlers:**
  - `0x14305C`: none (unused key)
  - `0x14311C`: single record
  - `0x143214`: 4 layers
  - `0x1431B8`: navigation / numeric keypad (Num Lock picks the digit)
  - `0x143060`: modifier
- **Event types:**
  - 3 = ASCII character
  - 5 = soft key 0–5
  - 0 = cursor up/left/right/down
  - 1 = value dec/inc
  - 6 = page up/down
  - 10 = front-panel button code (not yet identified)

**Not wired up:** `0x2ACDC` ("keyboard present?") is a stub that always returns 0. Its callers include the sequencer
page (`0xBB62C`), which would show a **SetKybd** soft key instead of **SetBCh** if it returned 1. The other callers are
`0x2733A`, `0x2E654` and `0xAA7A2`.

**Keypad + / − with Num Lock on (decided 2026-10-23):** kept as stock. With Num Lock on, keypad − types '-' and
keypad + does nothing; with Num Lock off they step the value down / up. A build that made − (and then +) step with
Num Lock on was published briefly as a build 2 pre-release (`088695df`) and withdrawn. Build 2 (`0886960e`)
keeps the stock keypad.
The keypad table records are 0x7B / 0x79 record 1 (`KEY_TAB + code * 0x1C + 10`, key table at `0x14355C`).

## Key map (scan code, key, handler, plain | Shift | Ctrl | Alt)

Unlisted codes do nothing. F7, F8 and F9 are unused.

```
0x03 F5           simple    type5:0x04
0x04 F3           4-layer   type5:0x02 | - | type10:0x10 | -
0x05 F1           4-layer   type5:0x00 | - | type10:0x0e | -
0x06 F2           4-layer   type5:0x01 | - | type10:0x0f | -
0x07 F12          simple    type10:0x10
0x09 F10          simple    type10:0x0e
0x0b F6           simple    type5:0x05
0x0c F4           simple    type5:0x03
0x0d Tab          4-layer   char 0x19 | char 0x19 | - | type10:0x07
0x0e `            4-layer   '`' | '~' | - | -
0x11 Alt          modifier  -
0x12 LShift       modifier  -
0x14 Ctrl         modifier  -
0x15 Q            4-layer   'q' | 'Q' | - | -
0x16 1            4-layer   '1' | '!' | - | -
0x1a Z            4-layer   'z' | 'Z' | - | type10:0x12
0x1b S            4-layer   's' | 'S' | type10:0x0c | type10:0x02
0x1c A            4-layer   'a' | 'A' | type10:0x16 | type10:0x06
0x1d W            4-layer   'w' | 'W' | - | -
0x1e 2            4-layer   '2' | '@' | - | -
0x21 C            4-layer   'c' | 'C' | - | -
0x22 X            4-layer   'x' | 'X' | char 0x19 | -
0x23 D            4-layer   'd' | 'D' | type10:0x07 | type10:0x03
0x24 E            4-layer   'e' | 'E' | type10:0x06 | -
0x25 4            4-layer   '4' | '$' | - | -
0x26 3            4-layer   '3' | '#' | - | -
0x29 Space        simple    ' '
0x2a V            4-layer   'v' | 'V' | type10:0x14 | -
0x2b F            4-layer   'f' | 'F' | type10:0x17 | type10:0x06
0x2c T            4-layer   't' | 'T' | - | -
0x2d R            4-layer   'r' | 'R' | type10:0x18 | -
0x2e 5            4-layer   '5' | '%' | - | -
0x31 N            4-layer   'n' | 'N' | - | -
0x32 B            4-layer   'b' | 'B' | - | -
0x33 H            4-layer   'h' | 'H' | - | -
0x34 G            4-layer   'g' | 'G' | type10:0x03 | -
0x35 Y            4-layer   'y' | 'Y' | - | -
0x36 6            4-layer   '6' | '^' | - | -
0x3a M            4-layer   'm' | 'M' | - | type10:0x01
0x3b J            4-layer   'j' | 'J' | - | -
0x3c U            4-layer   'u' | 'U' | type0:0x00 | -
0x3d 7            4-layer   '7' | '&' | - | -
0x3e 8            4-layer   '8' | '*' | - | -
0x41 ,            4-layer   ',' | '<' | - | -
0x42 K            4-layer   'k' | 'K' | - | -
0x43 I            4-layer   'i' | 'I' | - | -
0x44 O            4-layer   'o' | 'O' | - | -
0x45 0            4-layer   '0' | ')' | - | -
0x46 9            4-layer   '9' | '(' | - | -
0x49 .            4-layer   '.' | '>' | - | -
0x4a /            4-layer   '/' | '?' | - | -
0x4b L            4-layer   'l' | 'L' | type10:0x0b | -
0x4c ;            4-layer   ';' | ':' | - | -
0x4d P            4-layer   'p' | 'P' | - | type10:0x04
0x4e -            4-layer   '-' | '_' | - | -
0x52 '            4-layer   "'" | '"' | - | -
0x54 [            4-layer   '[' | '{' | - | type10:0x0c
0x55 =            4-layer   '=' | '+' | - | -
0x58 CapsLock     modifier  -
0x59 RShift       modifier  -
0x5a Enter        simple    char 0x0d
0x5b ]            4-layer   ']' | '}' | - | type10:0x0b
0x5d \            4-layer   '\\' | '|' | - | -
0x66 Backspace    simple    char 0x08
0x69 End/KP1      nav       char 0x18 | '1' | - | -
0x6b Left/KP4     nav       type0:0x01 | '4' | - | -
0x6c Home/KP7     nav       char 0x17 | '7' | - | -
0x70 Ins/KP0      nav       char 0x16 | '0' | - | -
0x71 Del/KP.      nav       char 0x7f | '.' | - | -
0x72 Down/KP2     nav       type0:0x03 | '2' | - | -
0x73 KP5          nav       char 0x00 | '5' | - | -
0x74 Right/KP6    nav       type0:0x02 | '6' | - | -
0x75 Up/KP8       nav       type0:0x00 | '8' | - | -
0x76 Esc          simple    char 0x1b
0x77 NumLock      modifier  -
0x78 F11          simple    type10:0x0f
0x79 KP+          nav       type1:0x01 | - | - | -
0x7a PgDn/KP3     nav       type6:0x01 | '3' | - | -
0x7b KP-          nav       type1:0x00 | '-' | - | -
0x7c KP*          nav       '*' | '*' | - | -
0x7d PgUp/KP9     nav       type6:0x00 | '9' | - | -
```
