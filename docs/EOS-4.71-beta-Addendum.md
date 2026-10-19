# EOS 4.71-beta Operation Manual Addendum

This is the Operation Manual Addendum for **EOS version 4.71-beta**, an unofficial update of E-mu's
EOS 4.70 for the **E4 Ultra** family of synthesizer/samplers. This revision includes Oberheim OB-Xa
filter models, tempo-synced LFOs, transwave scanning of sample loops, a MIDI clock that keeps running
when your sequencer stops, and a fix for the pan controls.

Read this addendum together with the EOS 4.7 Operation Manual and the EOS 4.7 Operation Manual Addendum.
Everything not mentioned here works as described there.

> **Note:** EOS 4.71-beta is not made, supported or endorsed by E-mu Systems or Creative Technology.
> It is a beta: back up your banks before installing it. You can return to EOS 4.70 at any time.

---

## To Install EOS version 4.71-beta

EOS 4.71-beta is built on your computer from E-mu's own EOS 4.70 update file (**EOS470.EXE**) and
sent to the E4 over MIDI. No floppy disk is needed.

You need:

- E-mu's **EOS470.EXE** (the EOS 4.70 update file).
- A MIDI interface connected **both ways**: computer MIDI Out → E4 MIDI In, and E4 MIDI Out →
  computer MIDI In. The E4 answers every packet during the transfer.
- The **EOS Flasher** application (macOS or Windows).

**To build and send EOS 4.71-beta:**

1. Start **EOS Flasher** and press **Choose EOS470.EXE…**. Select the file. The flasher confirms
   "original E-mu EOS v4.70 found and verified".
2. Select **EOS 4.71-beta** and press **Build**. (Optionally press **Save .syx…** to keep a copy.)
3. Select the MIDI **Output to E4** and the MIDI **Input from E4**.
4. Press **Send to E4**.
5. Turn the E4 on while holding the **Enter** button. When the display asks
   **"Download OS from MIDI?"**, press **Yes**. The display shows "Searching for OS…" and the transfer
   starts; the flasher shows its progress (about 9 minutes).
6. When the transfer is complete the E4 checks the new software and asks **"Burn to flash?"**.
   Press **Yes**. Do not turn the E4 off while it writes to flash.
7. The E4 restarts. The startup screen shows **EOS 4.71-beta**.

**To return to EOS 4.70:** repeat the procedure and select **Original EOS 4.70** in step 2.

> **Note:** If the flasher reports "header not acknowledged", check that the E4's MIDI Out is connected
> to the selected MIDI input and that the E4 is showing "Searching for OS…".

---

## Filters: OB-Xa Models

The lowpass, highpass and bandpass filter types below now model the filters of the Oberheim OB-Xa,
which are built on the Curtis CEM3320 filter chip. Filter type names and numbers are unchanged, so
existing presets load as before and use the new models.

| Filter type | 4.71-beta model |
|---|---|
| 2 Pole Lowpass | OB-Xa 2-pole state-variable lowpass (12 dB/oct) |
| 4 Pole Lowpass | OB-Xa 4-pole ladder lowpass (24 dB/oct) |
| 6 Pole Lowpass | 4-pole ladder followed by the 2-pole, same cutoff (36 dB/oct) |
| 2nd Order High-pass | OB-Xa 2-pole response as highpass |
| 4th Order High-pass | OB-Xa 4-pole response as highpass |
| 2nd Order Band-pass | OB-Xa state-variable bandpass |
| 4th Order Band-pass | OB-Xa 4-pole bandpass |
| Contrary Band-pass | E-mu's contrary bandpass with the cutoff calibrated to the display |

- **Frequency:** the cutoff (or centre) frequency now follows the frequency shown on the display,
  also at high Q. In EOS 4.70 the lowpass peak drifted up to 25 % sharp at low frequencies and the
  highpass corner sat 25–60 % below the display.
- **Q:** resonance rises the way the OB-Xa's does. Maximum resonance is matched to EOS 4.70
  (about 19 dB for 2-pole, 39 dB for 4-pole and 46 dB for 6-pole), so preset levels stay balanced.
- The 4th Order Band-pass has a resonant peak of about +15 dB at maximum Q.

> **Note:** The E4's filter hardware is linear, so the OB-Xa's saturation and self-oscillation are not
> reproduced.

---

## LFO Tempo Sync

LFO 1 and LFO 2 can run in time with the master clock: the sequencer/arpeggiator tempo, or incoming
MIDI clock.

**To sync an LFO to tempo:**

1. Edit the voice and go to the **LFO** page.
2. Turn the **Rate** field past its fastest free-running value (**18.01 Hz**). The display now shows a
   note value instead of hertz (see the table below).
3. Set **Sync** to **Key Sync** or **Free Run**.

