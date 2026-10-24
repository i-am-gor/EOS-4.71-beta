| Lfo1Ck / Lfo2Ck cord destinations (notes/lfock.md).
| The beta2 LFO tick hook (0x61BF4, jmp lfo_tick) is retargeted here. The cord summer writes its
| running sum into the gap between the two LFOs (voice+0x1A4 for LFO 1, voice+0x1A6 for LFO 2).
| A positive or zero sum leaves Rate alone. A negative sum is the depth: magnitude 4032 (a controller
| at CC 127 through panel amount -100) is 1/32, and smaller depths are the slower lengths, in 16
| even steps. 4032 = (127<<5)*(127<<5)>>12.
| The sync body at 0x2040E expects d0 = 0x8000|0x2000|div (key sync). LFO 2's gap keeps the stock
| init 1, so that word is one count higher.
| FUN_00061BC0 saves only d5-d7/a5, and the sync body saves d2-d4 only after its own entry, so this
| prologue saves d2-d3 around the divide and restores them before the jump. 5206e movem has no
| predecrement. divu.l into d0 encodes a remainder divide on 5206e; the quotient form uses d3.
| move.w into a data register does not sign-extend.
| Hooks (build_beta2.py): 0x61BF4 jmp cord_tick. Dest 98 / 107, flags 0x200.

        .equ    LFO_TICK,      0x00020400
        .equ    SYNC_BODY,     0x0002040E
        .equ    LFO2_TICK_RET, 0x00061D70
        .equ    FULL,          4032

        .section .lfk,"ax"
        .balign 4
        .globl  cord_tick
cord_tick:
        move.l  0x10(%sp),%d1
        cmpi.l  #LFO2_TICK_RET,%d1
        beq.s   2f
        move.w  0x1C(%a5),%d0           | LFO 1 gap (voice+0x1A4)
        bra.s   3f
2:      move.w  -2(%a5),%d0             | LFO 2 gap (voice+0x1A6)
3:      tst.w   %d0
        bmi.s   4f
        jmp     LFO_TICK                | zero or positive: Rate path
4:      ext.l   %d0
        lea     -8(%sp),%sp
        movem.l %d2-%d3,(%sp)
        cmpi.l  #LFO2_TICK_RET,%d1
        bne.s   5f
        subq.l  #1,%d0                  | undo the stock long-1 in the low half
5:      neg.l   %d0                     | magnitude
        subq.l  #1,%d0
        lsl.l   #4,%d0                  | (mag-1)*16
        move.l  %d0,%d3
        move.l  #FULL,%d2
        divu.l  %d2,%d3                 | quotient in d3
        move.l  %d3,%d0
        cmpi.l  #15,%d0
        bls.s   6f
        moveq   #15,%d0
6:      ori.l   #0xA000,%d0             | bit 15 active, bit 13 key sync
        cmpi.l  #LFO2_TICK_RET,%d1
        bne.s   7f
        ori.l   #0x4000,%d0             | LFO 2 note-tick base
7:      movem.l (%sp),%d2-%d3
        lea     8(%sp),%sp
        jmp     SYNC_BODY
