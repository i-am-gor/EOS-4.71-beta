# Changelog: EOS 4.70 → EOS 4.71-beta

## EOS 4.71-beta2 (in progress)

### Fixed: centre pan leaned slightly right
- In EOS 4.70 and 4.71-beta, a centred pan (0, CC10 64) came out one gain step louder on the right (about
  0.24 dB measured).
- **Cause:** E-mu's pan gain table has 128 entries, so the true centre falls between entries 63 and 64. Pan 0
  reads entry 64 for one side and entry 63 for the other.
- **Fix:** beta2 gives those two entries the same value. Centre is now exactly balanced, and every other pan
  setting is unchanged.

Pan schemes compared (gain steps of about 0.24 dB; L − R = left minus right):

| Setting | EOS 4.70 | EOS 4.71-beta (beta1) | EOS 4.71-beta2 |
|---|---|---|---|
| Hard left | at −32 (CC10 32); −33…−64 do nothing | at −64 (CC10 0) | at −64 (CC10 0) |
| −32 (CC10 32) | hard left | about 16 dB left | about 16 dB left |
| −1 (CC10 63) | 2 steps left-heavy | 1 step left-heavy | **balanced** |
| 0 (CC10 64) | 1 step right-heavy (−0.24 dB) | 1 step right-heavy (−0.24 dB) | **balanced (0 dB)** |
| +32 (CC10 96) | hard right | about 16 dB right | about 16 dB right |
| Hard right | at +32 (CC10 96); +33…+63 do nothing | at +63 (CC10 127) | at +63 (CC10 127) |
| Pan gain table entries 63 / 64 | −322 / −311 | −322 / −311 | −316 / −316 |

Verified in the emulator, running the real pan routine for every pan and level against stock, and on the E4
(Quantum 19/20, preset 000 sine).

| Measured L − R on the E4 | Voice Pan | CC10 |
|---|---|---|
| Centre | 0.00 dB at −1 and 0 (beta1: −0.24 dB at 0) | 0.00 dB at 63 and 64 |
| One step either side | +0.77 dB at −2, −0.79 dB at +1 | −0.78 dB at 65 |

### Renamed: SLpScn → WTScan
- The transwave/wavetable scan cord destination **SLpScn** is now called **WTScan**. Only the name has changed;
  beta1 presets play unchanged.

---

## EOS 4.71-beta

EOS 4.71-beta is an unofficial update of E-mu's EOS 4.70 for the Emulator IV family **Ultra** models
(ColdFire MCF5206e), built by patching the original 4.70 image. It is not made, supported or endorsed by
E-mu Systems / Creative. Header name **EOS 4.71-beta**, image checksum `0887f4e6`.

Everything below was verified in an instruction-level emulator (stock vs patched code paths) and on an
E-mu E4 Ultra with an RFX card, with measurements recorded from its outputs.

## New

### Filters: Oberheim OB-Xa (CEM3320) models
- **2 Pole Lowpass, 4 Pole Lowpass, 6 Pole Lowpass** now model the OB-Xa filters built on the CEM3320:
  the 2-pole is the state-variable filter, the 4-pole the transistor-style ladder, the 6-pole the ladder
  followed by the 2-pole on the same cutoff. Names, menu positions and preset compatibility are unchanged.
- The cutoff now follows the displayed frequency at high resonance (stock drifted up to ~25 % sharp at
  the bottom of the range). Resonance peaks are matched to the stock maxima (about 19 / 39 / 46 dB), so
  E-mu's level compensation still fits and existing presets keep their balance.
- **2nd Order High-pass, 4th Order High-pass, 2nd Order Band-pass, 4th Order Band-pass** use the same
  OB-Xa pole pairs; their cutoff/centre follows the display (stock HP corners sat 25–60 % below it).
  Band-pass levels match stock within ~2 dB at low and medium resonance; the 4th-order band-pass has a
  ~+15 dB resonant peak at full resonance.
- **Contrary Band-pass** keeps its stock character (the zero that moves against the cutoff and the stock
  resonance law) with the centre frequency calibrated to the display.
