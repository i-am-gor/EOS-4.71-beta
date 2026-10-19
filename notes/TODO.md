# Pending

- [x] **CPU flash = 4 Mb** (Hardware Configuration, 2026-10-17). OS growth limited by the loader's
      2 MB RAM buffer (~128 KB), pending the Resident FLASH check below.
- [x] OB-Xa v2 burned via handshaked MIDI File Dump (12,284 packets, 0 NAK) and confirmed running.
- [ ] (old note) **Check CPU flash size on the unit.** On the Hardware Configuration screen (next to SW version,
      Sample RAM, CPU RAM), read `CPU FLASH: _Mb`.
      - 2Mb → the OS can grow by only ~384 bytes (EOS 4.70 ends at 0x1FFE80); additions must reuse
        space inside the image (~10 KB of padding runs ≥64 B, plus dead code/strings).
      - 4Mb+ → growth limited by the loader RAM buffer (~128 KB), pending the item below.
- [ ] Trace where EOS keeps "Resident FLASH" / flash heap data, to rule out a collision just above
      the OS in CPU flash.
- [x] First hardware test: `sysex/EOS470_selfbuilt_test.syx` loaded and burned OK (2026-10-17).
      MIDI File Dump path, our Lz77 encoder and checksum confirmed on hardware.
- [x] OB-Xa v1 tested on hardware: clipped at the top of the range. v2 (truncated pole lines) burned and rescanned: 0 clips in 118 takes (notes/burst_investigation.md).
- [ ] Gain-word units measured (~1 dB/step, notes/filter_format.md); next: add the ladder's 1/(1+k) passband drop to the 4/6-pole.
- [x] Cutoff tracks the display at high resonance (v3b). [ ] v3c: fix low-resonance 4/6-pole brightness (damped-pole calibration).

- [x] OB-Xa v3d on the E4 (2026-10-18): stock brightness at low Q, ladder peaks on the display at high Q,
      0/118 clips. Drive not feasible via the gain word (no saturation, field wraps).
- [ ] Optional: A/B listening set stock vs v3d from the matching Quantum recordings.

- [x] LFO tempo sync verified on hardware (Sync4 test, 2026-10-18); final Sync5 burned and confirmed on hardware (±0.11%, Key Sync 3.5°, Free Run 0.2°). Was: LFO tempo sync built on v3d (`sysex/EOS470_OBXa_v3d_LFOsync.syx`, emulator 49,688 checks / 0 failures, 2026-10-18):
      hardware test pending (notes/lfo_sync.md: internal tempo, external MIDI clock, Key Sync vs Free Run, front-panel Rate display).
