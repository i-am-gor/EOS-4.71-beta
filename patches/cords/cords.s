| Cord processor optimization for EOS 4.70 (layer on Sync8+TW+HPBP6).
| Stock FUN_0005F89C runs its loop over all 24 cord slots of a voice every 10 ms tick. The slots (amp block
| + 0x208, 16 bytes: +0 source ptr, +4 destination ptr, +8 amount, +10 last contribution, +12 enabled) are
| only set at note-on by FUN_0005F810. At its end, count_build stores the number of slots up to and including
| the last enabled one (0..24) in the unused byte 13 of slot 0; the stock loop then runs that many slots
| instead of 24 (cnt_hook replaces its moveq #24,d7 ; lea $208(a1),a1). Same code, same order, same results:
| only the empty slots after the last cord (which stock tests and skips) are not visited.
| Safety: a count above 24 (never written) runs all 24 slots = stock; 0 returns at once.

        .equ    SLOTS,   0x208
        .equ    LOOP_END, 0x0005F8E4        | stock exit of FUN_0005F89C (restores d6/d7, rts)

        .section .vlo,"ax"
        .globl  _start
_start:
| ---- 0x5F8A4 in FUN_0005F89C: jsr cnt_hook (replaces moveq #$18,d7 ; lea $208(a1),a1); a1 = amp block ----
cnt_hook:
        lea     SLOTS(%a1),%a1
.ifdef ABSWITCH
        moveq   #24,%d7                     | A/B build: switch bit 0 off -> stock (24 slots)
        move.b  ABSWITCH,%d0
        btst    #0,%d0
        beq.s   2f
.endif
        moveq   #0,%d7
        move.b  13(%a1),%d7                 | slots to visit
        beq.s   1f
        moveq   #24,%d0
        cmp.l   %d0,%d7
        bls.s   2f
        move.l  %d0,%d7                     | not a count we wrote: all 24 (stock)
2:      rts
1:      addq.l  #4,%sp                      | no cords: leave FUN_0005F89C
        jmp     LOOP_END

| ---- end of FUN_0005F810 (0x5F892: jmp count_build; replaces movem.l (a7),d7/a3-a5 ; lea $10(a7),a7) ----
count_build:
        movem.l (%sp),%d7/%a3-%a5
        lea     16(%sp),%sp                 | stock epilogue; 4(sp) = amp block
.ifdef ABSWITCH
        move.b  ABSWITCH,%d0                | A/B build: off -> nothing written (pure stock)
        btst    #0,%d0
        bne.s   3f
        rts
3:
.endif
        movea.l 4(%sp),%a1
        lea     SLOTS+12+16*23(%a1),%a0     | enabled byte of slot 23
        moveq   #24,%d0
1:      tst.b   (%a0)
        bne.s   2f
        lea     -16(%a0),%a0
        subq.l  #1,%d0
        bne.s   1b
2:      move.b  %d0,SLOTS+13(%a1)
        rts
