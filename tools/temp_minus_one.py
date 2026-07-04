#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
单次温度- 采集 — 按一次降1度，抓松手帧
双击运行，按一次温度-就停
"""

import os, sys, subprocess, re, time as _time, glob

def find_esp32():
    ports = glob.glob("/dev/cu.wchusb*") + glob.glob("/dev/cu.usbserial*") + glob.glob("/dev/cu.SLAB*")
    return ports[0] if ports else None

def find_python():
    for py in [sys.executable,
               "/Users/guoli/Library/Application Support/QClaw/openclaw/config/bin/python/python3",
               "/usr/local/bin/python3", "/usr/bin/python3", "python3"]:
        try:
            r = subprocess.run([py, "-m", "mpremote", "--help"], capture_output=True, timeout=8)
            if r.returncode == 0: return py
        except: continue
    return None

def classify(hw):
    if hw < 700: return '0'
    if hw < 1200: return '1'
    if hw < 1600: return 'E'
    if hw >= 4000: return 'F'
    return '?'

def main():
    print()
    print("=" * 50)
    print("  单次温度- 采集")
    print("=" * 50)

    port = find_esp32()
    if not port:
        print("❌ ESP32 未检测到"); input(); return
    print(f"✅ {port}")

    py = find_python()
    if not py:
        print("❌ mpremote 未安装"); input(); return

    # 倒计时
    print("\n5秒后去按一次温度-，松手即可")
    for i in range(5, 0, -1):
        print(f"  ⏳ {i} ...", flush=True)
        _time.sleep(1)
    print("  🎬 按！")

    # 采集
    esp = "/tmp/_esp1.py"
    with open(esp, "w") as f:
        f.write(r'''
from machine import Pin
import time
pin=Pin(33,Pin.IN)
f=open("btn_cap.txt","w")
prev=pin.value()
start=time.ticks_us()
changes=0
deadline=time.ticks_add(start,8_000_000)
while time.ticks_diff(time.ticks_us(),deadline)<0:
    v=pin.value()
    if v!=prev:
        now=time.ticks_diff(time.ticks_us(),start)
        f.write(str(now)+" "+str(v)+"\n")
        prev=v
        changes+=1
f.close()
print("CAP_OK",changes)
''')
    try:
        r = subprocess.run([py, "-m", "mpremote", "connect", port, "run", esp],
                          capture_output=True, text=True, timeout=20)
        ok = "CAP_OK" in r.stdout
    except:
        ok = False
    os.unlink(esp)

    if not ok:
        print("❌ 采集失败"); input(); return

    # 下载
    raw = "/tmp/_raw1.txt"
    with open(raw, "w") as f:
        for chunk in range(3):
            s = chunk * 300
            rr = subprocess.run(
                [py, "-m", "mpremote", "connect", port, "exec",
                 f"f=open('btn_cap.txt');"
                 f"[f.readline() for _ in range({s})];"
                 f"[print(l.strip()) for l in [f.readline() for _ in range(300)] if l];"
                 f"f.close()"],
                capture_output=True, text=True, timeout=10
            )
            for l in rr.stdout.split("\n"):
                if re.match(r'\d+\s+[01]', l.strip()):
                    f.write(l.strip() + "\n")

    # 解析
    data = []
    with open(raw) as f:
        for l in f:
            m = re.match(r'(\d+)\s+([01])', l.strip())
            if m: data.append((int(m.group(1)), int(m.group(2))))

    pulses = []
    for j in range(1, len(data)):
        if data[j-1][1] == 1 and data[j][1] == 0:
            pulses.append((data[j][0], data[j][0]-data[j-1][0], classify(data[j][0]-data[j-1][0])))

    frames, cur = [], []
    for t, hw, s in pulses:
        if s == 'F':
            if cur: frames.append(cur)
            cur = []
        else: cur.append((t, hw, s))
    if cur: frames.append(cur)

    print(f"\n脉冲:{len(pulses)}  帧:{len(frames)}  时长:{data[-1][0]/1e6:.1f}秒")

    for i, f in enumerate(frames):
        bits = ''.join(s for _,_,s in f)
        pure = ''.join(c for c in bits if c in '01')
        t = f[0][0]/1000 if f else 0
        widths = [hw for _,hw,_ in f]
        if len(pure) >= 4:
            print(f"\n  🔑 F{i} @{t:.0f}ms: 帧=[{bits}]  纯数据=[{pure}]")
            print(f"      脉宽: {widths}")

    input("\n按回车退出...")

if __name__ == "__main__":
    main()
