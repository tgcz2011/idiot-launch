# -*- coding: utf-8 -*-
"""合成倒计时结束铃声 WAV（多音上行铃，类似上课提示音）。"""
import os
import math
import struct
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "alarm.wav")

SAMPLE_RATE = 22050
# 音符序列：频率(Hz), 时长(秒), 间隔(秒) —— 经典"叮咚"式上课铃
NOTES = [
    (880.0, 0.18, 0.05),   # 高音叮
    (1174.7, 0.18, 0.05),  # D6
    (880.0, 0.18, 0.05),
    (1174.7, 0.18, 0.05),
    (880.0, 0.35, 0.10),   # 结束长音
]

def synth(freq, dur, amp=0.55):
    n = int(SAMPLE_RATE * dur)
    out = []
    for i in range(n):
        t = i / SAMPLE_RATE
        # 指数衰减包络
        env = math.exp(-3.0 * t / dur) if dur > 0 else 0
        # 主音 + 二次谐波
        v = (math.sin(2 * math.pi * freq * t)
             + 0.35 * math.sin(2 * math.pi * freq * 2 * t))
        out.append(int(max(-1.0, min(1.0, v * env * amp)) * 32767))
    return out

samples = []
for freq, dur, gap in NOTES:
    samples.extend(synth(freq, dur))
    samples.extend([0] * int(SAMPLE_RATE * gap))

with wave.open(OUT, "w") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(SAMPLE_RATE)
    w.writeframes(struct.pack("<%dh" % len(samples), *samples))

print("saved", OUT, "duration=%.2fs" % (len(samples) / SAMPLE_RATE))
