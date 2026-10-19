# Test bank

**Test Suite.E4B** is the E4 bank used to develop and test EOS 4.71-beta. Download it and load it into
your E4 (from disk, SCSI or a card, as you load any .E4B bank) before running the tests.

| Preset | Used for |
|---|---|
| 000 | **Pan test** (EOS Pan Test app): one voice, 801 Hz sine on key 72. |
| 001, 002 | Filter and transwave tests (002: 32-frame wavetable on Mod Wheel → SLpScn). |
| 003 | Polyphonic preset used for CPU-load timing. |

**To run the pan test:** load the bank, select preset 000 on MIDI channel 1, connect the E4's main
outputs to your audio interface and run **EOS Pan Test** (see the top-level README). The app selects the
preset for editing, turns its cords down and opens the filter (not saved), then sweeps voice Pan,
Multimode Pan and MIDI CC10.
