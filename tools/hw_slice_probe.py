#!/usr/bin/env python3
"""Read the Slice probe ("EOS 4.71-b2 SliceProbe", patches/slice/probe.s) over SysEx parameter 195.

usage: hw_slice_probe.py            -> prints the last note-on's Slice inputs
Play one note on the voice with the 'Slice cord first. Halfwords: 0/1 note-on count, 2 Slice cord sum (voice+0x1C),
3 Slice mode flag (voice+0x1E), 4/5 note struct +16 (loop start, 8 = one-shot), 6/7 sample header +0x38/+0x3A.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eos_remote as er   # noqa: E402

e = er.Eos()
h = []
for i in range(8):
    e.set(195, i)
    v = e.get([195]).get(195)
    h.append(v & 0xFFFF if v is not None else None)
e.close()
s14 = lambda v: v - 0x4000 if v >= 0x2000 else v
print('raw halfwords (14-bit SysEx values):', h)
print(f'note-ons seen (low bits): {h[1]}')
print(f'Slice cord sum: {s14(h[2])}   (0 = no Slice input reached the voice)')
print(f'Slice mode flag: {h[3]}   (1 = voice recognised as a Slice voice)')
print(f'note +16 low word: {h[5]}  (8 with high word 0 = one-shot; else looped)  high word {h[4]}')
print(f'header +0x3A byte (loop type in bits 6-7): {h[7] >> 8 if h[7] is not None else None}  (+0x38 word {h[6]})')
