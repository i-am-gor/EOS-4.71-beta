| Loop-shift glide (EOS 4.71-beta2): the 10 ms tick (0x5FE4C) moves the loop by at most LIM samples per tick, so
| fast wheel / envelope moves and the note-on jump become a short glide instead of one big mid-cycle jump (noise
| burst). Slow moves (|change| <= LIM per tick) are unchanged. Applies to SLoop and SLpScn alike (both use this path).
| In place of 0x5FED0..0x5FEED (5 NOPs after the jsr + the stock "delta = new - stored; stored = new" code); the tick
| call at 0x5FECA goes to shift_t (patches/slice/slice.s), which returns d7 = target shift, a0 = stored shift,
| d1 = target - stored (flags set). Out: d1 = clamped delta (used by the stock loop-point update at 0x5FEEE),
| stored shift (pitch struct +0x2C) = stored + clamped delta.
        .equ    LIM,       64
        .globl  SKIP                        | 0x5FF24 (stock: no change), defined in the linker script
        .section .slew,"ax"
slew:   beq.w   SKIP
        moveq   #LIM,%d7
        cmp.l   %d7,%d1
        ble.s   1f
        move.l  %d7,%d1
1:      neg.l   %d7
        cmp.l   %d7,%d1
        bge.s   2f
        move.l  %d7,%d1
2:      adda.l  %d1,%a0
        move.w  %a0,0x2C(%a5)
        .balign 2
