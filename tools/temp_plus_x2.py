#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
温度逐级下降 ×2 采集
操作: 面板当前亮屏 → 按两次温度-(每次降1度) → 抓两个松手帧
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
    print("=" * 60)
    print("  温度TEMP+ ×2  — 每次升1度")
    print("=" * 60)
    print()
    print("  ⚠️ 关键步骤（面板会熄屏！）:")
    print("  1. 脚本开始后 → 10秒内完成下面操作")
    print("  2. 先按一下唤醒屏幕(不改变温度)")
    print("  3. 等2秒确认亮屏")
    print("  4. 再按TEMP+ → 升1度后松手")
    print("  5. 等2秒")
    print("  6. 再按一次TEMP+ → 再升1度后松手")
    print()

    port = find_esp32()
    if not port: print("❌ ESP32 未检测到"); input(); return
    print(f"✅ ESP32: {port}")

    py = find_python()
    if not py: print("❌ mpremote 未安装"); input(); return

    input("确认面板当前在某个温度(亮屏), 按回车开始...")

    for i in range(5, 0, -1):
        print(f"  ⏳ {i} ...", flush=True)
        _time.sleep(1)
    print("  🎬 15秒采集 — 按步骤: 唤醒→等→按TEMP+→等→再按TEMP+")

    # 15秒采集
    esp = "/tmp/_esp15.py"
    with open(esp, "w") as f:
        f.write(r'''
from machine import Pin
import time
pin=Pin(33,Pin.IN)
f=open("btn_cap.txt","w")
prev=pin.value()
start=time.ticks_us()
changes=0
deadline=time.ticks_add(start,15_000_000)
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
                          capture_output=True, text=True, timeout=25)
    except: pass
    os.unlink(esp)

    # 下载
    raw = "/tmp/_tpx2.txt"
    with open(raw, "w") as f:
        for chunk in range(6):
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

    print(f"\n脉冲:{len(pulses)} 帧:{len(frames)} 时长:{data[-1][0]/1e6:.1f}秒")

    # 按400ms窗口输出所有数据帧
    print("\n时间线 (400ms窗口, 含数据位的帧):")

    winsize = 400000
    for ws in range(0, int(data[-1][0]), winsize):
        we = ws + winsize
        fs = [f for f in frames if f and ws <= f[0][0] < we]
        if not fs: continue

        data_fs = []
        for f in fs:
            bits = ''.join(s for _,_,s in f)
            pure = ''.join(c for c in bits if c in '01')
            if len(pure) >= 2 or 'E' in bits:
                data_fs.append((f, bits, pure))

        if data_fs:
            print(f"\n  [{ws/1000:5.0f}-{we/1000:5.0f}ms] {len(fs)}帧:")
            for f, bits, pure in data_fs:
                t0 = f[0][0]/1000 if f else 0
                widths = [hw for _,hw,_ in f]
                hasE = 'E' in bits
                tag = ''
                if not hasE and len(pure) >= 4: tag = ' ← 状态帧(无E)!'
                elif hasE: tag = ' ← 扫描帧(有E)'
                print(f"    @{t0:5.0f}ms [{bits}] 纯{pure} 脉宽:{widths}{tag}")

    input("\n按回车退出...")

if __name__ == "__main__":
    main()
