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
| While the gap word is negative the stored Rate byte becomes 128+division (the existing Rate names)
| and rate_set does not write. The LFO page paints that byte when it opens; rate_show asks it to
| paint again. The same paint reads the Rate widget's enable byte. Clearing it is what greys Tempo
| while the clock is external, so that byte is cleared while this LFO's gap word is negative.
| The cord stays in force through MIDI Stop and through a missing beat clock. The sum going
| zero or positive is what puts the saved Rate back. That sum is written only while a note
| sounds, so leaving the Cords page would leave Rate grey until the next note. The LFO page
| opener (0xCDA70, pages 0x12 and 0x13) calls rate_enter where it stores the page id. A cord
| with a negative amount aimed at this LFO can still hold Rate; amount zero or above, or no
| such cord, puts the saved Rate back before the page is drawn.

        .equ    LFO_TICK,      0x00020400
        .equ    SYNC_BODY,     0x0002040E
        .equ    LFO2_TICK_RET, 0x00061D70
        .equ    FULL,          4032
        .equ    RATE_SET,      0x00069F80
        .equ    LFO_FMT,       0x00068BF0
        .equ    VOICE_NOW,     0x00139728
        .equ    VOICE_IX,      0x1000134A
        .equ    EDIT_VOICE,    0x100040AC   | preset screen's voice
        .equ    HOLD,          0x100003EC   | saved Rates, magic at +2
        .equ    PAGE_ID,       0x1000415C   | preset page being shown
        .equ    PAGE_CACHE,    0x102C327C   | built pages; the opener's moveq #-11 makes the index page-11
        .equ    SCREEN_VT,     0x000B2D1C   | cached LFO page object. Its page pointer is the long at +0x38.
        .equ    CORDS,         0xBC         | 24 x {src, dst, amt, pad} on the preset voice. Amounts are -100..100.

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
3:      bsr     rate_publish            | panel shows the edited voice's Rate byte
        tst.w   %d0
        bmi.s   4f
        jmp     LFO_TICK                | zero or positive: Rate path
4:      ext.l   %d0
        lea     -8(%sp),%sp
        movem.l %d2-%d3,(%sp)
        cmpi.l  #LFO2_TICK_RET,%d1
        bne.s   5f
        subq.l  #1,%d0                  | undo the stock long-1 in the low half
5:      bsr.s   cord_div
        ori.l   #0xA000,%d0             | bit 15 active, bit 13 key sync
        cmpi.l  #LFO2_TICK_RET,%d1
        bne.s   7f
        ori.l   #0x4000,%d0             | LFO 2 note-tick base
7:      movem.l (%sp),%d2-%d3
        lea     8(%sp),%sp
        jmp     SYNC_BODY

| d0 = sign-extended gap word, already adjusted for LFO 2. Negative. Returns the division in d0.
| Clobbers d2-d3. The caller has saved them.
cord_div:
        neg.l   %d0
        subq.l  #1,%d0
        lsl.l   #4,%d0
        move.l  %d0,%d3
        move.l  #FULL,%d2
        divu.l  %d2,%d3
        move.l  %d3,%d0
        cmpi.l  #15,%d0
        bls.s   1f
        moveq   #15,%d0
1:      rts

| Preset screen's voice in a0, or the indexed one when that pointer is clear.
| Clobbers d0/d1/a0/a1.
voice_now:
        move.l  EDIT_VOICE,%d0
        bne.s   1f
        move.w  VOICE_IX,%d0
        ext.l   %d0
        move.l  %d0,-(%sp)
        jsr     VOICE_NOW
        addq.l  #4,%sp
1:      movea.l %d0,%a0
        rts

