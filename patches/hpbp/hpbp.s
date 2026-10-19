| OB-Xa high-pass / band-pass for EOS 4.70: replaces the computeFrames/packQ methods of
| 2nd Order High-pass, 4th Order High-pass, 2nd Order Band-pass and 4th Order Band-pass.
| Pole words come from tables (tools/hpbp.py -> tables.inc); every other word, the chip mode
| (FUN_0010D3B0 flags 0xC0), the gain word (DAT_10004D7C) and the return values are stock.
|
| Code lives in the four stock method bodies being replaced (sections .hp2 .hp4 .bp2 .bp4, each
| exactly the cf+pq extent) plus the shared routines in the image header padding (.hdr2).
|
| Descriptor (16 bytes + 8 per constant word):
|   +0 tabA  +4 tabB  +8 offA shiftA offB(0xFF none) shiftB  +12 retshift(0 = HP) nconst maskB boost
|   +16 { .long value, .word offset, .word 0 } * nconst
| computeFrames: words 0,1,4,5,8 = NEUTRAL, then constants, then table words; word 9 = gain base;
|   SETMODE(blk, mode, 0xC0); return HP: 0, BP: -(q >> retshift)
| packQ: constants + table words; return HP: 1, BP: -(q >> retshift)

        .equ    NEUTRAL,  0xFFCFFFCF
        .equ    GAINBASE, 0x10004D7C
        .equ    SETMODE,  0x0010D3B0
        .equ    HP_ZERO,  0x80048004
        .equ    BP_W01,   0xFF68FFCF
        .equ    BP_ZERO,  0xFF04FF90
        .equ    CBP_ZERO, 0xFFD0FF20       | Contrary BP zero: F moves against the cutoff
        .equ    STRCPY,   0x001A6C4C
        .equ    SPRINTF,  0x001A6EA0
        .equ    S_EMPTY,  0x00068CA0       | ""
        .equ    S_FREQ,   0x00068CA4       | "Frequency"
        .equ    S_FMT_D,  0x00068CB0       | "%d"
        .equ    S_FMT_HZ, 0x00068CC0       | "%dHz"
        .equ    S_Q,      0x00068CC8       | "Q"
        .equ    W0, 0
        .equ    W1, 4
        .equ    W4, 16
        .equ    W5, 20
        .equ    W8, 32

        .include "tables.inc"           | HP_SVF/HP_LADA (32 longs), HP_LADB (8), BP_* likewise (macros)

| ===== 2nd Order High-pass: body 0x660CC..0x66177 =====
        .section .hp2,"ax"
        .globl  _start
_start:
hp2_cf: lea     desc_hp2(%pc),%a1
        jmp     common_cf
hp2_pq: lea     desc_hp2(%pc),%a1
        jmp     common_pq
desc_hp2:
        .long   hp_svf, 0
        .byte   W4, 2, 0xFF, 0, 0, 1, 0, 0
        .long   HP_ZERO
        .word   W1, 0
hp_svf: HP_SVF_TABLE

| ===== 4th Order High-pass: body 0x66278..0x6632B =====
        .section .hp4,"ax"
hp_lada: HP_LADA_TABLE
hp_ladb: HP_LADB_TABLE
hp4_cf: lea     desc_hp4(%pc),%a1
        bra.w   common_cf
hp4_pq: lea     desc_hp4(%pc),%a1
        bra.w   common_pq

| ===== 2nd Order Band-pass: body 0x668A8..0x6697F =====
        .section .bp2,"ax"
bp2_cf: lea     desc_bp2(%pc),%a1
        jmp     common_cf
bp2_pq: lea     desc_bp2(%pc),%a1
        jmp     common_pq
desc_bp2:
        .long   bp_svf, 0
        .byte   W8, 2, 0xFF, 0, 3, 3, 0, 0
        .long   BP_W01
        .word   W0, 0
        .long   BP_W01
        .word   W1, 0
        .long   BP_ZERO
        .word   W5, 0
bp_svf: BP_SVF_TABLE
| d0 += (q*q*B) >> 14, B = descriptor byte 15 (4th BP); d1 = q, d2 = retshift (< 256). Clobbers d1, d2.
bp_boost:
        move.b  15(%a1),%d2
        beq.s   1f
        muls.l  %d1,%d1
        muls.l  %d2,%d1
        moveq   #14,%d2
        asr.l   %d2,%d1
        add.l   %d1,%d0
