| Slice diagnostic probe (test build "EOS 4.71-b2 SliceProbe"): records the inputs of slice_exit for the last
| note-on and exposes them through SysEx parameter 195 (setter = halfword index 0..7, getter = that halfword).
| The note-on exit hook (0x5FD2C) jumps to probe_in, which records and continues into slice_exit.
| PRB (RAM copy of the unused vectors 92-95, 16 bytes):
|   +0  long  note-on count            (halfwords 0, 1)
|   +4  word  Slice cord sum (voice+0x1C), +6 word mode flag (voice+0x1E)   (halfwords 2, 3)
|   +8  long  note struct +16 (loop start, 8 = one-shot)                      (halfwords 4, 5)
|   +12 long  sample header +0x38 (flags; +0x3A loop byte in the low half)    (halfwords 6, 7)
| Index byte: 0x100003E4 (the LP+Fuzz test switch slot, unused in the release).

        .equ    PRB,       0x10000370
        .equ    IDX,       0x100003E4

        .section .prb,"ax"
probe_in:
        lea     PRB,%a0
        addq.l  #1,(%a0)
        move.l  -0x3E(%a5),%d0
        move.l  %d0,4(%a0)
        move.l  0x10(%a4),%d0
        move.l  %d0,8(%a0)
        movea.l 0x30(%a5),%a1
        move.l  0x38(%a1),%d0
        move.l  %d0,12(%a0)
        jmp     slice_exit

        .section .prbio,"ax"
prb_get:
        moveq   #0,%d0
        move.b  IDX,%d0
        moveq   #7,%d1
        and.l   %d1,%d0
        lea     PRB,%a0
        move.w  (%a0,%d0.l*2),%d0
        ext.l   %d0
        rts
prb_set:
        move.l  8(%sp),%d0
        move.b  %d0,IDX
        rts
