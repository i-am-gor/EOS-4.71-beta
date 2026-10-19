# OB-Xa CEM3320 lowpass family (2 / 4 / 6-pole) — option B

Test SysEx: `sysex/EOS470_OBXa_LP_test.syx` (header name "EOS 4.70 OB-Xa LP test").
Status: built and verified in emulation; not yet run on hardware.

## Analog references (electricdruid.net/cem3320-filter-designs; copies in `../ref/img/`)
**2-pole (`obxa2.png`)**: state-variable filter. Stage 1 = summer (no cap); stages 2, 3 = integrators
(300p, 100K input, no local feedback). LP→summer 91K; BP→Res VCA→summer for resonance; fixed
damping trim (500K + 300K); 1N4148 limiter into stage 2.
`H2 = kL / ((s/ωs)² + d·s/ωs + kL)`, kL = 100K/91K; resonance lowers d linearly (VCA).

**4-pole (`obxa4.png`)**: datasheet ladder. Each stage 91K in, 100K feedback, 300p, 82K bias.
Res VCA from stage 4 (15µF, 51K) into stage 1.
`H4 = G⁴ / ((1 + s/ωs)⁴ + k)`, G = 100K/91K; k = 4 oscillates.
Pole pairs: A = ωs(−1 + c/√2 ± j c/√2) (resonant), B = ωs(−1 − c/√2 ± j c/√2) (damped), c = k^¼.

**How they line up**: same chip, same 300p/100K, so one CV gives one ωs. The ladder peaks at ωs; the
SVF's natural frequency is √kL·ωs = 1.048·ωs. **6-pole = 4-pole ladder → 2-pole SVF on the same ωs.**

## Resonance laws (peak-matched to stock maxima so E-mu's gain compensation still fits)
| filter | law | max | peak at max res (model) stock → OB-Xa |
|---|---|---|---|
| 2-pole | d linear in q, Q 0.707 → 10 | Q = 10 | ~19 dB → ~19.5 dB |
| 4-pole | k = 3.971·q/127 | just below oscillation | ~38.6 dB → ~38.6 dB |
| 6-pole | ladder k + SVF Q at the same step, capped at step 30/32 | | ~47 dB → ~46 dB |

Not reproduced (linear hardware): OTA tanh, the 2-pole diode limiter, self-oscillation, and the ladder's
1/(1+k) passband drop (needs the gain-word units). At the lowest cutoffs with zero resonance the
4/6-pole sit slightly high, because the E4's angle byte cannot go below ~92 Hz.

## Implementation (`patches/obxa/obxa_lp.s`, `tools/build_obxa.py`)
- New code + SVF/LADA tables (32 steps, index q>>2) replace 0x65E18–0x660BF
  (FUN_00065E18 and the stock LP2/LP4/LP6 methods): 664 / 680 bytes; rest filled with NOP.
- LADB (damped pair, nearly constant) is 16 steps in the old RES16 slot 0x6875C.
- Vtables 0x68878 / 0x688A4 / 0x688D0 slots type/getName/computeFrames/packQ repointed.
- Unchanged by design: FUN_0010D3B0(blk, mode, 0x40), words 1/5 neutral, gain word 9 and return values
  from E-mu's gain tables (0x6871C / 0x6879C), same type IDs and names.
- Build checks: original vtable targets, no outside references into the region, stock RES16 present.

## Verification
- `tools/emu_obxa.py`: stock vs patched methods run in Unicorn through each image's vtables;
  1158 calls (type, name, computeFrames q 0..255, packQ q 0..127 × 3 filters): 0 differences in
  return values, gain word, words 1/5, untouched words and SETMODE arguments; pole words equal the
  model. Negative control (stock vs stock) correctly fails.
- `tools/eos_midi.py check`: SysEx reassembles to the exact patched image; checksum 0x08864B42.
- Response plots: `notes/obxa_fit.png` (solid E4 fit, dashed analog, dotted stock).
