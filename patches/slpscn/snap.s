| SLpScn whole-frame stepping (EOS 4.71-beta2): replaces the 22-byte continuous scan block of sl_shift at
| 0x200EC..0x20101 (remu/divu/muls/muls/divs/add: shift = sum * R / 4032). In: d0 = SLpScn sum, d1 = R (room in the
| sum's direction), d2 = L (loop = frame length), d5 = 4032. Out: d1 = shift = round(sum * floor(R / L) / 4032) * L,
| i.e. the loop moves in whole frames (cycle-aligned jumps, as the old SLoop + Gain4X chain). Rounding is exact for
| sum >= 0; negative sums round half a frame toward zero.
        .section .snap,"ax"
snap:   divu.l  %d2,%d1
        muls.l  %d0,%d1
        addi.l  #2016,%d1
        divs.l  %d5,%d1
        muls.l  %d2,%d1
