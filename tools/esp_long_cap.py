# esp_long_cap.py — 长时边沿捕获（60秒），支持多个操作
from machine import Pin
import time

pin = Pin(33, Pin.IN)
f = open('btn_cap.txt', 'w')
prev = pin.value()
start = time.ticks_us()
changes = 0

print("CAPTURE 60s — do multiple operations")

deadline = time.ticks_add(start, 60_000_000)
while time.ticks_diff(time.ticks_us(), deadline) < 0:
    v = pin.value()
    if v != prev:
        now = time.ticks_diff(time.ticks_us(), start)
        f.write(str(now) + ' ' + str(v) + '\n')
        prev = v
        changes += 1

f.close()
elapsed = time.ticks_diff(time.ticks_us(), start) // 1000
print("DONE:", changes, "edges in", elapsed, "ms")
