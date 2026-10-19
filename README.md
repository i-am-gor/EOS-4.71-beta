# EOS 4.71-beta for the E-mu E4 Ultra

An unofficial update of E-mu's **EOS 4.70** for the Emulator IV family **Ultra** models, made by reverse
engineering the 4.70 firmware and testing every change in an emulator and on a real E4 Ultra.

**What's new** (details in [CHANGELOG.md](CHANGELOG.md) and the
[EOS 4.71-beta Operation Manual Addendum](docs/EOS-4.71-beta-Addendum.md),
[PDF](docs/EOS-4.71-beta-Addendum.pdf)):

- **OB-Xa (CEM3320) filter models** for the 2/4/6-pole lowpasses, 2nd/4th-order high-pass and band-pass,
  with cutoffs that follow the display.
- **Tempo-synced LFOs** (4 bars … 1/32, Key Sync or Free Run) and a new **saw down** LFO shape.
- **Transwave scanning**: new cord destination **SLpScn** moves the sample loop through a wavetable
  ([sample guide](docs/transwave-guide.md)).
- **MIDI clock** that keeps LFOs, clock sources, arpeggiator and Beats running when your DAW stops, and
  no longer runs double speed with an external clock.
- **Pan bug fixed**: voice Pan, Multimode Pan and MIDI CC10 now use their full range (4.70 hits hard
  left/right at half range).
- **Faster cord processing** (sound-identical).

> EOS 4.71-beta is not made, supported or endorsed by E-mu Systems or Creative Technology. It is a beta:
> back up your banks first. You can always flash the original EOS 4.70 back.

## Get it

E-mu's firmware is not distributed here. The **EOS Flasher** app builds 4.71-beta from your own copy of
E-mu's update file **EOS470.EXE** (it verifies the file is the original 4.70, applies this project's
patch and verifies the result) and sends it to the E4 over MIDI.

Downloads (see [Releases](../../releases)):

| App | macOS (universal: Apple silicon + Intel) | Windows |
|---|---|---|
| **EOS Flasher**: build 4.71-beta (or the original 4.70) and flash it over MIDI | `EOS-Flasher-macOS-universal.zip` | `EOS-Flasher-Windows.zip` |
| **EOS Pan Test**: measure the pan bug on your E4 and report results | `EOS-PanTest-macOS-universal.zip` | `EOS-PanTest-Windows.zip` |

The apps are not signed with a developer certificate: on macOS, right-click the app and choose **Open**
the first time; on Windows, choose **More info → Run anyway**.

### Flash EOS 4.71-beta

1. Connect a MIDI interface **both ways** to the E4 (the loader acknowledges every packet).
2. Start **EOS Flasher**, choose your **EOS470.EXE**, select **EOS 4.71-beta**, press **Build**.
3. Select the MIDI output and input, press **Send to E4**.
4. Power on the E4 holding **Enter**, answer **Yes** to "Download OS from MIDI?".
5. After about 9 minutes answer **Yes** to "Burn to flash?". The startup screen shows **EOS 4.71-beta**.

To go back, do the same with **Original EOS 4.70**.

### Test the pan bug (and send a report)

1. **Download the test bank** [`testbank/Test Suite.E4B`](testbank/Test%20Suite.E4B) and load it into your
   E4. The pan test uses **preset 000** (one sine voice on key 72); see [testbank/README.md](testbank/README.md).
2. Connect MIDI both ways and the E4's main outputs (optionally sub outputs) to your audio interface.
3. Start **EOS Pan Test**, select the MIDI ports, the E4's device ID and channel, the audio device and the
   input pair(s), and press **Run tests**.
4. The summary says whether the pan bug is present ("hard left/right at half range") or fixed
   ("full pan range"). **Save CSV + WAV** keeps the data; **Report to GitHub** opens a pre-filled
   [Pan test report](../../issues/new?template=pan-test-report.md) issue in your browser for you to
   review and submit (attach the CSV/WAV if you like).

## Repository

| Path | Contents |
|---|---|
| `apps/` | Rust apps: `eos-flasher`, `eos-pantest`, shared `eos-core` (codec, patch, MIDI File Dump, editor SysEx) |
| `apps/eos-core/data/eos471beta.e4p` | The 4.71-beta patch: only the 3,232 bytes this project wrote, applied to your own 4.70 |
| `patches/` | Assembler sources (ColdFire) of every change |
| `tools/` | Python builders, emulator test suites, hardware test scripts, MIDI File Dump tool |
| `notes/` | Design notes and measurements for each feature |
| `docs/` | Manual addendum (Markdown + PDF), Transwave guide, technical reference |
| `testbank/` | Test Suite.E4B bank |
| `testsignals/` | Test sine/sweep signals and the example wavetable |

Building the apps: `cd apps && cargo build --release` (macOS universal bundles: `apps/bundle_macos.sh`).
Rebuilding the firmware from source needs the stock image from your EOS470.EXE; see
[docs/TECHNICAL.md](docs/TECHNICAL.md).

## License

MIT for the code, patches and documentation in this repository ([LICENSE](LICENSE)). E-mu's EOS
firmware is not included and remains the property of its owners.
