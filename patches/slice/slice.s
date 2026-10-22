| Cord destination "'Slice" (EOS 4.71-beta2): at note-on, the cord sum selects slice j of the sample and the
| voice plays only that slice. Adapted from SLpWav (EOS 4.70 Sync6+WaveTbl4, notes/slice_design.md).
|
| Slice length L = the sample's loop length: set the loop on slice 1 (loop start = slice 1 start, loop end =
| slice 1 end). j = round(sum * 127 / 4032) - the zone's original key: with Key+ -> 'Slice +100 the original key
| plays slice 1 and each key up the next slice (4032 = key/CC 127 through +100); clamped to the slices that exist.
| Slice j = [loop start + j*L, loop end + j*L). The original key is saved at voice+0x1F by pit_hook.
| At the end of the note-on sample setup (0x5FAE0 exit), for each channel (forward playback only):
|   play start += (loop start + j*L) - sample start (keeps the SStart offset and stereo ITD), limited to the slice;
|   one-shot: end = loop end + j*L - 1; looped: loop start / end += j*L (the loop stays on the slice).
| Destination 55, accumulator voice+0x1C (shared with SLpScn 58: the only free word), flags 0x0100 (note-on).
| Mode: byte voice+0x1E = 1 when any enabled cord of the voice targets 55 (scan in the LFO 1 init, as sl_mode in
| WaveTbl4); SLpScn's loop scan is skipped for such voices.
| Sections (placed by tools/build_beta2.py): .slA slice_exit + one, .slB sl_mode, .slF shift_w + name, .slP pit_hook.

        .equ    LFO_INIT,  0x204D8          | lfosync lfo_init (jmp from 0x61B9C)
        .equ    SL_SHIFT,  0x20080          | lfosync sl_shift (jsr from 0x5FBA6 / 0x5FECA)
        .equ    LFO2_RET,  0x61CF0          | return address of the LFO 2 init call
        .equ    SMPBASE,   0x100071BC       | sample memory base (added to header offsets)
        .equ    DEST,      55
        .equ    FULL,      4032

        .section .slB,"ax"
| ---- sl_mode: jmp from 0x61B9C (LFO init). a3 = preset LFO params, a5 = LFO struct (LFO 1: voice+0x188).
| LFO 1 only: voice+0x1E = 1 if a cord {src, dst, amt} at a3+0x26 (24 x 4 bytes) has dst 55, src and amt != 0.
sl_mode:
        move.l  0x18(%sp),%d0
        cmpi.l  #LFO2_RET,%d0
        beq.s   9f
        lea     0x26(%a3),%a0
        moveq   #24,%d1
1:      moveq   #0,%d0
        move.b  1(%a0),%d0
        cmpi.l  #DEST,%d0
        bne.s   2f
        tst.b   (%a0)
        beq.s   2f
        tst.b   2(%a0)
        beq.s   2f
        moveq   #1,%d0
        move.b  %d0,-0x16A(%a5)             | voice+0x1E (flag byte; +0x1F = original key)
        bra.s   9f
2:      addq.l  #4,%a0
        subq.l  #1,%d1
        bne.s   1b
9:      jmp     LFO_INIT

        .section .slF,"ax"
| ---- shift_w: jsr from 0x5FBA6 / 0x5FECA. a5 = pitch struct (voice+0x5A). Slice voices: the stock loop
| shift (SLoop) only; others: sl_shift (stock + SLpScn).
shift_w:
        tst.b   -0x3C(%a5)                  | voice+0x1E
        bne.s   1f
        jmp     SL_SHIFT
1:      move.w  0x1C(%a5),%d7
        ext.l   %d7
        move.w  0x0A(%a5),%d1
        ext.l   %d1
        asr.l   #5,%d1
        add.l   %d1,%d7
        rts

        .section .slP,"ax"
| ---- pit_hook: jsr from 0x5F914 in the pitch-struct init 0x5F8EC (replaces move.w 10(a1),d1 ; move.w 56(a0),d0).
| a1 = zone (+12 = original key), a0 = sample header, a5 = pitch struct (voice+0x5A): voice+0x1F = original key.
pit_hook:
        move.b  12(%a1),%d1
        move.b  %d1,-0x3B(%a5)
        move.w  10(%a1),%d1
        move.w  56(%a0),%d0
        rts

        .section .slA,"ax"
        .globl  slice_exit
| ---- slice_exit: jmp from 0x5FD2C (the epilogue of 0x5FAE0: movem.l (sp),d6-d7/a2/a4-a5 ; lea 20(sp),sp ; rts).
| a4 = left note struct (channel+0x4A), a5 = pitch struct, a2 = channel struct; d6/d7 are restored below.
slice_exit:
        tst.b   -0x3C(%a5)
        bne.s   10f
        jmp     scan_start                  | not a Slice voice: SLpScn start-at-loop (epilogue there)
10:
        lea     -16(%sp),%sp
        movem.l %d2-%d5,(%sp)
        movea.l %a4,%a1
        moveq   #0,%d6                      | side 0
        bsr.w   one
        moveq   #0,%d0
        move.b  0x18(%a4),%d0
        andi.l  #6,%d0                      | stereo
        beq.s   8f
        lea     0x448(%a2),%a1              | right note struct (channel + 0x3FE + 0x4A)
        moveq   #4,%d6                      | side 1: header fields + 4
        bsr.w   one
