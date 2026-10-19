#!/usr/bin/env python3
"""Gapless recording of the E4 outputs (MOTU inputs 17/18) in 60 s WAV chunks with wall-clock stamps.

usage: hw_monitor.py OUTDIR MINUTES [DEVICE_SUBSTRING] [FIRST_CHANNEL_1BASED]   (default Quantum, 19)
Each chunk: OUTDIR/chunk_NNN_HHMMSS.wav ; index in OUTDIR/index.csv (chunk, start wall clock, frames).
"""
import os, queue, sys, time, datetime
import numpy as np, sounddevice as sd, soundfile as sf

FS = 48000
CH = (16, 17)


def main():
    out, minutes = sys.argv[1], float(sys.argv[2])
    name = sys.argv[3] if len(sys.argv) > 3 else 'Quantum'
    first = int(sys.argv[4]) - 1 if len(sys.argv) > 4 else 18
    os.makedirs(out, exist_ok=True)
    dev = [i for i, d in enumerate(sd.query_devices()) if name in d['name'] and d['max_input_channels'] > 0][0]
    nch = sd.query_devices(dev)['max_input_channels']
    q = queue.Queue()
    overflows = [0]

    def cb(indata, frames, t, status):
        if status:
            overflows[0] += 1
        q.put(indata[:, first:first + 2].copy())

    idx = open(os.path.join(out, 'index.csv'), 'a')
    total = int(minutes * 60 * FS)
    got = 0
    chunk_n = 0
    with sd.InputStream(samplerate=FS, device=dev, channels=nch, dtype='float32', blocksize=2048, callback=cb):
        while got < total:
            start = datetime.datetime.now()
            name = os.path.join(out, f'chunk_{chunk_n:03d}_{start:%H%M%S}.wav')
            n = 0
            with sf.SoundFile(name, 'w', FS, 2, 'PCM_24') as f:
                while n < 60 * FS and got < total:
                    b = q.get()
                    f.write(b)
                    n += len(b); got += len(b)
            idx.write(f'{chunk_n},{start:%Y-%m-%d %H:%M:%S.%f},{n},{overflows[0]}\n'); idx.flush()
            print(f'chunk {chunk_n} started {start:%H:%M:%S} frames {n} overflows {overflows[0]}', flush=True)
            chunk_n += 1


if __name__ == '__main__':
    main()