| Rate display | Cycle length | MIDI clocks per cycle |
|---|---|---|
| 4bars | 4 bars | 384 |
| 2bars | 2 bars | 192 |
| 1bar | 1 bar | 96 |
| 1/2. | dotted half note | 72 |
| 1/2 | half note | 48 |
| 1/4. | dotted quarter note | 36 |
| 1/2T | half-note triplet | 32 |
| 1/4 | quarter note | 24 |
| 1/8. | dotted eighth note | 18 |
| 1/4T | quarter-note triplet | 16 |
| 1/8 | eighth note | 12 |
| 1/16. | dotted sixteenth note | 9 |
| 1/8T | eighth-note triplet | 8 |
| 1/16 | sixteenth note | 6 |
| 1/16T | sixteenth-note triplet | 4 |
| 1/32 | thirty-second note | 3 |

**Sync settings**

- **Key Sync:** each note starts its LFO at the beginning of the cycle.
- **Free Run:** all voices run in phase with the song; the cycle is locked to bar 1 (MIDI Start).

**Notes**

- The tempo follows the master clock. To follow your sequencer, set the Master **Clock Source** to
  **External** and send MIDI clock to the E4.
- While an LFO is synced, the Rate cords (Lfo1Rt / Lfo2Rt), **Variation** and the LFO trigger are
  ignored. **Shape**, **Delay** and all LFO destinations work as usual.
- Over MIDI SysEx the divisions are Rate values 128–143.

**New LFO shape:** **saw down** (shape 16), a falling sawtooth. The existing **sawtooth** rises.

---

## MIDI Clock

**Clock keeps running when the sequencer stops.** With the Clock Source set to **External**, when your
sequencer stops sending MIDI clock:

- synced LFOs, the clock modulation sources (**CkDwhl … Ck16th**), the arpeggiator and Beats keep
  running at the last tempo instead of freezing;
- the sequencer still stops with your DAW.

When the sequencer continues, synced LFOs return to its grid; MIDI **Start** resets them to bar 1.
Short dropouts in the clock (under 250 ms) are caught up, so the LFOs stay in time.

**Corrected in this version:**

- With Clock Source External, EOS 4.70 counted the incoming MIDI clock **and** its own internal clock,
  so the sequencer, arpeggiator and clock sources ran too fast (60 BPM played like 180 BPM). They now
  follow the MIDI clock exactly.
- After power-on, the clock sources did not move until the arpeggiator or sequencer tempo had been
  changed. The clock now starts at the arpeggiator tempo when the first note plays.

---

## Transwave Scanning: the SLpScn Cord Destination

The new cord destination **SLpScn** (sample loop scan) slides a sample's loop window through the
sample while the note plays. With a sample made of a series of single-cycle waveforms ("frames"), the
loop moves from frame to frame: Ensoniq-style transwave and wavetable sounds.

**To scan a wavetable sample:**

1. Prepare the sample as described in **Building Transwave Samples** below: **at least 2 samples of
   silence**, then the frames. Loop it on its first frame (forward or alternating loop, Start 2).
2. Assign the sample to a voice.
3. On the **Cords** page, choose a source (for example **ModWl**, **Lfo1+** or an envelope), set the
   destination to **SLpScn** and the amount to **+100**.
4. Play a note and move the source: the sound changes as the loop moves through the frames.

- At **+100**, a full-scale source moves the loop from frame 1 to the end of the sample;
  **−100** moves it towards the start. Smaller amounts cover proportionally less; several cords add up.
- The loop position is updated every 10 ms and always stays inside the sample.
- Positions between frames blend the two neighbouring frames (no crossfade).
- The existing **SLoop** destination is unchanged (small loop offsets, about 127 samples per full cord).

### Building Transwave Samples

SLpScn slides the sample's loop window through the sample while the note plays. How you build the sample
decides how far it can travel and how many waveforms (frames) it can reach.

**Rules**

- **Minimum 2 samples of silence first.** Every transwave sample must begin with at least 2 samples of
  silence before frame 1: the E4 does not allow a loop to start before sample 2 (the loop editor stops
  at Start 2). Without this lead-in, frame 1 cannot be the loop, and the frame grid is off by 2 samples.
  With it, the loop sits on frame 1 at Start 2, End 2 + frame size.
- **Equal frames.** Make every frame exactly the loop (window) length. For click-free single-cycle
  frames, start each one at a zero crossing.
- **Loop on the first frame**, forward or alternating loop type. Other loop types are left alone.
- **Travel limit: 32,767 samples.** EOS keeps the loop shift in a 16-bit value, so the window can move
  at most 32,767 samples from where the loop is set (about 0.74 s at 44.1 kHz, 0.68 s at 48 kHz). The
  loop is also kept inside the sample.
- **Keep the whole sample within reach:** sample length ≤ 2 + 32,768 samples (with the loop on frame 1).
  Longer samples still play, but SLpScn's range is scaled to the whole sample, so the part of the
  controller travel aimed beyond the reachable area just holds at the limit.

**Maximum number of frames** (loop on frame 1; frames × frame size ≤ 32,768)

