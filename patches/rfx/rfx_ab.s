| A/B diagnostic variant of the RFX skip: stock FUN_00060674 stays in place; its first 8 bytes jump to
| ab_disp, which runs the stock code (displaced prologue + jmp 0x6067C) when switch bit 1 is off and the new
| implementation (rfx.s, relocated) when it is on.
        .include "rfx.s"

        .section .disp,"ax"
        jmp     ab_disp
        nop

        .section .dsp2,"ax"
ab_disp:
        move.b  ABSWITCH,%d0
        btst    #1,%d0
        bne.s   1f
        lea     -0x18(%sp),%sp              | stock prologue (displaced)
        movem.l %d4-%d7/%a4-%a5,(%sp)
        jmp     0x0006067C
1:      jmp     rfx_writer