| d0.w = the gap word just read, d1 = the tick return address. Puts 128+division into the
| edited voice's Rate byte while the word is negative, and puts the original byte back when
| it is not. The panel redraws that byte; the sounding path does not read it while overridden.
| Preserves d0, d1 and a5.
rate_publish:
        lea     -24(%sp),%sp
        movem.l %d0-%d3/%a0-%a1,(%sp)
        move.l  EDIT_VOICE,%a0
        move.l  %a0,%d2
        beq.w   9f
        lea     HOLD,%a1
        moveq   #0,%d2
        move.b  2(%a1),%d2
        cmpi.l  #0xC3,%d2
        beq.s   1f
        moveq   #-1,%d2
        move.b  %d2,(%a1)
        move.b  %d2,1(%a1)
        moveq   #0,%d2
        move.b  #0xC3,%d2
        move.b  %d2,2(%a1)
1:
        cmpi.l  #LFO2_TICK_RET,%d1
        bne.s   2f
        addq.l  #1,%a1
        move.w  %d0,0x1A6(%a0)
        moveq   #0,%d3
        move.w  #0x9E,%d3
        bra.s   3f
2:      move.w  %d0,0x1A4(%a0)
        moveq   #0,%d3
        move.w  #0x96,%d3
3:      adda.l  %d3,%a0                 | a0 = Rate byte
        tst.w   %d0
        bmi.s   4f
        moveq   #0,%d2
        move.b  (%a1),%d2
        cmpi.l  #0xFF,%d2
        beq.s   9f
        moveq   #0,%d3
        move.b  (%a0),%d3
        cmp.l   %d2,%d3
        beq.s   7f
        move.b  %d2,(%a0)
        bsr     rate_show
7:      move.b  #0xFF,(%a1)
        bra.s   9f
4:      moveq   #0,%d2
        move.b  (%a1),%d2
        cmpi.l  #0xFF,%d2
        bne.s   5f
        move.b  (%a0),(%a1)             | keep the Rate this cord is covering
5:      move.l  (%sp),%d0
        ext.l   %d0
        cmpi.l  #LFO2_TICK_RET,%d1
        bne.s   6f
        subq.l  #1,%d0
6:      bsr     cord_div
        addi.l  #128,%d0
        moveq   #0,%d2
        move.b  %d0,%d2
        moveq   #0,%d3
        move.b  (%a0),%d3
        cmp.l   %d2,%d3
        beq.s   9f
        move.b  %d2,(%a0)
        bsr     rate_show
9:      move.l  (%sp),%d0
        move.l  4(%sp),%d1              | rate_show reuses d1; the tick return is the saved one
        bsr.s   rate_tone
        movem.l (%sp),%d0-%d3/%a0-%a1
        lea     24(%sp),%sp
        rts

| d0.w = this LFO's gap word, d1 = the tick return. Grey this page's Rate widget while the word
| is negative. A rebuilt page comes back enabled, so the widget byte itself is the record.
rate_tone:
        move.l  PAGE_ID,%d2
        moveq   #0x12,%d3
        cmpi.l  #LFO2_TICK_RET,%d1
        bne.s   1f
        addq.l  #1,%d3
1:      cmp.l   %d3,%d2
        bne.s   9f
        tst.w   %d0
        bmi.s   2f
        moveq   #1,%d0
        bra.s   3f
2:      moveq   #0,%d0
3:      bsr.s   rate_grey
        beq.s   9f
        bsr.s   rate_show
9:      rts

| d0 = 1 to show Rate normally, 0 to grey it. Returns Z set when the widget is already that way.
| The cached object is the field list. Its container's first child is Rate. The paint reads
| byte +0x3A, and a focused field also has +0x24 set.
rate_grey:
        move.l  %d0,%d2
        bsr.s   rate_slot
        move.l  %a0,%d0
        beq.s   9f
        move.l  (%a0),%d0
        cmpi.l  #SCREEN_VT,%d0
        bne.s   7f
        move.l  0x30(%a0),%d0
        beq.s   9f
        movea.l %d0,%a0
        move.l  0x0C(%a0),%d0
        beq.s   9f
        movea.l %d0,%a0
        moveq   #0,%d0
        move.b  0x3A(%a0),%d0
        cmp.l   %d2,%d0
        beq.s   9f
        move.b  %d2,0x3A(%a0)
        bne.s   8f
        clr.b   0x24(%a0)
8:      moveq   #1,%d0
        rts
