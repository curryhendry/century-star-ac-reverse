#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
温度逐级下降 ×3 采集工具
按三次温度-，每次降1度，抓3个松手帧对比
"""

import os, sys, subprocess, re, time as _time, glob, datetime

DOWNLOADS = os.path.expanduser("~/Downloads")

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

def do_capture(py, port, label, raw_file):
    esp = "/tmp/_esp_step.py"
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
    finally:
        try: os.unlink(esp)
        except: pass

    if not ok:
        return None

    # download
    with open(raw_file, "w") as f:
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
    return raw_file

def extract_first_frame(raw_file):
    data = []
    with open(raw_file) as f:
        for l in f:
            m = re.match(r'(\d+)\s+([01])', l.strip())
            if m: data.append((int(m.group(1)), int(m.group(2))))

    pulses = []
    for j in range(1, len(data)):
        if data[j-1][1] == 1 and data[j][1] == 0:
            hw = data[j][0] - data[j-1][0]
            pulses.append((data[j][0], hw, classify(hw)))

    frames, cur = [], []
    for t, hw, s in pulses:
        if s == 'F':
            if cur: frames.append(cur)
            cur = []
        else: cur.append((t, hw, s))
    if cur: frames.append(cur)

    # 找第一个≥4bit的数据帧
    for f in frames:
        if len(f) >= 4:
            bits = ''.join(s for _,_,s in f)
            pure = ''.join(c for c in bits if c in '01')
            widths = [hw for _,hw,_ in f]
            return bits, pure, widths
    return None, None, None

def main():
    print()
    print("=" * 60)
    print("  温度逐级下降 ×3 采集")
    print("  每按一次温度-降1度，连续按3次")
    print("=" * 60)

    port = find_esp32()
    if not port:
        print("❌ 未检测到 ESP32")
        input("\n按回车退出..."); return
    print(f"\n✅ ESP32: {port}")

    py = find_python()
    if not py:
        print("❌ 找不到 mpremote")
        input("\n按回车退出..."); return

    results = []
    for step in range(3):
        print(f"\n━━━ 第 {step+1}/3 次 ━━━")
        print("  5秒倒计时 ...")
        for i in range(5, 0, -1):
            print(f"  ⏳ {i} ...", flush=True)
            _time.sleep(1)
        print("  🎬 现在！去按一次 温度- ！")

        raw = f"/tmp/_step{step}.txt"
        do_capture(py, port, f"step{step}", raw)

        bits, pure, widths = extract_first_frame(raw)
        if pure:
            print(f"  ✅ 抓到: [{bits}]  → 纯数据位=[{pure}]  ({len(pure)}位)")
            results.append((f"第{step+1}次", pure, bits, widths))
        else:
            print(f"  ⚠ 未抓到数据帧")
            results.append((f"第{step+1}次", "?", "?", []))

        if step < 2:
            print("  等待用户按完按钮 ...")
            _time.sleep(2)

    # 汇总
    print()
    print("=" * 60)
    print("  三次采集汇总")
    print("=" * 60)
    for label, pure, bits, widths in results:
        print(f"\n  {label}:")
        print(f"    帧: [{bits}]")
        print(f"    纯数据位: [{pure}]")
        print(f"    原始脉宽: {widths}")

    # 差分
    if len(results) >= 2:
        p0 = results[0][1]
        p1 = results[1][1]
        if p0 != '?' and p1 != '?' and len(p0) == len(p1):
            diff = ''.join('X' if a!=b else '.' for a,b in zip(p0, p1))
            print(f"\n  📌 差分(1→2): [{p0}]→[{p1}]  [{diff}]  变化{diff.count('X')}位")

    if len(results) >= 3:
        p2 = results[2][1]
        if p2 != '?' and len(p1) == len(p2):
            diff2 = ''.join('X' if a!=b else '.' for a,b in zip(p1, p2))
            print(f"  📌 差分(2→3): [{p1}]→[{p2}]  [{diff2}]  变化{diff2.count('X')}位")

    input("\n按回车退出...")

if __name__ == "__main__":
    main()
