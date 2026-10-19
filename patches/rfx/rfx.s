| RFX amp path skip for EOS 4.70 (layer on Sync8c). Replaces FUN_00060674 in place (272 bytes).
| Stock: with the RFX card (0x10004D88 = 1) the amp tick calls FUN_00060674(struct, vol, pan, flag) on every
| 10 ms tick: it stores vol/pan/flag in the voice's RFX block (*(struct+0x72)), computes the four FX sends into
| it and calls the chip writer FUN_0010E280 (rewrites the chip volume, derives pan and sends, writes changed ones).
| New: identical computation and identical block writes. When the call comes from the amp tick, the new and
| the stored flag are 0, and vol, pan, all four sends and the global send offset (0x10004D84, low word,
| cached per voice) equal what the block already held, FUN_0010E280 is replaced by its one unconditional
| write: the chip volume byte (vol_only). Its pan/send caches already match, so its send writes would not
| happen. (The volume byte must be rewritten every tick like stock: something else nudges it by one step;
| the first version without this write measured +0.34 dB level jumps in the hardware null test.)
| Note-on calls (from FUN_000609D8) always run in full.
| Offset caches: unused bytes 14-15 of cord slots 0 (main) / 1 (stereo partner) at voice + 0x28C / 0x29C.

        .equ    WRITER,  0x0010E280
        .equ    TICK_LO, 0x00060B7C         | callers at/after this are the amp tick
        .equ    TABLE,   0x00061890
        .equ    MODE,    0x10004F04
        .equ    NOMULTI, 0x1000228C
        .equ    OFFSET,  0x10004D86         | low word of the global send offset

        .section .body,"ax"
        .globl  _start
_start:
| Every block store goes through cs (compare old word, set d3 if different, store): the block receives
| exactly stock's writes in stock's order; d3 says whether anything changed.
rfx_writer:
        lea     -36(%sp),%sp
        movem.l %d2-%d7/%a2/%a4-%a5,(%sp)   | args: struct 40, vol 46, pan 50, flag 52; caller at 36
        moveq   #0,%d3                      | changed
        movea.l 40(%sp),%a5
        move.l  %a5,%d4
        movea.l 0x72(%a5),%a0               | RFX block
        move.w  46(%sp),%d1
        bsr.w   cs                          | vol
        move.w  50(%sp),%d1
        bsr.w   cs                          | pan
        move.l  52(%sp),%d1                 | flag: changed unless old == new == 0
        bne.s   1f
        cmp.l   (%a0),%d1
        beq.s   2f
1:      moveq   #1,%d3
2:      move.l  %d1,(%a0)+                  | a0 = block + 8 (send 0)
        move.l  0x1A(%a5),%d0
        subq.l  #8,%d0
        bne.s   3f
        lea     -0x3FE(%a5),%a5             | stereo partner: sends come from the main struct
3:      movea.l 0xA(%a5),%a4                | channel
        lea     0x26E(%a5),%a1
        move.b  MODE,%d0
        extb.l  %d0
        subq.l  #2,%d0
        bne.s   plain
        move.b  2(%a4),%d0
        extb.l  %d0
        moveq   #-2,%d1
        cmp.l   %d1,%d0
        bne.s   plain
        tst.b   NOMULTI
        bne.s   plain
        moveq   #4,%d2                      | Multimode channel sends (stock arithmetic)
        lea     TABLE,%a2
m2:     move.w  0x50(%a4),%d0               | channel send word i (stock: 0x30(a4,(0x10 + i)*2))
        addq.l  #2,%a4
        ext.l   %d0
        asr.l   #5,%d0
        moveq   #-128,%d1
        cmp.l   %d1,%d0
        bge.s   4f
        move.l  %d1,%d0                     | (-128 also passes the upper clamp)
4:      moveq   #127,%d1
        cmp.l   %d1,%d0
        ble.s   5f
        move.l  %d1,%d0
5:      moveq   #0x65,%d1
        muls.l  %d1,%d0
        bge.s   6f
        addi.l  #127,%d0                    | x < 0: (x + 127) >> 7 == -((-x) >> 7) (stock)
6:      asr.l   #7,%d0
        extb.l  %d0
        addq.l  #2,%a1
        move.w  (%a2,%d0.l*2),%d0
        move.w  (%a1)+,%d1
        add.l   %d0,%d1
        bsr.s   cs
        addq.l  #8,%a0
        subq.l  #1,%d2
        bne.s   m2
        bra.s   sends_done
cs:     move.w  (%a0),%d0                   | (a0) = d1 word?  low word of the difference
        sub.l   %d1,%d0
        tst.w   %d0
        beq.s   8f
        moveq   #1,%d3
8:      move.w  %d1,(%a0)+
        rts
plain:  moveq   #4,%d2                      | voice send pairs
9:      move.w  (%a1)+,%d0
        move.w  (%a1)+,%d1
        add.l   %d0,%d1
        bsr.s   cs
        addq.l  #8,%a0
        subq.l  #1,%d2
        bne.s   9b
sends_done:
        lea     0x28C(%a5),%a0              | send-offset cache: main / stereo partner
        cmpa.l  %d4,%a5
        beq.s   10f
        lea     16(%a0),%a0
10:     move.w  OFFSET,%d1
        bsr.s   cs
        move.l  36(%sp),%d0                 | caller
        cmpi.l  #TICK_LO,%d0
        bcs.s   full                        | note-on: always
        tst.l   %d3
        bne.s   full
        jsr     vol_only                    | nothing changed: only stock's unconditional volume write
        bra.s   done
full:   movea.l %d4,%a0
        move.l  0x72(%a0),-(%sp)
        jsr     WRITER
        addq.l  #4,%sp
done:   movem.l (%sp),%d2-%d7/%a2/%a4-%a5
        lea     36(%sp),%sp
        rts

        .section .vtail,"ax"
| ---- skip path: the one write FUN_0010E280 does unconditionally for flag 0 (chip volume byte) ----
vol_only:
        movea.l %d4,%a0
        movea.l 0x72(%a0),%a0               | RFX block
        movea.l 0x36(%a0),%a1               | chip voice
        move.w  (%a0),%d0                   | vol, clamped 0..255 as in FUN_0010E280
        ext.l   %d0
        bge.s   1f
        moveq   #0,%d0
1:      move.l  #255,%d1
        cmp.l   %d1,%d0
        ble.s   2f
        move.l  %d1,%d0
2:      move.b  %d0,0x71(%a1)
        rts
