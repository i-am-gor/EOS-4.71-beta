| CPU-load probe for EOS 4.70 (diagnostic build only, on top of Sync8+TW+HPBP6).
| Counters (RAM copy of the vector cave, never read by EOS; garbage at boot -> host resets first):
|   PASSES  main cooperative loop passes (0x321D8 loop: fewer passes = less CPU left for the UI/tasks)
|   TICKS   voice control ticks run (FUN_00060E80)
|   LATEMAX worst voice-tick lateness, ms (now - deadline at voice+0x1E when the tick starts)
|   LATESUM summed lateness, ms
| Readout through SysEx parameter 195 ("Foreign sampler SCSI ID"): set(n) latches var n
| (0 PASSES, 1 TICKS, 2 LATEMAX, 3 LATESUM; 15 = clear LATEMAX), then each get returns the next
| 11 bits of the latched value (lo, mid, hi). Rates are differences over host-timed windows.

        .equ    NOWMS,   0x10000450
        .equ    VARS,    0x10000200
        .equ    PASSES,  VARS + 0
        .equ    TICKS,   VARS + 4
        .equ    LATEMAX, VARS + 8
        .equ    LATESUM, VARS + 12
        .equ    LATCH,   VARS + 16
        .equ    PIECE,   VARS + 20

        .section .vlo,"ax"
        .globl  _start
_start:
| ---- voice tick 0x60E90: replaces move.l NOWMS,d6 (a4 = voice) ----
probe_tick:
        move.l  NOWMS,%d6
        move.l  %d6,%d0
        sub.l   0x1E(%a4),%d0           | lateness, ms
        addq.l  #1,TICKS
        add.l   %d0,LATESUM
        cmp.l   LATEMAX,%d0
        ble.s   1f
        move.l  %d0,LATEMAX
1:      rts

| ---- parameter 195 getter (desc) -> next 11 bits of the latch ----
probe_get:
        move.l  PIECE,%d1
        addq.l  #1,PIECE
        move.l  LATCH,%d0
        mulu.w  #11,%d1
        lsr.l   %d1,%d0
        andi.l  #0x7FF,%d0
        rts
        .section .ext2,"ax"
| ---- main loop 0x321DE: replaces lea $184(a5),a0 ; move.l a0,-(a7) ----
probe_loop:
        movea.l (%sp)+,%a1
        pea     0x184(%a5)
        addq.l  #1,PASSES
        jmp     (%a1)


        .section .vhi,"ax"
| ---- parameter 195 setter (desc, value): 0-3 latch PASSES/TICKS/LATEMAX/LATESUM, 15 clear LATEMAX ----
probe_set:
        move.l  8(%sp),%d0
        clr.l   PIECE
        moveq   #15,%d1
        cmp.l   %d1,%d0
        bne.s   1f
        clr.l   LATEMAX
        rts
1:      moveq   #3,%d1
        and.l   %d1,%d0
        lsl.l   #2,%d0
        lea     VARS,%a0
        move.l  (%a0,%d0.l),%d0
        move.l  %d0,LATCH
        rts