| Frame size (samples) | Max frames | Sample length | Frame-1 pitch at 44.1 kHz |
|---|---|---|---|
| 64 | 512 | 32,770 | 689.1 Hz |
| 128 | 256 | 32,770 | 344.5 Hz |
| 256 | 128 | 32,770 | 172.3 Hz |
| 512 | 64 | 32,770 | 86.1 Hz |
| 1,024 | 32 | 32,770 | 43.1 Hz |
| 2,048 | 16 | 32,770 | 21.5 Hz |
| 4,096 | 8 | 32,770 | 10.8 Hz |

Sample length = 2 + frames × frame size. Fewer frames are fine; the scan always spans the whole sample.
Frame-1 pitch is just the loop's natural pitch (sample rate ÷ frame size); set the root key so it plays
in tune. Bigger frames suit lower pitches and hold more detail. Smaller frames give more frames, but the
E4's resampling dulls high harmonics more when a frame has few samples per cycle.

**Control**

- **Range:** one cord at **+100** from a full-scale source (mod wheel at 127, Lfo1+ at peak, an envelope
  at full) moves the window from frame 1 to the end of the sample; **−100** moves it towards the start.
  Smaller amounts cover proportionally less, and extra cords add together.
- **Resolution:** the window position updates every 10 ms. A MIDI controller has 128 steps, so on a
  128 × 256 table each mod-wheel step moves about one frame (about 256 samples); on 32 × 256 it is about
  62 samples per step.
- **Character:** positions between frames blend the two neighbours, with the slightly gritty sound of a
  moving loop. There is no crossfade.
- **Other loop cords:** stock SLoop cords on the same voice still add their small fine offset (about 127
  samples per full cord).

**Example:** the test bank's **WT test** presets use a table of 32 frames of 256 samples with 2 lead-in
samples (8,194 samples, loop 2–258). Use Mod Wheel → SLpScn +100.

---

## Pan

**Corrected in this version:** in EOS 4.70 every pan control reached hard left or hard right at half its
range: voice **Pan** at −32/+32, Multimode (mixer) **Pan** at −32/+32, MIDI **controller 10** at 32/96, and
**AmpPan** cords at about half their amount. The outer half of each control did nothing. In 4.71-beta the
full range is used:

| Setting | −64 / CC 0 | −32 / CC 32 | −16 / CC 48 | 0 / CC 64 | +16 / CC 80 | +32 / CC 96 | +63 / CC 127 |
|---|---|---|---|---|---|---|---|
| Left − Right, EOS 4.70 | +72 dB | +72 dB (hard) | +15 dB | −0.2 dB | −16 dB | −72 dB (hard) | −72 dB |
| Left − Right, EOS 4.71-beta | +72 dB | +16 dB | +6 dB | −0.2 dB | −7 dB | −16 dB | −72 dB |

Presets that relied on the old behaviour (pan set to ±32 for a hard-panned sound) now sit half-way
between the centre and the side; set them to ±64 for a hard pan.

**To test pan on your E4:** load the test bank **Test Suite.E4B** (from the `testbank` folder of the
project) and run the **EOS Pan Test** application (see *Pan Test Application* below).

---

## Performance

The cord processing of every playing voice now stops after the last cord in use instead of always
checking all 24 cords. The sound is identical. On a 64-voice test preset the time spent on voice
control dropped by about 7 % (the cord stage by 29 %), leaving more processing time for the rest of the
system.

---

## Pan Test Application

**EOS Pan Test** (macOS and Windows) measures how far the E4's pan controls really pan.

**To run the pan test:**

1. Load the bank **Test Suite.E4B** into the E4 (from the project's `testbank` folder). The test uses
   preset **000** (a single sine voice on key 72).
2. Connect MIDI both ways, and connect the E4's main outputs (and, if you like, sub outputs) to an audio
   interface input.
3. Start **EOS Pan Test**. Select the MIDI output and input, the E4's MIDI device ID and channel, the
   audio device and the input pair(s) the E4 is connected to.
4. Choose the tests (voice Pan, Multimode Pan, MIDI CC10) and press **Run tests**.
5. The results table shows the left and right levels for every setting, and the summary tells you
   whether the pan bug is present ("hard left/right at half range") or fixed ("full pan range").
6. Press **Save CSV + WAV…** to keep the measurements, and **Report to GitHub…** to send them to the
   project as a report (your browser opens a pre-filled report for you to review and submit).

> **Note:** "Prepare preset" selects preset 000 for editing, turns its cords down and opens its filter so
> that only pan changes the level. These edits are not saved.

---

## Known Limitations

- Synced LFOs do not follow MIDI Song Position Pointer; after Continue they resume from where the
  sequencer stopped.
- While the MIDI clock is stopped, the clock keeps the last tempo within about 0.2 % (LFOs) and 2 %
  (clock sources).
- A small 0.25 dB right-heavy offset at the pan centre (from E-mu's pan table) remains.
- EOS 4.71-beta runs on Ultra models only, like EOS 4.70.
