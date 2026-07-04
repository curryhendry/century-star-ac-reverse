#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
温度全序列采集: 20→19→18→17→16
20秒采集, 你每隔2-3秒按一次温度-, 连按4次
"""

import os, sys, subprocess, re, time as _time, glob

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

def main():
    print()
    print("=" * 60)
    print("  温度全序列: 20→19→18→17→16")
    print("  20秒采集, 每2-3秒按一次温度-")
    print("=" * 60)

    port = find_esp32()
    if not port:
        print("❌ ESP32 未检测到"); input(); return
    print(f"✅ {port}")

    py = find_python()
    if not py:
        print("❌ mpremote 未安装"); input(); return

    print("""
    ╔═════════════════════════════════════╗
    ║  操作说明:                         ║
    ║  1. 确认面板当前是 20°C            ║
    ║  2. 倒计时到0后 → 开始采集         ║
    ║  3. 立即按第一次温度-(20→19)       ║
    ║  4. 等2-3秒 → 按第二次(19→18)      ║
    ║  5. 等2-3秒 → 按第三次(18→17)      ║
    ║  6. 等2-3秒 → 按第四次(17→16)      ║
    ║  7. 脚本自动结束, 出报告            ║
    ╚═════════════════════════════════════╝
    """)

    input("确认面板在20°C, 按回车继续...")

    for i in range(5, 0, -1):
        print(f"  ⏳ {i} ...", flush=True)
        _time.sleep(1)
    print("  🎬 开始！按第一下！(20→19)")

    # 20秒采集
    esp = "/tmp/_esp20.py"
    with open(esp, "w") as f:
        f.write(r'''
from machine import Pin
import time
pin=Pin(33,Pin.IN)
f=open("btn_cap.txt","w")
prev=pin.value()
start=time.ticks_us()
changes=0
deadline=time.ticks_add(start,20_000_000)
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
                          capture_output=True, text=True, timeout=30)
        ok = "CAP_OK" in r.stdout
    except:
        ok = False
    os.unlink(esp)

    if not ok:
        print("❌ 采集失败"); input(); return

    # 下载(分10片)
    print("\n📥 下载数据 ...")
    raw = "/tmp/_seq20.txt"
    with open(raw, "w") as f:
        for chunk in range(10):
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

    lines = sum(1 for _ in open(raw))
    print(f"✅ {lines} 行")

    # 解析所有帧
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

    # 提取≥2bit的数据帧，去重
    print(f"\n脉冲:{len(pulses)}  帧:{len(frames)}")
    print("\n键数据帧(≥3位纯数据), 按时间排序:")

    seen = set()
    data_frames = []
    for i, f in enumerate(frames):
        bits = ''.join(s for _,_,s in f)
        pure = ''.join(c for c in bits if c in '01')
        t = f[0][0]/1000 if f else 0
        if len(pure) >= 3:
            data_frames.append((t, pure, bits, [hw for _,hw,_ in f]))

    # 去重并排序
    for t, pure, bits, widths in data_frames:
        if pure not in seen:
            seen.add(pure)
            print(f"  @{t:6.1f}s  [{bits}]  纯=[{pure}]  ({len(pure)}位)")

    if len(seen) >= 2:
        vals = sorted(seen, key=lambda x: len(x), reverse=True)
        print(f"\n  去重后 {len(vals)} 个独立值: {vals}")
        print(f"\n  已知: 20°C=0011000  17°C=10011")

    input("\n按回车退出...")

if __name__ == "__main__":
    main()