1:      rts

| ===== 4th Order Band-pass: body 0x6698C..0x66A6B =====
        .section .bp4,"ax"
bp4_cf: lea     desc_bp4(%pc),%a1
        jmp     common_cf
bp4_pq: lea     desc_bp4(%pc),%a1
        jmp     common_pq
desc_bp4:
        .long   bp_lada, bp_ladb
        .byte   W0, 2, W8, 3, 2, 2, 15, BP4_BOOST
        .long   BP_ZERO
        .word   W1, 0
        .long   BP_ZERO
        .word   W5, 0
bp_lada: BP_LADA_TABLE
| 4th Order High-pass descriptor
desc_hp4:
        .long   hp_lada, hp_ladb
        .byte   W4, 2, W8, 4, 0, 2, 7, 0
        .long   HP_ZERO
        .word   W1, 0
        .long   HP_ZERO
        .word   W5, 0


| ===== Contrary Band-pass: body 0x66A78..0x66B37 =====
| HPBP6: OB-Xa SVF F bytes (BP display) with the stock contrary X law (cbp_tab) in word 0; stock contrary
| zero in word 5; returns as stock (computeFrames 0, packQ 1).
        .section .cbp,"ax"
cbp_cf: lea     desc_cbp(%pc),%a1
        jmp     common_cf
cbp_pq: lea     desc_cbp(%pc),%a1
        jmp     common_pq
desc_cbp:
        .long   cbp_tab, 0
        .byte   W0, 2, 0xFF, 0, 0, 1, 0, 0
        .long   CBP_ZERO
        .word   W5, 0
cbp_tab: CBP_TABLE

| ===== HP/BP Frequency/Q display: one routine in the old HP formatter body 0x66178..0x6626B =====
| Identical text to stock FilterShared_formatParam_66178 (HP) and 0x667A8 (BP / Contrary BP):
|   idx 0: "Frequency", "%dHz" of start*(R/1024)^(255-v) (odd steps start from the odd value)
|   idx 1: "Q", "%d" of v;  other: "", ""
        .section .fmt,"ax"
hp_fmt: move.l  #0x4650,%d0
        move.l  #0x44DE,%d1
        movea.w #0x3EB,%a0
        bra.s   gen_fmt
bp_fmt: move.l  #0x2710,%d0
        move.l  #0x2656,%d1
        movea.w #0x3ED,%a0
| (this, idx, value, label, valbuf): saved 20 bytes -> ret 20, idx byte 31, value word 34, label 36, val 40
gen_fmt:
        lea     -20(%sp),%sp
        movem.l %d4-%d7/%a5,(%sp)
        move.l  %d0,%d7
        move.l  %d1,%d5
        move.l  %a0,%d4
        movea.l 40(%sp),%a5
        move.b  31(%sp),%d0
        extb.l  %d0
        beq.s   3f
        subq.l  #1,%d0
        beq.s   2f
        pea     S_EMPTY
        move.l  36+4(%sp),-(%sp)
        jsr     STRCPY
        addq.l  #8,%sp
        pea     S_EMPTY
        move.l  %a5,-(%sp)
        jsr     STRCPY
        addq.l  #8,%sp
        bra.s   9f
2:      pea     S_Q
        move.l  36+4(%sp),-(%sp)
        jsr     STRCPY
        addq.l  #8,%sp
        move.w  34(%sp),%d0
        ext.l   %d0
        move.l  %d0,-(%sp)
        pea     S_FMT_D
        bra.s   8f
3:      pea     S_FREQ
        move.l  36+4(%sp),-(%sp)
        jsr     STRCPY
        addq.l  #8,%sp
        move.w  34(%sp),%d6
        ext.l   %d6
        neg.l   %d6
        addi.l  #255,%d6                | 255 - v
        ble.s   7f
        btst    #0,%d6
        beq.s   4f
        move.l  %d5,%d7
        subq.l  #1,%d6
        beq.s   7f
4:      lsr.l   #1,%d6
        moveq   #10,%d1
5:      muls.l  %d4,%d7
        asr.l   %d1,%d7                 | positive: same as stock divs by 0x400
        muls.l  %d4,%d7
        asr.l   %d1,%d7
        subq.l  #1,%d6
        bne.s   5b
7:      move.l  %d7,-(%sp)
        pea     S_FMT_HZ
8:      move.l  %a5,-(%sp)
        jsr     SPRINTF
        lea     12(%sp),%sp
9:      movem.l (%sp),%d4-%d7/%a5
        lea     20(%sp),%sp
        rts


| ===== shared routines: the old BP/Contrary BP formatter body 0x667A8..0x6689B =====
        .section .fmt2,"ax"
| computeFrames(this, blk, mode, q, struct), a1 = descriptor
common_cf:
        lea     -20(%sp),%sp
        movem.l %d2-%d3/%a2-%a4,(%sp)   | ret 20, this 24, blk 28, mode 32, q 36
        movea.l %a1,%a4                 | descriptor survives SETMODE (C code: d0/d1/a0/a1 scratch)
        movea.l 28(%sp),%a0             | blk
        move.l  #NEUTRAL,%d0
        move.l  %d0,(%a0)
        move.l  %d0,W1(%a0)
        move.l  %d0,W4(%a0)
        move.l  %d0,W5(%a0)
        move.l  %d0,W8(%a0)
        move.l  GAINBASE,%d0
        move.l  %d0,36(%a0)             | word 9: gain base, as stock
        move.l  36(%sp),%d1             | q
        move.l  %d1,%d3                 | q survives SETMODE
        bsr.s   apply
        pea     0xC0.w
        move.l  32+4(%sp),-(%sp)        | mode
        move.l  %a0,-(%sp)
        jsr     SETMODE
        lea     12(%sp),%sp
        move.l  %d3,%d1
        movea.l %a4,%a1
        moveq   #0,%d0                  | HP: 0
        bra.s   ret_bp

| packQ(this, blk, q, struct), a1 = descriptor
common_pq:
        lea     -20(%sp),%sp
        movem.l %d2-%d3/%a2-%a4,(%sp)   | ret 20, this 24, blk 28, q 32
        movea.l 28(%sp),%a0
        move.l  32(%sp),%d1
        andi.l  #0xFF,%d1               | q is a byte argument
        bsr.s   apply
        moveq   #1,%d0                  | HP: 1
ret_bp: moveq   #0,%d2
        move.b  12(%a1),%d2             | BP: -(q >> retshift)
        beq.s   1f
        move.l  %d1,%d0
        asr.l   %d2,%d0
        neg.l   %d0
        jsr     bp_boost                | HPBP6: + resonance boost (header pad)
1:      movem.l (%sp),%d2-%d3/%a2-%a4
        lea     20(%sp),%sp
        rts

| constants then table words; a0 = blk, a1 = descriptor, d1 = q. Clobbers d0, d2, a2, a3.
apply:
        moveq   #0,%d2
        move.b  13(%a1),%d2             | nconst
        lea     16(%a1),%a2
1:      subq.l  #1,%d2
        bmi.s   2f
        move.l  (%a2)+,%d0
        movea.w (%a2),%a3               | word offset
        addq.l  #4,%a2
        move.l  %d0,(%a0,%a3.l)
        bra.s   1b
2:      movea.l (%a1),%a2               | table A: (q >> shiftA) & 31
        move.l  %d1,%d0
        moveq   #0,%d2
        move.b  9(%a1),%d2
        asr.l   %d2,%d0
        moveq   #31,%d2
        and.l   %d2,%d0
        move.l  (%a2,%d0.l*4),%d0
        moveq   #0,%d2
        move.b  8(%a1),%d2
        move.l  %d0,(%a0,%d2.l)
        moveq   #0,%d2
        move.b  10(%a1),%d2             | table B? (q >> shiftB) & 7
        cmpi.l  #0xFF,%d2
        beq.s   3f
        movea.l 4(%a1),%a2
        movea.l %d2,%a3
        move.l  %d1,%d0
        move.b  11(%a1),%d2
        asr.l   %d2,%d0
        move.b  14(%a1),%d2             | table B step mask (7 or 15)
        and.l   %d2,%d0
        move.l  (%a2,%d0.l*4),%d0
        move.l  %d0,(%a0,%a3.l)
3:      rts
end_of_fmt2:

| ===== 4th Order Band-pass ladder B table: image header padding (end of it) =====
        .section .hdr2,"a"
bp_ladb: BP_LADB_TABLE
