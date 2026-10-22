| Compact replacement for the plugin port-map builders 0x15EF5C (A, 15 rows) and 0x15F3E0 (B, 14 rows).
| Stock: per row, push 16 values (first, first+2, ... count of them, then -1), idx, a4, a5 and bsr 0x15D50C
| (this, a4, idx, v1..v16); the stack is popped once at the end. Here each row is 3 table bytes and the stack
| is popped after every call (the callee reads only its 19 arguments). d0 = the last call's result, as stock.
| A stays at 0x15EF5C; the member-pointer longword 0x15FAD4 is repointed to pm_B. Frees ~2 KB after pm_end.
        .equ PORTSET, 0x15D50C
        .section .pm,"ax"
        .globl pm_A, pm_B, pm_end
pm_A:   lea     tabA(%pc),%a0
        moveq   #14,%d0
        bra.s   pm_C
pm_B:   lea     tabB(%pc),%a0
        moveq   #13,%d0
pm_C:   lea     -20(%sp),%sp
        movem.l %d6-%d7/%a3-%a5,(%sp)
        movea.l 24(%sp),%a5
        movea.l 28(%sp),%a4
        movea.l %a0,%a3
        move.l  %d0,%d7
        moveq   #-1,%d6
1:      moveq   #0,%d1
        move.b  2(%a3),%d1              | count
        moveq   #16,%d0
        sub.l   %d1,%d0                 | -1 padding
        beq.s   3f
2:      move.l  %d6,-(%sp)
        subq.l  #1,%d0
        bne.s   2b
3:      moveq   #0,%d0
        move.b  1(%a3),%d0
        add.l   %d1,%d0
        add.l   %d1,%d0                 | first + 2*count
4:      subq.l  #2,%d0
        move.l  %d0,-(%sp)
        subq.l  #1,%d1
        bne.s   4b
        moveq   #0,%d0
        move.b  (%a3),%d0
        move.l  %d0,-(%sp)              | idx
        addq.l  #3,%a3
        move.l  %a4,-(%sp)
        move.l  %a5,-(%sp)
        jsr     PORTSET
        lea     76(%sp),%sp
        subq.l  #1,%d7
        bpl.s   1b
        movem.l (%sp),%d6-%d7/%a3-%a5
        lea     20(%sp),%sp
        rts
        .include "rows.inc"
        .even
pm_end:
