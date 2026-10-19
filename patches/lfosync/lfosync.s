| LFO tempo sync for EOS 4.70 (LFO 1 and LFO 2, every voice).
| Code at 0x20400 (the unused interrupt vectors 128-255 of the image: zero in 4.70, copied to the
| RAM vector table at boot, never taken) and in .ext at 0x68BF0 (dormant filter method tables).
|
| LFO Rate gets 16 values past 127 (128..143 = 4 bars .. 1/32). With one of those the LFO phase is
| computed from a clock instead of accumulating at a fixed rate:
|  * MIDI clock (any F8 within the last 250 ms): our own count of F8s received on the physical MIDI
|    ports (parser port structs 0/1; the other structs carry an internal clock stream), timestamped by
|    the hook on the F8 path, interpolated inside the current clock from the smoothed clock period.
|    Clock stopped (no F8 for 250 ms) with Clock Source = External: the LFOs run on at the last
|    period (flywheel); when the clock resumes the count catches up, MIDI Start resets it.
|      phase = (E mod K*256) * 256 / K,  E = clocks*256 + fraction, K = MIDI clocks per cycle
|    Free Run: clocks since MIDI Start.  Key Sync: clocks since note-on (count saved at +0x1A).
|    (EOS's own master tick is not used here: with MIDI clock arriving it ran at internal + external.)
|  * otherwise the internal master tick 0x10000428 (sequencer/arp tempo):
|      phase = ((T - T0) mod P) * 65536 / P,  P = K * ticks-per-MIDI-clock
|    T0 = note-on tick (voice+0x2E) for Key Sync, 0 for Free Run. A master clock that was never
|    started since boot is started at the arp tempo on the first synced note-on.
| Rates 0..127 run the stock code unchanged. In sync mode Rate cords, Variation and the LFO trigger
| are ignored.
|
| Runtime marker: LFO struct word +0x10 (base rate, stock 0..127) = 0x8000 | flags | division
|   bit 13 = key sync, bit 14 = LFO 2 (struct at voice+0x1A8, else voice+0x188)

        .equ    TICK,      0x10000428       | master tick counter (PPQ/24 per MIDI clock)
        .equ    TPC,       0x10000420       | word: ticks per MIDI clock
        .equ    NOWMS,     0x10000450       | ms timer
        .equ    CLKRATE,   0x10000434       | master ticks per second; 0 until a tempo has been set
        .equ    CLKMODE,   0x1000042C       | master clock source: 1 = external (MIDI clock)
        .equ    ARPTEMPO,  0x1000719C       | arpeggiator tempo (BPM, default 120)
        .equ    SETTEMPO,  0x00193F88       | stock arp tempo setter: tempo -> master clock
        .equ    STRCPY,    0x001A6C4C
        .equ    RATEFMT,   0x0006A880       | stock LFO rate formatter ("%2d.%02d")
        .equ    TICK_RET,  0x00061BFA       | stock tick after the two replaced instructions
        .equ    TICK_WAVE, 0x00061C52       | stock tick: waveform lookup / S&H, outputs, noise
        .equ    LFO2_RET,  0x00061CF0       | return address of the LFO 2 init call (FUN_00061CDC)
        .equ    START_STK, 0x00136B10       | stock MIDI Start handler (called from the realtime parser)
        .equ    NDIV,      16
        .equ    VOICE_LFO1, 0x188
        .equ    NOTE_TICK, 0x2E             | voice: tick at note-on (clock sources' start)
        | patch RAM: RAM vector slots 252-254 (never taken, never written by EOS)
        .equ    CNT,       0x100003F0       | MIDI clocks received (reset by MIDI Start)
        .equ    LASTMS,    0x100003F4       | ms timer at the last MIDI clock
        .equ    PER,       0x100003F8       | smoothed MIDI clock period, ms * 256
        .equ    ACC,       0x100003FC       | master clock flywheel fraction (16.16), RAM vector slot 255
        .equ    PORT0,     0x102C94EA       | MIDI port structs, 0x256 apart (5 of them)
        .equ    PORTSZ,    0x256
        .equ    EXT_MS,    250              | MIDI clock counts as present for this long
        .equ    STOCK_CLK, 0x000216C0       | stock MIDI clock handler (master tick), now called only for
                                            | F8s from the physical ports (its jsr at 0x135F24 is NOPed)
        .equ    SAWDOWN,   16               | new LFO shape: falling sawtooth
        .equ    SAWTAB,    0x0006CB6E       | stock sawtooth table (shape 2, rising), read backwards
        .equ    REVERSE,   0x80000000       | wave pointer bit 31: read the table backwards
        | SLoop transwave scan (cord destination SLpScn 58)
        .equ    P_ACC,     -0x3E            | pitch struct (voice+0x5A) -> voice+0x1C: SLpScn sum

        .text
        .globl  _start
_start:

| ---- hook at 0x61BF4 (replaces moveq #0,d6 ; move.w 0x10(a5),d0) ----
| a5 = LFO struct, d5 = elapsed control ticks, a1 = &random seed, saved-register frame on the stack
lfo_tick:
        move.w  0x10(%a5),%d0
        bmi.s   1f
        moveq   #0,%d6
        jmp     TICK_RET
1:      lea     -16(%sp),%sp
        movem.l %d2-%d4/%a2,(%sp)
        move.l  %d0,%d7                 | flags
        moveq   #0,%d6
        move.w  0x12(%a5),%d6           | old phase (stock S&H compares against it)
        moveq   #15,%d0
        and.l   %d7,%d0
        lea     ktab(%pc),%a2
        moveq   #0,%d4
        move.w  (%a2,%d0.l*2),%d4       | K = MIDI clocks per cycle
        move.l  NOWMS,%d2
        sub.l   LASTMS,%d2              | ms since the last MIDI clock
        cmpi.l  #EXT_MS,%d2
        bcs.s   24f
        moveq   #1,%d0                  | clock gone: keep running at the last tempo only while
        cmp.l   CLKMODE,%d0             | Clock Source = External, else the internal master tick
        bne.s   20f
24:     move.l  PER,%d0
        beq.s   20f                     | no clock period measured yet
        bsr.w   flyfrac                 | d2 = clocks since the last F8, 1/256 (may exceed 256)
22:     move.l  CNT,%d1
        btst    #13,%d7
        beq.s   23f
        moveq   #0,%d0
        move.w  0x1A(%a5),%d0
        sub.l   %d0,%d1                 | key sync: clocks since note-on (16 bits)
        andi.l  #0xFFFF,%d1
23:     lsl.l   #8,%d1
        add.l   %d2,%d1                 | E
        move.l  %d4,%d0
        lsl.l   #8,%d0                  | K * 256
        remu.l  %d0,%d3:%d1
        lsl.l   #8,%d3
        divu.l  %d4,%d3                 | phase
        bra.s   10f
        | ---- internal master tick ----
20:     move.l  TICK,%d1
        moveq   #0,%d0
        move.w  TPC,%d0
        mulu.w  %d0,%d4                 | period in ticks
        btst    #13,%d7
        beq.s   7f
        lea     -VOICE_LFO1(%a5),%a2
        btst    #14,%d7
        beq.s   8f
        lea     -0x20(%a2),%a2
8:      sub.l   NOTE_TICK(%a2),%d1
7:      tst.l   %d4
        beq.s   9f
        remu.l  %d4,%d3:%d1             | d3 = (T - T0) mod P
        swap    %d3
        clr.w   %d3
        divu.l  %d4,%d3                 | phase 0..65535
        bra.s   10f
9:      moveq   #0,%d3
10:     move.w  %d3,0x12(%a5)
        move.w  2(%a5),%d7              | S&H holds its value between steps
        ext.l   %d7
        movem.l (%sp),%d2-%d4/%a2
        lea     16(%sp),%sp
        jmp     TICK_WAVE

| ---- hook at 0x61B9C (end of LFO init FUN_00061A50; replaces clr.w 0x18(a5) ; clr.w 0x1a(a5)) ----
| a5 = LFO struct, a3 = preset LFO params (rate, shape, delay, variation, sync)
lfo_init:
        clr.w   0x18(%a5)
        clr.w   0x1A(%a5)
        moveq   #0,%d1
        move.b  1(%a3),%d1
        moveq   #SAWDOWN,%d0
        cmp.l   %d0,%d1
        bne.s   7f
        move.l  #SAWTAB+REVERSE,%d0     | shape 16: the rising saw table, reversed
        move.l  %d0,0x14(%a5)
7:      tst.l   CLKRATE                 | master clock never started since boot (stock bug: Ck sources,
        bne.s   6f                      | arp, Beats frozen): start it at the arp tempo on any note-on
        move.l  ARPTEMPO,-(%sp)
        jsr     SETTEMPO
        addq.l  #4,%sp
6:      moveq   #0,%d0
        move.b  (%a3),%d0
        bpl.s   1f                      | rates 0..127: stock
        moveq   #15,%d1
        and.l   %d1,%d0                 | division 0..15
2:      ori.l   #0x8000,%d0
        tst.b   4(%a3)
        bne.s   3f
        ori.l   #0x2000,%d0             | Sync = Key Sync
3:      move.l  0x18(%sp),%d1           | return address: LFO 1 or LFO 2
        cmpi.l  #LFO2_RET,%d1
        bne.s   4f
        ori.l   #0x4000,%d0
4:      move.w  %d0,0x10(%a5)
        move.w  CNT+2,%d0
        move.w  %d0,0x1A(%a5)           | MIDI clock count at note-on (trigger history unused here)
1:      movem.l (%sp),%d5-%d7/%a3-%a5
        lea     0x18(%sp),%sp
        rts

| MIDI clocks (24 per quarter) per LFO cycle, slowest first
| ---- F8 hook: 0x135F1E jsr 0x136B0C (an empty stub) -> midi_clk ----
midi_clk:
        move.l  %a5,%d0                 | a5 = port struct of the parser
        subi.l  #PORT0,%d0
        move.l  #PORTSZ,%d1
        divu.l  %d1,%d0
        moveq   #2,%d1                  | physical MIDI ports only (structs 0 and 1); EOS feeds an
        cmp.l   %d1,%d0                 | internal clock stream through the others
        bcc.s   1f                      | internal stream: no LFO count, no master tick
        jmp     midi_clk2
1:      rts

| ---- hook at 0x61C84 (jsr; replaces moveq #0,d0 ; move.w 0x12(a5),d0 ; asr.l #8,d0) ----
| a0 = wave table; out d0 = table index (phase >> 8), reversed for a flagged table
lfo_look:
        moveq   #0,%d0
        move.w  0x12(%a5),%d0
        asr.l   #8,%d0
        move.l  %a0,%d1
        bpl.s   1f
        bclr    #31,%d1
        movea.l %d1,%a0
        eori.l  #0xFF,%d0
1:      rts

| ---- flyfrac: d2 = ms since the last MIDI clock, d0 = smoothed period (ms*256, nonzero) ->
| d2 = elapsed clocks * 256 (flywheel): x = dt/period clocks; x <= 1: x; 1 < x <= 2: 1 (a late clock
| holds, as before); x > 2: x - 1 (clock stopped: run on at the last tempo, continuous). Clobbers d1.
flyfrac:
        lsl.l   #8,%d2                  | dt * 256
        cmp.l   %d0,%d2
        bhi.s   1f
        lsl.l   #8,%d2
        divu.l  %d0,%d2
        rts
1:      sub.l   %d0,%d2
        cmp.l   %d0,%d2
        bhi.s   2f
        moveq   #1,%d2
        lsl.l   #8,%d2
        rts
2:      remu.l  %d0,%d1:%d2             | d1 = y mod period (ColdFire remu keeps the dividend)
        divu.l  %d0,%d2                 | d2 = y / period
        lsl.l   #8,%d2
        lsl.l   #8,%d1
        divu.l  %d0,%d1
        add.l   %d1,%d2
        rts

ktab:   .word   384, 192, 96, 72, 48, 36, 32, 24, 18, 16, 12, 9, 8, 6, 4, 3
sawname: .asciz "saw down"
        .balign 2
end_of_patch:

        .section .ext,"ax"
| ---- Rate formatter (value, buf): 0..127 stock, 128.. division names ----
lfo_fmt:
        move.l  4(%sp),%d0
        moveq   #-128,%d1
        add.l   %d1,%d0
        bmi.s   1f                      | field max is 143
        mulu.w  #6,%d0
        lea     names,%a0
        adda.l  %d0,%a0
        move.l  %a0,-(%sp)
        move.l  12(%sp),-(%sp)
        jsr     STRCPY
        addq.l  #8,%sp
        rts
1:      jmp     RATEFMT

| ---- names (6 bytes each) ----
names:  .ascii  "4bars\0" "2bars\0" "1bar\0\0" "1/2.\0\0" "1/2\0\0\0" "1/4.\0\0" "1/2T\0\0" "1/4\0\0\0"
        .ascii  "1/8.\0\0" "1/4T\0\0" "1/8\0\0\0" "1/16.\0" "1/8T\0\0" "1/16\0\0" "1/16T\0" "1/32\0\0"
end_of_ext:

| ---- 8 spare bytes at the end of the OB-Xa region (0x660B0) ----
| ===== master clock flywheel: unused interrupt vectors 96-127 (0x20380-0x203FF, all the "Gen Trap"
| default handler; no code reads the RAM vector table outside the startup copy) =====
        .section .vec,"ax"
| ---- hook at 0x21732 in FUN_0002172C (1 ms): replaces tst.l $10(a0) ; bne.b $2179c ----
| a0 = 0x1000041C (clock block). Internal clock: back to the stock code (a0 kept). External (MIDI)
| clock: stock does nothing here; when the MIDI clock is more than 2 periods late (stopped), advance the
| master tick at the last smoothed period (ticks per ms = TPC * 256 / PER, 16.16 accumulator), so the
| Ck sources, arpeggiator, Beats and timer events keep running. The song tick (sequencer) is untouched.
mclk_hook:
        tst.l   0x10(%a0)               | 0x1000042C: 1 = external
        bne.s   1f
        rts                             | internal: continue at 0x21738
1:      addq.l  #4,%sp                  | external: return straight to FUN_0002172C's caller
        move.l  PER-0x1000041C(%a0),%d1
        beq.s   9f                      | no MIDI clock measured yet
        move.l  NOWMS-0x1000041C(%a0),%d0
        sub.l   LASTMS-0x1000041C(%a0),%d0
        lsl.l   #8,%d0                  | ms since the last clock * 256
        movea.l %d1,%a1
        add.l   %d1,%d1
        cmp.l   %d1,%d0
        bls.s   8f                      | clock present (or one late clock): stock
        moveq   #0,%d0
        move.w  TPC-0x1000041C(%a0),%d0
        swap    %d0
        lsl.l   #8,%d0                  | TPC << 24
        move.l  %a1,%d1
        divu.l  %d1,%d0                 | ticks per ms, 16.16
        add.l   ACC-0x1000041C(%a0),%d0
        move.l  %d0,%d1
        clr.w   %d1
        swap    %d1                     | whole ticks
        add.l   %d1,TICK-0x1000041C(%a0)
        swap    %d1
        sub.l   %d1,%d0                 | fraction
        move.l  %d0,ACC-0x1000041C(%a0)
9:      rts
8:      clr.l   ACC-0x1000041C(%a0)
        rts

        .section .obx,"a"
| Sync formatter table (the stock one at 0x10003374 doubles as shape name 16 now)
synctab: .long  0x0006C620, 0x0006C62C   | "key sync", "free run"

        .section .hdr,"ax"
| ===== code in the image header padding 0x20080-0x201FF =====


| ---- sl_shift: replaces the loop-shift expression at 0x5FBA6 (note-on) and 0x5FECA (every tick).
| a5 = pitch struct (voice+0x5A). Out d7 = loop shift in samples. Keeps all registers but d0/d1/d7.
| stock: (SLoop sum >> 5) + base. With a nonzero SLpScn sum (voice+0x1C) on a forward-looped sample:
| + sum * R / 4032, R = room to the sample end (sum > 0) or start (sum < 0): positive full scale =
| sample end, negative = start; total clamped inside the sample and to +/-32767 (16-bit shift word).
sl_shift:
        move.w  0x1C(%a5),%d7
        ext.l   %d7
        move.w  0x0A(%a5),%d1
        ext.l   %d1
        asr.l   #5,%d1
        add.l   %d1,%d7                 | stock shift
        move.w  P_ACC(%a5),%d0
        ext.l   %d0
        beq.w   9f
        lea     -24(%sp),%sp
        movem.l %d2-%d6/%a0,(%sp)
        movea.l 0x30(%a5),%a0           | sample header
        moveq   #0,%d1
        move.b  0x3A(%a0),%d1
        lsr.l   #6,%d1
        subq.l  #1,%d1
        moveq   #1,%d2
        cmp.l   %d2,%d1                 | loop type 1 or 2 only
        bhi.w   8f
        move.l  0x2C(%a0),%d2
        sub.l   0x24(%a0),%d2
        asr.l   #1,%d2                  | L = loop length
        ble.w   8f
        move.l  0x14(%a0),%d3
        sub.l   0x24(%a0),%d3
        asr.l   #1,%d3                  | lowest shift (sample start), <= 0
        move.l  0x1C(%a0),%d4
        sub.l   0x2C(%a0),%d4
        asr.l   #1,%d4
        addq.l  #1,%d4                  | highest shift: sample end is the last sample (inclusive),
                                        | loop end is one past the loop
        move.l  %d4,%d1                 | R = room in the direction of the sum
        tst.l   %d0
        bpl.s   1f
        move.l  %d3,%d1
        neg.l   %d1
1:      move.l  #4032,%d5               | full scale = 7-bit controller at 127 through a +100 cord
                                        | ((127 << 5) x (127 << 5) >> 12): CC 127 = sample end
        | scan: shift += sum * R / 4032 (split R = q*4032 + r against overflow)
        remu.l  %d5,%d6:%d1             | d6 = R mod 4032
        divu.l  %d5,%d1                 | d1 = R / 4032
        muls.l  %d0,%d1
        muls.l  %d0,%d6
        divs.l  %d5,%d6
        add.l   %d6,%d1
        add.l   %d1,%d7
        cmp.l   %d3,%d7                 | clamp inside the sample
        bge.s   5f
        move.l  %d3,%d7
5:      cmp.l   %d4,%d7
        ble.s   6f
        move.l  %d4,%d7
6:      move.l  #32767,%d1              | and to the 16-bit shift word
        cmp.l   %d1,%d7
        ble.s   7f
        move.l  %d1,%d7
7:      neg.l   %d1
        cmp.l   %d1,%d7
        bge.s   8f
        move.l  %d1,%d7
8:      movem.l (%sp),%d2-%d6/%a0
        lea     24(%sp),%sp
9:      rts

name_scn: .asciz "SLpScn"
        .balign 2

| ---- FA hook: 0x135F2C jsr 0x136B10 -> midi_start ----
midi_start:
        clr.l   CNT
        jmp     START_STK

| ---- F8 hook, second half (after the port filter in .text) ----
| CNT += 1, or round(dt / period) after dropped clocks (gap < 250 ms: the sender kept playing), so
| the LFOs stay on the sender's grid. After a stop (gap >= 250 ms) the sender's song position did not move:
| the count continues from the stop and the flywheeling LFOs snap back onto the sender's grid.
midi_clk2:
        move.l  NOWMS,%d0
        move.l  %d0,%d1
        sub.l   LASTMS,%d1              | ms since the previous clock
        move.l  %d0,LASTMS
        movea.l %d1,%a1
        moveq   #1,%d0
        cmpi.l  #EXT_MS,%d1
        bcc.s   2f                      | a stop: no catch-up
        move.l  PER,%d1
        beq.s   2f
        movea.l %d1,%a0
        move.l  %a1,%d0
        lsl.l   #8,%d0                  | dt * 256 (dt < 250)
        lsr.l   #1,%d1
        add.l   %d1,%d0
        move.l  %a0,%d1
        divu.l  %d1,%d0                 | clocks elapsed = round(dt / period)
        moveq   #2,%d1
        cmp.l   %d1,%d0
        bhi.s   2f                      | >= 2.5 periods: clocks were dropped
        moveq   #1,%d0                  | else one clock (a late or early one is jitter)
2:      add.l   %d0,CNT
        move.l  %a1,%d1
        cmpi.l  #200,%d1                | first clock after a gap: keep the old period
        bhi.s   4f
        lsl.l   #8,%d1
        move.l  PER,%d0
        beq.s   3f                      | first period: take it as is
        sub.l   %d0,%d1
        asr.l   #3,%d1
        add.l   %d0,%d1                 | period += (dt - period) / 8
3:      move.l  %d1,PER
4:      jmp     STOCK_CLK               | master tick (sequencer, arp, Ck sources) from real clocks only
end_of_hdr:
