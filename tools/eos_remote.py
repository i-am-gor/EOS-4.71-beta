#!/usr/bin/env python3
"""Talk to a live EOS 4.70 sampler over MIDI using E-mu's editor SysEx (decoded from EOS, see notes/eos_sysex.md).

Header: F0 18 21 <dev> 55 <cmd> ...
  0x02 parameter request : F0 18 21 dd 55 02 <n> (<id lo> <id hi>)*n F7      (read-only)
  reply / 0x01 edit      : F0 18 21 dd 55 01 02 <id lo> <id hi> <val lo> <val hi> 7F F7
IDs are table indices 0..270 (table 0x63E58); values are 14-bit, >= 0x2000 negative.

usage: eos_remote.py get ID [ID...]      eos_remote.py names
"""
import sys, time
import mido

PORT = '828mk3 Hybrid MIDI Port'
DEV = 1

NAMES = {
    82: 'filter type', 83: 'filter freq', 84: 'filter Q',
    105: 'LFO1 rate', 106: 'LFO1 shape', 107: 'LFO1 delay', 108: 'LFO1 variation', 109: 'LFO1 sync',
    110: 'LFO2 rate', 111: 'LFO2 shape', 112: 'LFO2 delay', 113: 'LFO2 variation', 114: 'LFO2 sync',
    222: 'magic load preset',
}
for c in range(18):
    NAMES[129 + 3 * c] = f'cord{c+1} src'
    NAMES[130 + 3 * c] = f'cord{c+1} dst'
    NAMES[131 + 3 * c] = f'cord{c+1} amount'


def s14(v):
    return v - 0x4000 if v >= 0x2000 else v


class Eos:
    def __init__(self, port=PORT, dev=DEV):
        self.dev = dev
        self.out = mido.open_output(port)
        self.inp = mido.open_input(port)

    def close(self):
        self.out.close(); self.inp.close()

    def _drain(self):
        for _ in self.inp.iter_pending():
            pass

    def send(self, body):
        self.out.send(mido.Message('sysex', data=[0x18, 0x21, self.dev, 0x55] + list(body)))

    def get(self, ids, timeout=1.0):
        self._drain()
        body = [0x02, len(ids)]
        for i in ids:
            body += [i & 0x7f, (i >> 7) & 0x7f]
        self.send(body)
        got, t0 = {}, time.time()
        while time.time() - t0 < timeout and len(got) < len(ids):
            for m in self.inp.iter_pending():
                d = m.data if m.type == 'sysex' else ()
                if len(d) >= 10 and d[:4] == (0x18, 0x21, self.dev, 0x55) and d[4] == 0x01:
                    pid = d[6] | (d[7] << 7)
                    got[pid] = s14(d[8] | (d[9] << 7))
            time.sleep(0.005)
        return got

    def set(self, pid, value):
        v = value & 0x3fff
        self.send([0x01, 0x02, pid & 0x7f, (pid >> 7) & 0x7f, v & 0x7f, (v >> 7) & 0x7f, 0x7f])


def main():
    if sys.argv[1] == 'names':
        for k in sorted(NAMES):
            print(k, NAMES[k])
        return
    if sys.argv[1] == 'get':
        e = Eos()
        ids = [int(x, 0) for x in sys.argv[2:]]
        vals = e.get(ids)
        for i in ids:
            print(f'{i:3d} {NAMES.get(i, ""):18s} = {vals.get(i, "(no reply)")}')
        e.close()


if __name__ == '__main__':
    main()
