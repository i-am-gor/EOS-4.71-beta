| Cord destination list: show Lfo2Ck (107) before Lag0in (106). Notes: notes/lfock.md.
| Stored ids do not change. Visit position n maps to id n, except 106 -> 107 and 107 -> 106.
| 0x62C98 (stored id -> display index) counts a limit of 106 as 107 and 107 as 106, then joins
| the stock loop at 0x62CA4. tst.l leaves Z set for the stock bne when the id is 0.
| 0x62D00 takes the display index in d1. 0x62D60 takes it as the stack long (0x14 after the frame).
| Both save d5-d7/a5, clobber d1/a0/a1, and return the id in d0. Index <= 0 or >= 192 returns 0.
| Hooks (build_beta2.py): jmp ord_d1 / ord_stk / ord_rev from 0x62D00 / 0x62D60 / 0x62C98.

        .equ    DEST_TABLE, 0x0006344C
        .equ    REV_JOIN,   0x00062CA4
        .equ    NDEST,      192
        .equ    SENTINEL,   0x1E

        .section .ord,"ax"
        .balign 4
        .globl  ord_d1, ord_stk, ord_rev

ord_d1:
        lea     -16(%sp),%sp
        movem.l %d5-%d7/%a5,(%sp)
        bra.s   body
ord_stk:
        lea     -16(%sp),%sp
        movem.l %d5-%d7/%a5,(%sp)
        move.l  0x14(%sp),%d1
body:
        tst.l   %d1
        ble.s   none
        cmpi.l  #NDEST,%d1
        bge.s   none
        moveq   #0,%d7                  | visit position
1:      move.l  %d7,%d6                 | id
        cmpi.l  #106,%d7
        bne.s   2f
        moveq   #107,%d6
        bra.s   3f
2:      cmpi.l  #107,%d7
        bne.s   3f
        moveq   #106,%d6
3:      move.l  #DEST_TABLE,%a0
        move.l  %d6,%d0
        lsl.l   #3,%d0
        adda.l  %d0,%a0
        moveq   #0,%d0
        move.w  4(%a0),%d0
        cmpi.l  #SENTINEL,%d0
        beq.s   4f
        subq.l  #1,%d1
        bgt.s   4f
        move.l  %d6,%d0
        bra.s   done
4:      addq.l  #1,%d7
        cmpi.l  #NDEST,%d7
        blt.s   1b
none:   moveq   #0,%d0
done:   movem.l (%sp),%d5-%d7/%a5
        lea     16(%sp),%sp
        rts

ord_rev:
        lea     -16(%sp),%sp
        movem.l %d5-%d7/%a5,(%sp)
        move.b  0x17(%sp),%d1
        andi.l  #0xFF,%d1
        cmpi.l  #106,%d1
        bne.s   1f
        moveq   #107,%d1
        bra.s   2f
1:      cmpi.l  #107,%d1
        bne.s   2f
        moveq   #106,%d1
2:      tst.l   %d1
        jmp     REV_JOIN
