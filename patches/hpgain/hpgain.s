| High-pass / Contrary Band-pass headroom (EOS 4.71-beta2, notes/filter_survey_beta2.md, recommendation 1).
| The HP2/HP4/Contrary BP models kept word 9 at the base gain at every Q, so at high Q they ran ~10 dB hotter than
| stock and came within 1.5-3 dB of the chip's clip ceiling. Word 9 is the gain E-mu's Master Headroom lowers
| (base = 0x00FE00FE - 4 * Headroom), i.e. it acts before the clipping point. Here it is lowered with Q:
|   word 9 = base - off * 0x00010001,  off = (q * q * K) >> 14,  K = descriptor byte 15
| for descriptors with retshift (byte 12) = 0 (HP2, HP4, Contrary BP; byte 15 was unused there). Band-pass keeps
| byte 15 as its resonance boost and its word 9 untouched.
| Hooks (build_beta2.py): common_cf 0x667CE "move.l GAINBASE,d0; move.l d0,36(a0)" -> jsr hg_cf; nop; nop
|                         common_pq 0x6680C "andi.l #0xFF,d1"                     -> jsr hg_pq
        .equ    GAINBASE, 0x10004D7C

        .section .hpg,"ax"
        .globl  hg_cf, hg_pq
| computeFrames: a0 = blk, a1 = descriptor, q at 36(sp) of the caller (40 here). Clobbers d0, d1.
hg_cf:  move.l  GAINBASE,%d0
        move.l  40(%sp),%d1
        bsr.s   hg_sub
        move.l  %d0,36(%a0)
        rts

| packQ: a0 = blk, a1 = descriptor, d1 = q argument. Returns d1 = q & 0xFF (as the replaced andi). Clobbers d0.
hg_pq:  andi.l  #0xFF,%d1
        moveq   #0,%d0
        move.b  12(%a1),%d0
        bne.s   9f                      | band-pass: word 9 as before (not written by packQ)
        move.b  15(%a1),%d0
        beq.s   9f
        move.l  %d1,-(%sp)
        move.l  GAINBASE,%d0
        bsr.s   hg_sub
        move.l  %d0,36(%a0)
        move.l  (%sp)+,%d1
9:      rts

| d0 = base, d1 = q (clobbered), a1 = descriptor: d0 -= ((q*q*K) >> 14) in both halves when retshift = 0, K != 0.
hg_sub: move.l  %d2,-(%sp)
        moveq   #0,%d2
        move.b  12(%a1),%d2
        bne.s   9f
        move.b  15(%a1),%d2
        beq.s   9f
        muls.l  %d1,%d1
        muls.l  %d2,%d1
        moveq   #14,%d2
        asr.l   %d2,%d1                 | off (0..K)
        move.l  %d1,%d2
        swap    %d2                     | off << 16
        add.l   %d2,%d1
        sub.l   %d1,%d0
9:      move.l  (%sp)+,%d2
        rts
