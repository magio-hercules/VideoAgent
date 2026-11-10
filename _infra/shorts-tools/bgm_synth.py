#!/usr/bin/env python3
"""가벼운 해설용 배경음악 루프를 코드로 합성한다 (저작권 걱정 없는 자체 생성음).

플럭(카플러스-스트롱) 아르페지오 + 부드러운 베이스 + 벨 멜로디 + 가벼운 셰이커/킥.
사용: python3 _infra/shorts-tools/bgm_synth.py out.wav [--bpm 104] [--bars 8] [--seed 7]
출력: 48kHz 스테레오 WAV, 끝과 처음이 이어지는 루프. ffmpeg로 −20 LUFS에 맞춘다.
"""
import argparse
import os
import subprocess
import wave

import numpy as np

SR = 48000
NOTE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def hz(name, octave):
    return 440.0 * 2 ** ((NOTE[name] + 12 * (octave + 1) - 69) / 12)


def pluck(f, dur, rng, bright=0.5):
    n = int(dur * SR)
    p = max(2, int(SR / f))
    buf = rng.uniform(-1, 1, p)
    out = np.empty(n)
    for i in range(n):
        out[i] = buf[i % p]
        buf[i % p] = 0.5 * (buf[i % p] + buf[(i + 1) % p]) * (0.996 - 0.004 * (1 - bright))
    env = np.minimum(1, np.arange(n) / (0.003 * SR))
    return out * env


def bell(f, dur):
    t = np.arange(int(dur * SR)) / SR
    y = (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * f * 2.76 * t) * np.exp(-t * 6)
         + 0.2 * np.sin(2 * np.pi * f * 5.4 * t) * np.exp(-t * 10))
    return y * np.exp(-t * 3.2) * np.minimum(1, t / 0.002)


def bass(f, dur):
    t = np.arange(int(dur * SR)) / SR
    y = np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * 2 * f * t)
    return y * np.exp(-t * 2.2) * np.minimum(1, t / 0.01)


def kick(dur=0.25):
    t = np.arange(int(dur * SR)) / SR
    f = 50 + 70 * np.exp(-t * 30)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 14)


def shaker(rng, dur=0.07):
    n = int(dur * SR)
    x = rng.standard_normal(n)
    X = np.fft.rfft(x)
    fr = np.fft.rfftfreq(n, 1 / SR)
    X[fr < 5000] *= 0.05
    x = np.fft.irfft(X, n)
    t = np.arange(n) / SR
    return x / (np.abs(x).max() or 1) * np.exp(-t * 60)


def add(bus, y, t, gain, pan=0.0):
    i = int(round(t * SR)) % len(bus)
    l, r = gain * (1 - max(0, pan)), gain * (1 + min(0, pan))
    n = len(y)
    end = i + n
    if end <= len(bus):
        bus[i:end, 0] += y * l
        bus[i:end, 1] += y * r
    else:  # 루프 끝을 넘으면 앞으로 감는다
        k = len(bus) - i
        bus[i:, 0] += y[:k] * l
        bus[i:, 1] += y[:k] * r
        bus[:n - k, 0] += y[k:] * l
        bus[:n - k, 1] += y[k:] * r


def reverb(x, rng, secs=0.9, wet=0.16):
    n = int(secs * SR)
    ir = rng.standard_normal(n) * np.exp(-np.arange(n) / SR * 5.5)
    ir /= np.sqrt((ir ** 2).sum())
    out = np.empty_like(x)
    L = len(x)
    for c in range(2):
        X = np.fft.rfft(np.concatenate([x[:, c], x[:, c]]), 2 * L + n)
        H = np.fft.rfft(ir, 2 * L + n)
        y = np.fft.irfft(X * H, 2 * L + n)
        out[:, c] = y[L:2 * L]  # 원형(루프) 잔향
    return x * (1 - wet) + out * wet


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--bpm", type=float, default=104)
    ap.add_argument("--bars", type=int, default=8)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    beat = 60 / a.bpm
    bar = 4 * beat
    total = a.bars * bar
    bus = np.zeros((int(round(total * SR)), 2))
    prog = [("C", ["C", "E", "G"]), ("G", ["G", "B", "D"]), ("A", ["A", "C", "E"]), ("F", ["F", "A", "C"])]
    arp = [0, 2, 1, 2, 0, 2, 1, 2]
    melody = [("E", 5), ("G", 5), ("A", 5), ("G", 5), ("D", 5), ("E", 5), ("C", 5), None,
              ("E", 5), ("G", 5), ("C", 6), ("A", 5), ("G", 5), ("E", 5), ("D", 5), None]
    for b in range(a.bars):
        root, tri = prog[b % 4]
        t0 = b * bar
        for k in range(8):
            nm = tri[arp[k]]
            octv = 4 if k % 4 != 2 else 5
            add(bus, pluck(hz(nm, octv), beat * 1.6, rng, 0.6), t0 + k * beat / 2, 0.16 if k % 2 else 0.2, -0.35)
        add(bus, bass(hz(root, 2), beat * 1.8), t0, 0.32)
        add(bus, bass(hz(root, 2), beat * 1.8), t0 + 2 * beat, 0.26)
        add(bus, kick(), t0, 0.22)
        add(bus, kick(), t0 + 2 * beat, 0.16)
        for k in range(8):
            add(bus, shaker(rng), t0 + k * beat / 2, 0.05 if k % 2 == 0 else 0.08, 0.3)
        if b >= a.bars // 2:
            for k in range(4):
                m = melody[((b - a.bars // 2) * 4 + k) % len(melody)]
                if m:
                    add(bus, bell(hz(*m), beat * 1.5), t0 + k * beat, 0.11, 0.4)
    bus = reverb(bus, rng)
    bus /= np.abs(bus).max() * 1.25
    raw = a.out + ".raw.wav"
    with wave.open(raw, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(bus, -1, 1) * 32767).astype("<i2").tobytes())
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-af", "loudnorm=I=-20:TP=-3:LRA=11",
                    "-ar", str(SR), a.out], check=True)
    os.remove(raw)
    print(a.out, round(total, 3), "s")


if __name__ == "__main__":
    main()
