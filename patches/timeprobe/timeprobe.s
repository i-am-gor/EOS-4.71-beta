| Per-stage timing probe for the EOS 4.70 voice control tick (diagnostic build on stock 4.70).
| Every stage call inside FUN_00060E80 (and the call of FUN_00060E80 itself) goes through a stub in EXT
| (within bsr.w range) -> common wrapper in the vector cave. The wrapper is stack-based (re-entrant: a voice
| tick can nest inside another one): it pushes the timer 1 count (TCN1), re-pushes the two call arguments,
| calls the stage, then adds the elapsed timer counts and one call to the stage's accumulators.
| Timer 1 counts 0..TRR1 per 2 kHz period; elapsed = (end - start) mod (TRR1 + 1).
| Readout: SysEx parameter 195: set(v) latches var v (0..23: ACC[k], CNT[k] for stage k = v/2, 24 = TRR1),
| each get returns the next 11 bits (lo, mid, hi). Rates are differences over host-timed windows.

        .equ    TCN1,    0x2000010C
        .equ    TRR1,    0x20000104
        .equ    VARS,    0x10000300          | RAM copy of vector cave (never read by EOS)
        .equ    LATCH,   0x10000370
        .equ    PIECE,   0x10000374

        .macro  STUB k, fn
stub\k: lea     \fn,%a1
        moveq   #8*\k,%d1
        jmp     common
        .endm

        .section .ext,"ax"
        .globl  _start
_start:
        STUB 0,  0x00060E80                  | whole voice tick
        STUB 1,  0x0005F89C                  | cords
        STUB 2,  0x00062208                  | envelopes (3 calls)
        STUB 3,  0x0005FD38                  | pitch envelope / glide
        STUB 4,  0x00061BC0                  | LFO 1
        STUB 5,  0x00061D5C                  | LFO 2 (+ lag)
        STUB 6,  0x00062544                  | aux
        STUB 7,  0x00062798                  | key/velocity window
        STUB 8,  0x0005FFD8                  | filter tick
        STUB 9,  0x00060B7C                  | amp tick
        STUB 10, 0x0005FE4C                  | pitch/loop -> chip
        STUB 11, 0x000625F8                  | Ck clock sources

        .section .cave,"ax"
| a1 = stage function, d1 = 8*k; stack: return, arg1, arg2. Keeps d0 (stage result).
common:
        move.l  %d1,-(%sp)
        moveq   #0,%d1
        move.w  TCN1,%d1
        move.l  %d1,-(%sp)                   | t0, 8k, return, arg1, arg2
        move.l  16(%sp),-(%sp)               | arg2
        move.l  16(%sp),-(%sp)               | arg1
        jsr     (%a1)
        addq.l  #8,%sp
        moveq   #0,%d1
        move.w  TCN1,%d1
        sub.l   (%sp)+,%d1
        bpl.s   1f
        move.l  %d0,-(%sp)                   | wrapped once: + period
        moveq   #0,%d0
        move.w  TRR1,%d0
        add.l   %d0,%d1
        addq.l  #1,%d1
        move.l  (%sp)+,%d0
1:      movea.l (%sp)+,%a0
        adda.l  #VARS,%a0
        add.l   %d1,(%a0)
        addq.l  #1,4(%a0)
        rts

| ---- parameter 195 getter (desc): next 11 bits of the latch ----
probe_get:
        move.l  PIECE,%d1
        addq.l  #1,PIECE
        move.l  LATCH,%d0
        mulu.w  #11,%d1
        lsr.l   %d1,%d0
        andi.l  #0x7FF,%d0
        rts

| ---- parameter 195 setter (desc, v): latch var v ----
probe_set:
        move.l  8(%sp),%d0
        clr.l   PIECE
.ifdef ABSWITCH
        moveq   #32,%d1                      | A/B build: set(32..35) -> switch byte = value - 32
        cmp.l   %d1,%d0
        blt.s   0f
        sub.l   %d1,%d0
        move.b  %d0,ABSWITCH
        rts
0:
.endif
        moveq   #24,%d1
        cmp.l   %d1,%d0
        bne.s   1f
        moveq   #0,%d0
        move.w  TRR1,%d0
        move.l  %d0,LATCH
        rts
1:      bhi.s   9f
        lsl.l   #2,%d0
        lea     VARS,%a0
        move.l  (%a0,%d0.l),%d0
        move.l  %d0,LATCH
9:      rts