7:      moveq   #0,%d0
9:      rts

| The open LFO page (id 0x12 or 0x13) reads its fields again, the same way re-opening it does.
| Preserves a5. No page object means there is nothing to draw.
rate_show:
        bsr.s   rate_slot
        move.l  %a0,%d1
        beq.s   9f
        move.l  %a5,-(%sp)
        pea     3
        move.l  %d0,-(%sp)
        jsr     0xCC1CC
        addq.l  #8,%sp
        movea.l (%sp)+,%a5
9:      rts

| Page object of the open LFO page in a0, and its cache index in d0. a0 is 0 otherwise.
rate_slot:
        move.l  PAGE_ID,%d0
        subi.l  #0x12,%d0
        moveq   #1,%d1
        cmp.l   %d1,%d0
        bhi.s   1f
        addq.l  #7,%d0
        movea.l #PAGE_CACHE,%a0
        move.l  (%a0,%d0.l*4),%a0
        rts
1:      suba.l  %a0,%a0
        rts

| (descriptor, value). While the gap word is negative the stored Rate is left alone.
| The panel reads the Rate byte itself, so the descriptor getter stays the stock zero.
        .globl  rate_set
rate_set:
        move.l  4(%sp),-(%sp)
        bsr     voice_now
        move.l  %a0,%d0
        beq.s   1f
        movea.l (%sp),%a1
        moveq   #0,%d1
        move.w  0x10(%a1),%d1
        cmpi.l  #0x9E,%d1
        beq.s   2f
        move.w  0x1A4(%a0),%d0
        bra.s   3f
2:      move.w  0x1A6(%a0),%d0
3:      tst.w   %d0
        bpl.s   1f                      | zero or positive: the knob writes
        addq.l  #4,%sp
        rts
1:      addq.l  #4,%sp
        jmp     RATE_SET

| The LFO opener's move.l d7,PAGE_ID and add.l d7,d6. d7 is the page, d6 arrived as -11.
| Both survive the refresh that rate_open may run. The opener still uses them afterwards.
        .globl  rate_enter
rate_enter:
        move.l  %d7,PAGE_ID
        add.l   %d7,%d6
        lea     -8(%sp),%sp
        movem.l %d6-%d7,(%sp)
        bsr     rate_open
        movem.l (%sp),%d6-%d7
        lea     8(%sp),%sp
        rts

| Release this page's Rate when the preset no longer has a negative-amount cord aimed at
| it. The gap word can still be the sum from the last note. A negative amount whose
| controller is idle stays held until that note's cord pass, which is what sums it.
        .globl  rate_open
rate_open:
        move.l  PAGE_ID,%d0
        moveq   #0x12,%d1
        cmp.l   %d1,%d0
        beq.s   .Lopen1
        addq.l  #1,%d1
        cmp.l   %d1,%d0
        bne.s   .Lopen9
        moveq   #98,%d2
        addq.l  #8,%d2
        addq.l  #1,%d2                  | 107, Lfo2Ck
        bra.s   .Lscan
.Lopen1:
        moveq   #98,%d2                 | Lfo1Ck
.Lscan:
        move.l  EDIT_VOICE,%a0
        move.l  %a0,%d0
        beq.s   .Lopen9
        lea     CORDS(%a0),%a0
        moveq   #24,%d1
.Lcord:
        tst.b   (%a0)
        beq.s   .Lnext
        moveq   #0,%d0
        move.b  1(%a0),%d0
        cmp.l   %d2,%d0
        bne.s   .Lnext
        tst.b   2(%a0)                  | panel amount. Zero and above never engage.
        bmi.s   .Lopen9
.Lnext:
        addq.l  #4,%a0
        subq.l  #1,%d1
        bne.s   .Lcord
        moveq   #0,%d0                  | idle gap. LFO 2 keeps the stock 1.
        moveq   #0,%d1
        cmpi.l  #98,%d2
        beq.s   .Lpub
        moveq   #1,%d0
        move.l  #LFO2_TICK_RET,%d1
.Lpub:
        bsr     rate_publish
.Lopen9:
        rts