- Not modelled: analog saturation and self-oscillation (the E4's filter hardware is linear).

### LFO tempo sync
- **LFO 1 and LFO 2 Rate** continue past 18.01 Hz into 16 tempo divisions:
  `4bars, 2bars, 1bar, 1/2., 1/2, 1/4., 1/2T, 1/4, 1/8., 1/4T, 1/8, 1/16., 1/8T, 1/16, 1/16T, 1/32`
  (values 128–143 over MIDI/SysEx).
- The tempo comes from the master clock: the internal sequencer/arpeggiator tempo, or incoming MIDI
  clock when the Clock Source is External (phase-locked to MIDI Start).
- **Sync = Key Sync** restarts the cycle at note-on; **Sync = Free Run** locks all voices to the song grid.
- In sync mode the Rate cords, Variation and LFO trigger are ignored; Shape, Delay and all destinations work.
- Measured accuracy: within ±0.06 % of the MIDI clock at 60–140 BPM; Free Run phase spread 0.2°.

### New LFO shape: "saw down"
- Shape 16, a falling sawtooth (shape 2 "sawtooth" rises).

### Transwave / wavetable scanning: cord destination "SLpScn"
- New cord destination **SLpScn** slides a sample's loop window through the sample while the note plays
  (Ensoniq-style transwave). +100 from a full-scale source moves the loop from frame 1 to the sample end,
  −100 towards the start; the loop always stays inside the sample. See `docs/transwave-guide.md` for how to
  build samples: **at least 2 samples of silence before the first frame** (a loop cannot start
  before sample 2), equal frames, frames × frame size ≤ 32,768.

### MIDI clock: keeps running when the clock stops ("flywheel")
- With Clock Source External, **synced LFOs, the Ck clock modulation sources (CkDwhl … Ck16th), the
  arpeggiator and Beats keep running at the last MIDI tempo when the MIDI clock stops** (DAW stopped),
  instead of freezing. The song sequencer still stops with the DAW.
- On Continue, synced LFOs snap back onto the DAW's grid; MIDI Start resets them to bar 1.
- Short dropouts (missing clocks under 250 ms) are caught up so the LFOs stay on the grid.

## Fixed

### Pan reached hard left/right at half range (EOS 4.70 bug)
- **Voice Pan, Multimode (mixer) Pan, MIDI CC10 and AmpPan cords** now use their full range. In 4.70 the
  pan sum was scaled twice too large, so ±32 (CC10 32/96) was already hard left/right and the outer half of
  every pan control did nothing. Now ±64 (CC10 0/127) is hard, ±32 is about 16 dB between the sides.
- Verified on the main outputs and the sub outputs 1–3. (A 0.25 dB right-heavy centre offset from E-mu's
  pan table remains; fixed in beta2, see above.)
- Test it yourself with the **EOS Pan Test** app and the bank in `testbank/` (see README).

### MIDI clock counted twice
- With Clock Source External, the master clock advanced on the incoming MIDI clock **and** on EOS's own
  internal clock stream, so the sequencer, arpeggiator and Ck sources ran at internal + external tempo
  (60 BPM MIDI clock played like 180 BPM). Only clocks from the MIDI inputs are counted now.

### Clock sources frozen after power-on
- After power-on the master clock rate stayed 0 until the arpeggiator/sequencer tempo was edited, so the
  Ck sources (and anything else on the master clock) did not move. The clock now starts at the arpeggiator
  tempo on the first note.

## Faster
- **Cord processing**: each voice's 10 ms control tick tested all 24 cord slots; it now stops after the last
  cord in use (results identical). On a 64-voice test preset: cord stage −29 %, whole voice tick −6.7 %,
  CPU used by voice control 64 % → 60 %. Confirmed sound-identical by an in-session A/B null test.

## Known limitations
- MIDI Song Position Pointer is not followed by the synced LFOs (Continue resumes from the stop point).
- While the MIDI clock is stopped the flywheel runs within about 0.2 % (LFOs) / 2 % (Ck sources) of the last tempo.
- Ultra models only (as EOS 4.70). Back up your work before flashing; to go back, flash the original 4.70.