8:      movem.l (%sp),%d2-%d5
        lea     16(%sp),%sp
9:      movem.l (%sp),%d6-%d7/%a2/%a4-%a5
        lea     20(%sp),%sp
        rts

| one: a1 = note struct, d6 = 4 * side, a5 = pitch struct. Clobbers d0-d5, d7, a0.
one:    tst.b   0x19(%a1)                   | reverse playback: unchanged
        bne.w   9f
        movea.l 0x30(%a5),%a0               | sample header
        adda.l  %d6,%a0
        move.l  0x3C(%a0),%d7
        add.l   SMPBASE,%d7                 | byte base of this side
        move.l  0x24(%a0),%d2
        add.l   %d7,%d2
        asr.l   #1,%d2                      | LS (word address)
        move.l  0x2C(%a0),%d3
        add.l   %d7,%d3
        asr.l   #1,%d3                      | LE
        move.l  %d3,%d5
        sub.l   %d2,%d5                     | L
        ble.w   9f
        move.l  0x14(%a0),%d4
        add.l   %d7,%d4
        asr.l   #1,%d4                      | S (sample start)
        move.l  0x1C(%a0),%d1
        add.l   %d7,%d1
        asr.l   #1,%d1                      | E (sample end, inclusive)
        | j = round(sum * 127 / FULL) - original key (one slice per key with Key+ at +100), clamped to the
        | whole slices before (Fb) and after (Fa) slice 1
        move.w  -0x3E(%a5),%d0
        ext.l   %d0
        moveq   #127,%d7
        muls.l  %d7,%d0
        move.l  #FULL/2,%d7
        tst.l   %d0
        bpl.s   1f
        neg.l   %d7
1:      add.l   %d7,%d0
        move.l  #FULL,%d7
        divs.l  %d7,%d0
        moveq   #0,%d7
        move.b  -0x3B(%a5),%d7              | original key (voice+0x1F)
        sub.l   %d7,%d0                     | j
        sub.l   %d3,%d1
        addq.l  #1,%d1
        divu.l  %d5,%d1                     | Fa
        cmp.l   %d1,%d0
        ble.s   2f
        move.l  %d1,%d0
2:      move.l  %d2,%d1
        sub.l   %d4,%d1
        divu.l  %d5,%d1
        neg.l   %d1                         | -Fb
        cmp.l   %d1,%d0
        bge.s   3f
        move.l  %d1,%d0
3:      move.l  %d0,%d1
5:      muls.l  %d5,%d1                     | shift = j * L
        add.l   %d1,%d2                     | slice start
        | play start: keep its offset from the sample start (SStart, ITD), limited to the slice
        move.l  0x0C(%a1),%d0
        sub.l   %d4,%d0                     | offset
        bpl.s   6f
        moveq   #0,%d0
6:      cmp.l   %d5,%d0
        blt.s   7f
        move.l  %d5,%d0
        subq.l  #1,%d0
7:      add.l   %d2,%d0
        move.l  %d0,0x0C(%a1)
        moveq   #8,%d0
        cmp.l   0x10(%a1),%d0               | loop start 8 = one-shot
        bne.s   8f
        add.l   %d1,%d3
        subq.l  #1,%d3
        move.l  %d3,0x14(%a1)               | end = slice end (inclusive)
        rts
8:      add.l   %d1,0x10(%a1)               | looped: the loop moves with the slice
        add.l   %d1,0x14(%a1)
9:      rts

        .section .slT,"ax"
| ---- shift_t: jsr from the tick call 0x5FECA (patches/slpscn/slew.s follows it in place): d7 = target loop shift
| (shift_w), a0 = stored shift (pitch struct +0x2C), d1 = d7 - a0 with the flags set.
shift_t:
        jsr     shift_w
        movea.w 0x2C(%a5),%a0
        move.l  %d7,%d1
        sub.l   %a0,%d1
        rts

        .section .slS,"ax"
| ---- scan_start: note-on exit for non-Slice voices (jmp from slice_exit, does the stock epilogue). With a
| non-zero SLpScn sum (voice+0x1C) the note starts at the (already shifted) loop start instead of the sample start,
| so it does not run through the frames before the loop (the note-start noise burst). Each channel (left; right
| when stereo): only forward playback (+0x19 = 0) of a looped sample (loop start +0x10 != 8): +0x0C = +0x10.
scan_start:
        tst.w   -0x3E(%a5)
        beq.s   9f
        movea.l %a4,%a1
        bsr.s   sst
        moveq   #0,%d0
        move.b  0x18(%a4),%d0
        andi.l  #6,%d0                      | stereo
        beq.s   9f
        lea     0x448(%a2),%a1              | right note struct (channel + 0x3FE + 0x4A)
        bsr.s   sst
9:      movem.l (%sp),%d6-%d7/%a2/%a4-%a5
        lea     20(%sp),%sp
        rts
sst:    tst.b   0x19(%a1)
        bne.s   1f
        moveq   #8,%d0
        cmp.l   0x10(%a1),%d0
        beq.s   1f
        move.l  0x10(%a1),0x0C(%a1)
1:      rts

        .section .slF,"ax"
name_slice: .asciz "'Slice"
        .balign 2
