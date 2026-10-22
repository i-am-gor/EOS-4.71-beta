| Beat Munger "Slice" soft key (EOS 4.71-beta2, notes/slicer_design.md).
| Turns the Beat Munger's analysed slice list into one new sample per slice (copied with Copy Section's own
| routine 0xF7050 through the clipboard slot, whose contents are saved and put back) and a new preset with one
| zone per slice, slice 1 on key KEY0 and each next slice one key up, each zone's original key = its key.
| Nothing is changed until every check has passed (slices, free sample slots, a free preset, sample memory).
|
| Beat Munger slice entry (0xE9AA6): (0x40000000 | channel base) + 2*nch*frame, frame counted from the base.
| Copy region frame r reads base + start + 4 + 2r (0xF6F78), so r = frame - 2 - start/2.
| Each cut is PRE frames before its onset (the analyser's onsets come ~7-8 ms after the attack starts).
| Each cut then moves back to the last zero crossing of the first channel within SNAPW frames (none: unchanged),
| read through the sample port the way the analyser reads (0xE9F34..0xEA014).
| Slice 1 always starts at region 0; later cuts closer than MINF frames to the previous one or the end are
| dropped; at most MAXK slices (keys KEY0..127).
        .equ    RGN_S, 0x10000E14
        .equ    RGN_E, 0x10000E18
        .equ    RGN_C, 0x10000E0E
        .equ    CURHDR, 0x10005000
        .equ    PLAYER, 0x100042F4
        .equ    DEFER, 0x10003EE8
        .equ    KEY0, 36
        .equ    MAXK, 92
        .equ    MINF, 1024              | shortest slice (~23 ms)
        .equ    PRE, 512                | cut this far before each onset (~11 ms)
        .equ    SNAPW, 256              | then back to the nearest zero crossing, at most this far (~6 ms)
        .equ    CHIP, 0x10003DCC        | -> sample port registers; +0x1C reads the next sample
        .equ    PORT_ADDR, 0x956D4      | set the read address (as the Beat Munger analyser, 0xE9F44)
        .equ    PORT_END, 0x95BA4
        .equ    AUD_STOP, 0xE405C
        .equ    AUD_BUSY, 0xE4008
        .equ    BM_EXIT, 0xB6080
        .equ    STATUS, 0x1A20D8
        .equ    SPRINTF, 0x1A6EA0
        .equ    SMP_HDR, 0x13D32C
        .equ    SMP_LEN, 0x13D5E0
        .equ    SMP_REG, 0x13E854
        .equ    SMP_UNREG, 0x13E8C8
        .equ    SMP_NAME, 0x13D48C
        .equ    MEM_NEED, 0x13E3C8
        .equ    MEM_SYNC, 0x13DF14
        .equ    VOICES_OFF, 0x23E84
        .equ    VOICES_ON, 0x23F14
        .equ    COPY_CLIP, 0xF7050
        .equ    PRE_PTR, 0x139728
        .equ    PRE_NEW, 0x13C52C
        .equ    PRE_NAME, 0x13CD68
        .equ    PRE_SEL, 0x13A484
        .equ    VOICE_I, 0x513F4
        .equ    ZONE_ADD, 0x50E40
| locals (a6)
        .equ    CLIP, -96               | 92-byte clipboard header copy
        .equ    NAME, -120              | 20-byte name buffer
        .equ    SV_S, -124
        .equ    SV_E, -128
        .equ    SV_C, -132
        .equ    HAVECLIP, -136
        .equ    RMAX, -140
        .equ    EBASE, -144             | entry base (0x40000000 | channel base) before any compaction
        .equ    R0, -148                | frame offset of region 0
        .equ    SHIFT, -152             | log2(2*nch)
        .equ    PRESET, -156
        .equ    SLOT0, -160             | sample slot of slice 1
        .equ    LASTSLOT, -164
        .equ    K, -168
        .equ    TOTAL, -172
        .equ    LOC, 176

        .section .slcx,"ax"
        .globl  slc_key, slc_name
slc_key:
        link    %a6,#-LOC
        lea     -40(%sp),%sp
        movem.l %d2-%d7/%a2-%a5,(%sp)
        jsr     AUD_STOP
        jsr     AUD_BUSY
        tst.b   %d0
        beq.s   1f
        lea     slc_key(%pc),%a0        | still playing: run again when it stops (as OK does)
        move.l  %a0,DEFER
        bra.w   out
1:      clr.l   DEFER
        movea.l PLAYER,%a0
        move.l  %a0,%d0
        beq.w   e_none
        move.l  0x23A(%a0),%d7          | slice count
        movea.l 0x23E(%a0),%a4          | slice entries
        move.l  %a4,%d0
        beq.w   e_none
        tst.l   %d7
        ble.w   e_none
        movea.l CURHDR,%a5
        moveq   #0,%d5
        move.b  0x3A(%a5),%d5
        lsr.l   #1,%d5
        moveq   #3,%d0
        and.l   %d0,%d5                 | channel bits: 1 L, 2 R, 3 stereo
        beq.w   e_none
        moveq   #0,%d1
        btst    #0,%d5
        bne.s   2f
        moveq   #4,%d1                  | right only
2:      move.l  0x3C(%a5,%d1.l),%d0
        ori.l   #0x40000000,%d0
        move.l  %d0,EBASE(%a6)
        move.l  0x14(%a5,%d1.l),%d0
        asr.l   #1,%d0
        addq.l  #2,%d0
        move.l  %d0,R0(%a6)
        moveq   #1,%d0
        cmp.l   #3,%d5
        bne.s   3f
        moveq   #2,%d0
3:      move.l  %d0,SHIFT(%a6)
        move.l  %a5,-(%sp)
        jsr     SMP_LEN
        addq.l  #4,%sp
        subq.l  #5,%d0                  | last region frame (Sample Edit's own limit, 0x48D88)
        move.l  %d0,RMAX(%a6)
        cmp.l   #3*MINF,%d0
        blt.w   e_none
| ---- pass 1: count slices and the memory they need (nothing written) ----
        sub.l   %a1,%a1                 | no write
        bsr.w   conv
| ---- free sample slots >= K, and a free preset ----
        moveq   #0,%d6                  | free slots found
        moveq   #1,%d4
4:      move.l  %d4,-(%sp)
        jsr     SMP_HDR
        addq.l  #4,%sp
        tst.l   %d0
        bne.s   5f
        addq.l  #1,%d6
5:      addq.l  #1,%d4
        cmp.l   #1000,%d4
        blt.s   4b
        cmp.l   K(%a6),%d6
        blt.w   e_room
        moveq   #0,%d4
6:      move.l  %d4,-(%sp)
        jsr     PRE_PTR
        addq.l  #4,%sp
        tst.l   %d0
        beq.s   7f
        addq.l  #1,%d4
        cmp.l   #1000,%d4
        blt.s   6b
        bra.w   e_room
7:      move.l  %d4,PRESET(%a6)
| ---- sample memory (may compact sample RAM: slice entries are read against EBASE, saved above) ----
        jsr     VOICES_OFF              | as the Sample Edit op wrapper 0xFB564
        jsr     MEM_SYNC
        move.l  TOTAL(%a6),-(%sp)
        jsr     MEM_NEED
        addq.l  #4,%sp
        addq.l  #1,%d0
        beq.w   e_mem
| ---- committed ----
        movea.l %a4,%a1                 | pass 2: region starts of slices 2..K into the entry list
        bsr.w   conv
| ---- snap the cuts of slices 2..K back to the nearest zero crossing (d7, the entry count, is free now) ----
        moveq   #0,%d1
        btst    #0,%d5
        bne.s   1f
        moveq   #4,%d1
1:      move.l  0x3C(%a5,%d1.l),%d4     | channel base now (the memory check may have moved the data)
        ori.l   #0x40000000,%d4
        moveq   #1,%d6                  | slice i, cut = entry[i-1]
2:      cmp.l   K(%a6),%d6
        bge.s   6f
        move.l  -4(%a4,%d6.l*4),%d2
        sub.l   #SNAPW,%d2              | first frame read
        move.l  %d2,%d0
        add.l   R0(%a6),%d0
        add.l   %d0,%d0
        add.l   %d4,%d0
        move.l  %d0,-(%sp)
        jsr     PORT_ADDR
        addq.l  #4,%sp
        movea.l CHIP,%a2
        move.w  0x1C(%a2),%d1
        ext.l   %d1                     | sample at d2
        moveq   #-1,%d3                 | offset of the last crossing
        moveq   #1,%d7
3:      move.w  0x1C(%a2),%d0
        ext.l   %d0
        eor.l   %d0,%d1
        bpl.s   4f                      | same sign
        move.l  %d7,%d3                 | sign changed: cut at d2 + d7
4:      move.l  %d0,%d1
        addq.l  #1,%d7
        cmp.l   #SNAPW,%d7
        ble.s   3b
        tst.l   %d3
        bmi.s   5f
        add.l   %d3,%d2
        move.l  %d2,-4(%a4,%d6.l*4)
5:      addq.l  #1,%d6
        bra.s   2b
6:      jsr     PORT_END
        move.l  RGN_S,%d0
        move.l  %d0,SV_S(%a6)
        move.l  RGN_E,%d0
        move.l  %d0,SV_E(%a6)
        moveq   #0,%d0
        move.b  RGN_C,%d0
        move.l  %d0,SV_C(%a6)
        clr.l   -(%sp)
        jsr     SMP_HDR                 | save the clipboard header (0xF7050 overwrites slot 0)
        addq.l  #4,%sp
        move.l  %d0,HAVECLIP(%a6)
        beq.s   8f
        movea.l %d0,%a0
        lea     CLIP(%a6),%a1
        bsr.w   copy92
8:      clr.l   LASTSLOT(%a6)
        moveq   #0,%d6                  | slice index
| ---- one sample per slice: start = 0 or entry[i-1], end = entry[i] - 1 or RMAX ----
sloop:  moveq   #0,%d2
        tst.l   %d6
        beq.s   1f
        move.l  -4(%a4,%d6.l*4),%d2
1:      move.l  RMAX(%a6),%d3
        move.l  %d6,%d0
        addq.l  #1,%d0
        cmp.l   K(%a6),%d0
        bge.s   2f
        move.l  (%a4,%d6.l*4),%d3
        subq.l  #1,%d3
2:      move.l  %d2,RGN_S
        move.l  %d3,RGN_E
        move.b  %d5,RGN_C
        jsr     COPY_CLIP               | slot 0 = region d2..d3 of the current sample
        move.l  LASTSLOT(%a6),%d4       | next empty slot 1..999
3:      addq.l  #1,%d4
        move.l  %d4,-(%sp)
        jsr     SMP_HDR
        addq.l  #4,%sp
        tst.l   %d0
        bne.s   3b
        move.l  %d4,LASTSLOT(%a6)
        move.l  %d4,-(%sp)
        jsr     SMP_REG
        movea.l %d0,%a3
        clr.l   (%sp)
        jsr     SMP_HDR
        addq.l  #4,%sp
        movea.l %d0,%a0
        movea.l %a3,%a1
        bsr.w   copy92                  | slot 0 header -> new slot
        clr.l   -(%sp)
        jsr     SMP_UNREG               | slot 0 empty again
        addq.l  #4,%sp
        bsr.w   mkname                  | "<name> " into NAME, a0 = its end
        move.l  %d6,%d0
        addq.l  #1,%d0
        move.l  %d0,-(%sp)
        pea     fmt_n(%pc)
        move.l  %a0,-(%sp)
        jsr     SPRINTF                 | "<name> NN"
        clr.l   (%sp)                   | len 0 = strlen
        pea     NAME(%a6)
        move.l  %d4,-(%sp)
        jsr     SMP_NAME
        lea     20(%sp),%sp
        tst.l   %d6                     | remember the slot: slice 1 in SLOT0, slice i+1 over entry[i-1]
        bne.s   4f
        move.l  %d4,SLOT0(%a6)
        bra.s   5f
4:      move.l  %d4,-4(%a4,%d6.l*4)
5:      addq.l  #1,%d6
        cmp.l   K(%a6),%d6
        blt.w   sloop
| ---- clipboard back, Sample Edit region back ----
        move.l  HAVECLIP(%a6),%d0
        beq.s   1f
        clr.l   -(%sp)
        jsr     SMP_REG
        addq.l  #4,%sp
        movea.l %d0,%a1
        lea     CLIP(%a6),%a0
        bsr.w   copy92
1:      move.l  SV_S(%a6),%d0
        move.l  %d0,RGN_S
        move.l  SV_E(%a6),%d0
        move.l  %d0,RGN_E
        move.l  SV_C(%a6),%d0
        move.b  %d0,RGN_C
        jsr     MEM_SYNC
| ---- preset: one zone per slice ----
        move.l  PRESET(%a6),-(%sp)
        jsr     PRE_NEW
        addq.l  #4,%sp
        tst.l   %d0
        beq.w   9f
        moveq   #0,%d6
2:      move.l  PRESET(%a6),-(%sp)
        jsr     PRE_PTR
        tst.l   %d0
        beq.s   7f
        clr.l   (%sp)
        move.l  %d0,-(%sp)
        jsr     VOICE_I                 | voice 0 (re-fetched: the preset block can move)
        addq.l  #4,%sp
7:      addq.l  #4,%sp
        tst.l   %d0
        beq.s   8f
        movea.l %d0,%a0
        lea     0x11C(%a0),%a3          | zone 1 of the default voice
        tst.l   %d6
        beq.s   3f
        move.l  PRESET(%a6),-(%sp)
        move.l  %a0,-(%sp)
        jsr     ZONE_ADD
        addq.l  #8,%sp
        movea.l %d0,%a3
        tst.l   %d0
        beq.s   8f
3:      moveq   #KEY0,%d0
        add.l   %d6,%d0
        move.b  %d0,(%a3)               | key low
        clr.b   1(%a3)
        clr.b   2(%a3)
        move.b  %d0,3(%a3)              | key high
        move.b  %d0,12(%a3)             | original key
        move.l  SLOT0(%a6),%d1
        tst.l   %d6
        beq.s   4f
        move.l  -4(%a4,%d6.l*4),%d1
4:      move.w  %d1,8(%a3)              | sample
        addq.l  #1,%d6
        cmp.l   K(%a6),%d6
        blt.s   2b
8:      bsr.w   mkname
        clr.b   -1(%a0)                 | preset name = sample name
        pea     NAME(%a6)
        move.l  PRESET(%a6),-(%sp)
        jsr     PRE_NAME
        addq.l  #4,%sp
        move.l  PRESET(%a6),(%sp)
        jsr     PRE_SEL
        addq.l  #4,%sp
9:      jsr     VOICES_ON
        jsr     BM_EXIT
        move.l  PRESET(%a6),-(%sp)
        move.l  K(%a6),-(%sp)
        pea     msg_ok(%pc)
        bra.s   msg
e_mem:  jsr     VOICES_ON
        jsr     BM_EXIT                 | sample RAM may have been compacted: leave Beat Munger
        pea     msg_mem(%pc)
        bra.s   msg
e_room: pea     msg_room(%pc)
        bra.s   msg
e_none: pea     msg_none(%pc)
msg:    jsr     STATUS
out:    movem.l -LOC-40(%a6),%d2-%d7/%a2-%a5
        unlk    %a6
        rts

| conv: stream the slice entries; region start r = (entry - EBASE) >> SHIFT - R0 - PRE. Keeps r when it is at least
| MINF after the previous kept start and MINF before the end, up to MAXK slices. a1 = 0: count only;
| otherwise kept starts of slices 2.. are written from a1 (never ahead of the read). Sets K and TOTAL
| (sum over slices of (2*len + 10 + 0x5C) * nch + 10, Copy Section's own size per copy 0xF72F2).
conv:   movea.l %a4,%a0
        move.l  %d7,%d4                 | entries left
        moveq   #0,%d2                  | previous kept start
        moveq   #1,%d6                  | slices so far
        clr.l   TOTAL(%a6)
1:      move.l  (%a0)+,%d0
        sub.l   EBASE(%a6),%d0
        move.l  SHIFT(%a6),%d1
        asr.l   %d1,%d0
        sub.l   R0(%a6),%d0
        sub.l   #PRE,%d0                | Beat Munger's onsets lag the attack by ~7-8 ms (measured, P005)
        move.l  %d2,%d1
        add.l   #MINF,%d1
        cmp.l   %d1,%d0
        blt.s   2f
        move.l  RMAX(%a6),%d1
        sub.l   #MINF,%d1
        cmp.l   %d1,%d0
        bgt.s   2f
        cmp.l   #MAXK,%d6
        bge.s   3f
        move.l  %a1,%d1
        beq.s   4f
        move.l  %d0,(%a1)+
4:      move.l  %d0,%d3
        sub.l   %d2,%d3                 | length of the slice that ends here
        bsr.s   size
        move.l  %d0,%d2
        addq.l  #1,%d6
2:      subq.l  #1,%d4
        bne.s   1b
3:      move.l  RMAX(%a6),%d3
        sub.l   %d2,%d3
        addq.l  #1,%d3
        bsr.s   size
        move.l  %d6,K(%a6)
        rts
size:   add.l   %d3,%d3
        add.l   #10+0x5C,%d3
        cmp.l   #3,%d5
        bne.s   1f
        add.l   %d3,%d3
1:      add.l   #10,%d3
        add.l   %d3,TOTAL(%a6)
        rts

| mkname: up to 12 characters of the current sample's name, trailing spaces dropped, then one space, into NAME.
| Returns a0 = the end (where the number goes).
mkname: movea.l CURHDR,%a1
        lea     NAME(%a6),%a0
        moveq   #12,%d0
1:      move.b  (%a1)+,(%a0)+
        subq.l  #1,%d0
        bne.s   1b
        lea     NAME(%a6),%a1
2:      cmpa.l  %a1,%a0
        beq.s   3f
        moveq   #0,%d0
        move.b  -1(%a0),%d0
        beq.s   4f
        moveq   #0x20,%d1
        cmp.l   %d1,%d0
        bne.s   3f
4:      subq.l  #1,%a0
        bra.s   2b
3:      moveq   #0x20,%d0
        move.b  %d0,(%a0)+
        clr.b   (%a0)
        rts

copy92: moveq   #23,%d0
1:      move.l  (%a0)+,(%a1)+
        subq.l  #1,%d0
        bne.s   1b
        rts

slc_name: .asciz "Slice"
fmt_n:  .asciz  "%02d"
msg_ok: .asciz  "Sliced: %d samples, preset %d"
msg_mem: .asciz "Slice: not enough sample memory"
msg_room: .asciz "Slice: no free sample slots/preset"
msg_none: .asciz "Slice: no slices to make"
        .even
