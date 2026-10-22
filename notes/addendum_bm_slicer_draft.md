## Beat Munger: Slice to Samples and Preset

The new **Slice** soft key in Beat Munger turns a drum loop into a playable kit, like a dedicated loop slicer. It
uses the slice points Beat Munger finds, makes one new sample per slice and builds a new preset with each slice on
its own key.

**To slice a loop:**

1. In Sample Edit, select the loop and open **Beat Munger**.
2. Adjust Beat Munger's settings, using **re-Anlyz** and **Play**, until the slices fall on the hits you want.
3. Press **Slice** (the soft key between Cancel and Stop).

The E4 then:

- makes one new sample per slice in the first free sample locations, named after the loop with a slice number, for
  example `Amen Break 01`, `Amen Break 02`, …;
- makes a new preset in the first free preset location, named after the loop;
- maps slice 1 to key 36 (C1), slice 2 to the next key up, and so on. Each slice's original key is its own key, so
  every slice plays back at its original pitch;
- leaves Beat Munger and selects the new preset, with the message **Sliced: n samples, preset p**.

Notes:

- The original loop is not changed, and the sample clipboard and the Sample Edit selection are kept.
- Each cut is placed just before its hit, so attacks are not clipped. It then moves to the nearest point where the
  waveform crosses zero, so slices start without a click.
- Slice 1 starts at the beginning of the loop, and the last slice runs to its end, so the slices play back to back
  as the complete loop.
- Slices are uneven in length because they follow the hits in the loop: a slice runs from one hit to the next.
- Hits closer than about 23 ms are kept in one slice. A preset holds at most 92 slices (keys 36 to 127).
- Mono and stereo loops can both be sliced.
- Each slice takes the loop's loop setting: if the loop is set to loop, so is every slice.
- Slicing uses new sample memory about the size of the loop.

**Messages:**

| Message | Meaning |
|---|---|
| Slice: no slices to make | Beat Munger has found no slices, or the sample is too short. |
| Slice: no free sample slots/preset | There are not enough free sample locations for the slices, or no free preset. Nothing is changed. |
| Slice: not enough sample memory | There is not enough free sample memory. Nothing is made; Beat Munger closes. |

If Beat Munger is still playing when you press Slice, slicing starts when playback stops.

### Slicing compared

| | **Beat Munger Slice** | **'Slice cord** |
|---|---|---|
| Slice points | At the hits Beat Munger finds | Equal lengths, set by the loop |
| What it makes | New samples and a new preset | Nothing: it plays sections of one sample |
| Sample memory | About one more copy of the loop | None |
| Editing slices | Each slice is its own sample | Edit the one sample |

Use **Beat Munger Slice** for real drum loops with uneven hits, and the **'Slice** cord for loops cut into equal steps.
