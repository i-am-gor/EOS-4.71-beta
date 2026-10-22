| Sample Edit "Insert Silence" (EOS 4.71-beta2): inserts NSIL = 4 zero frames at the region start (the region end
| is not used). notes/silence_insert.md.
|
| Reuses Paste's insert path: 0xF7464(d0 = N, d1 = pos) opens an N-frame gap in every channel (moves the sample
| arena, fixes the other samples' pointers, shifts loop/end points at or after pos), 0xF7988(d0 = N, d1 = pos)
| zero-fills it. Registered as operation 3 (Paste) without a parameter page: the soft-key handler is Truncate's
| (0xB54B0) with op 3 and page 0; Paste's exec pointer (dispatch entry 0xFB8BE + 36) goes to paste_wrap, which
| runs sil_exec when the page pointer 0x10003EE4 is 0 (Paste always sets it to its page 0xB65AC) and the stock
| Paste exec 0xF79D4 otherwise. The generic exec wrapper 0xFB564 supplies undo ("Paste Section"), voice lock,
| progress and redraw.
|
| Sections (placed by tools/build_beta2.py): .silwrap (paste_wrap), .silx1 / .silx2 / .silx3 (sil_exec, split
| over the reserved exception vectors 48-63, the unused user vectors 116-127 and the reserved vectors 16-23,
| joined by bra.w), .silh (soft-key handler), .silstr (strings).

        .equ    REG_START, 0x10000E14
        .equ    REG_END,   0x10000E18
        .equ    PAGE,      0x10003EE4
        .equ    OPCODE,    0x10003ED8
        .equ    MEMCHK,    0x13E3C8           | (bytes) -> -1 if they do not fit
        .equ    CURSMP,    0x13D2F4           | () -> current sample number
        .equ    SMPLEN,    0x13D578           | (sample) -> length (Paste: last frame = length - 5)
        .equ    OPENGAP,   0xF7464
        .equ    ZEROGAP,   0xF7988
        .equ    PASTE,     0xF79D4
        .equ    ERR_MEM,   0xFC000002
        .equ    NSIL,      4                  | frames inserted

        .section .silwrap,"ax"
| ---- Paste's exec slot: Insert Silence (no parameter page) or the stock Paste ----
paste_wrap:
        tst.l   PAGE
        beq.s   1f
        jmp     PASTE
1:      jmp     sil_exec

        .section .silx1,"ax"
| ---- sil_exec: insert NSIL zero frames at the region start; d0 = 0 or ERR_MEM ----
sil_exec:
        move.l  %d7,-(%sp)
        move.l  %d6,-(%sp)
        moveq   #NSIL,%d7                    | N
        move.l  %d7,%d0
        lsl.l   #2,%d0
        addq.l  #8,%d0
        addq.l  #8,%d0                       | bytes, stereo worst case
        move.l  %d0,-(%sp)
        jsr     MEMCHK
        addq.l  #4,%sp
        addq.l  #1,%d0
        bne.w   1f
        move.l  #ERR_MEM,%d0
        bra.w   9f

        .section .silx2,"ax"
1:      jsr     CURSMP
        move.l  %d0,-(%sp)
        jsr     SMPLEN
        addq.l  #4,%sp
        subq.l  #5,%d0                       | last frame
        move.l  REG_START,%d6                | pos
        cmp.l   %d0,%d6
        bne.s   2f
        addq.l  #1,%d6                       | at the last frame: append (as Paste)
2:      move.l  %d6,%d1
        move.l  %d7,%d0
        jsr     OPENGAP
        bra.w   3f

        .section .silx3,"ax"
3:      move.l  %d6,%d1
        move.l  %d7,%d0
        jsr     ZEROGAP
8:      moveq   #0,%d0
9:      move.l  (%sp)+,%d6
        move.l  (%sp)+,%d7
        rts

        .section .silh,"ax"
| ---- soft-key handler (Truncate's 0xB54B0 with operation 3 and no parameter page) ----
sil_key:
        jsr     0x26138
        moveq   #3,%d0
        move.l  %d0,OPCODE
        clr.l   PAGE
        pea     0xB530C
        jsr     0xAE9F8
        addq.l  #4,%sp
        tst.b   %d0
        beq.s   9f
        clr.l   -(%sp)
        pea     0xB32E0
        jsr     CURSMP
        move.l  %d0,-(%sp)
        pea     3.w
        jsr     0xFB6F8
        lea     16(%sp),%sp
9:      rts

        .section .silstr,"a"
sil_name:  .asciz  "Insert Silence"
sil_short: .asciz  "Silnc"
