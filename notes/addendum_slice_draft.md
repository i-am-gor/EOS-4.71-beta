## Beat Slicing: the 'Slice Cord Destination

The new cord destination **'Slice** plays one slice of a sample per key, like a sliced drum loop in a
dedicated slicer. The slices are equal-length sections of one sample, so no new samples are made and no
extra sample memory is used. As with **'SStart**, the apostrophe means the slice is chosen when the note
starts.

**To slice a loop:**

1. Prepare the sample as equal-length slices, one after another, for example a one-bar loop at an exact
   tempo with 16 equal steps. Start it with **at least 2 samples of silence**: the E4 does not allow a loop to
   start before sample 2. **Insert Silence** (Sample Edit, Utils, Silnc) adds 4.
2. In Sample Edit, set the **loop** on the first slice: Loop Start = the start of slice 1, Loop End = the end
   of slice 1. The loop length is the slice length.
   - **Loop off:** each slice plays once and stops at its end.
   - **Loop on:** each slice loops on itself while the key is held.
3. Assign the sample to a voice. The voice's **Original Key** is the key that plays slice 1.
4. On the **Cords** page, set the source to **Key+**, the destination to **'Slice** and the amount to **+100**.
5. Play the Original Key for slice 1, the next key up for slice 2, and so on.

- Keys above the last slice play the last slice; keys below the Original Key play the first slice (or
  slices before the loop, if the sample has whole slices before it).
- Stereo samples are sliced on both sides.
- **SStart** still works: it offsets the start point inside the slice.
- With a controller source, such as **ModWl** at +100, the controller value counted from the Original Key
  picks the slice: value = Original Key plays slice 1, each step up the next slice.
- The slice is set at note-on; moving the source during a note does not change the slice.
- 'Slice and **WTScan** share the same cord sum: do not use both on one voice.

### 'Slice and WTScan compared

Both destinations read the sample's loop, but they do different jobs: **'Slice** is a slicer,
**WTScan** is a transwave scanner.

| | **'Slice** | **WTScan** |
|---|---|---|
| When it acts | Once, at note-on | At note-on, then every 10 ms while the note plays |
| Where the note starts | At the start of slice *n* | At the current loop position (not the sample start) |
| What moves | Play start and end (and the loop, if on) jump to slice *n* | The loop window slides through the sample |
| Steps | Whole slices, snapped | Continuous: in-between positions blend neighbouring frames |
| Fast moves | — | Glide: at most 64 samples per 10 ms, so fast sources do not burst |
| Scale | One slice per key or controller step, from the Original Key | Full scale (+100, source at max) sweeps the whole sample |
| Loop off | Works: each slice plays once | Does nothing; it needs a forward loop |

Use **'Slice** for sliced drum loops and phrases, and **WTScan** for evolving wavetable and transwave sounds.
Do not use both on one voice: they share one cord sum, and on a voice with a 'Slice cord the WTScan
scan is switched off.
