#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
温度- 采集工具 — 双击运行
流程: 检测 → 倒计时5秒(走去面板) → 开始采集 → 你按一次温度- → 自动出报告
"""

import os, sys, subprocess, datetime, re, time as _time, glob

DOWNLOADS = os.path.expanduser("~/Downloads")
NOW = datetime.datetime.now().strftime("%m%d_%H%M")
REPORT = os.path.join(DOWNLOADS, f"温度减_采集报告_{NOW}.txt")

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

ESP_CODE = r'''
from machine import Pin
import time

pin = Pin(33, Pin.IN)
f = open("btn_cap.txt","w")
prev = pin.value()
start = time.ticks_us()
changes = 0

deadline = time.ticks_add(start, 10_000_000)
while time.ticks_diff(time.ticks_us(), deadline) < 0:
    v = pin.value()
    if v != prev:
        now = time.ticks_diff(time.ticks_us(), start)
        f.write(str(now) + " " + str(v) + "\n")
        prev = v
        changes += 1

f.close()
print("CAP_OK", changes)
'''

def main():
    print()
    print("=" * 60)
    print("  空调温度- 采集工具")
    print("=" * 60)

    # 1. 检测
    print("\n🔌 检测 ESP32 ...")
    port = find_esp32()
    if not port:
        print("❌ 未检测到 ESP32，请确认 USB 已接好")
        input("\n按回车退出...")
        return
    print(f"   ✅ {port}")

    print("🐍 检测 Python ...")
    py = find_python()
    if not py:
        print("❌ 找不到 mpremote")
        input("\n按回车退出...")
        return
    print(f"   ✅ OK")

    # 2. 倒计时
    print()
    print("━" * 60)
    print("  5秒后开始采集，去面板前站好")
    print("━━" * 30)
    for i in range(5, 0, -1):
        print(f"  ⏳ {i} ...", flush=True)
        _time.sleep(1)
    print("  🎬 开始！现在去按一次 温度- ！")
    print()

    # 3. 采集
    esp_file = "/tmp/_esp_cap.py"
    with open(esp_file, "w") as f:
        f.write(ESP_CODE)

    ok = False
    try:
        r = subprocess.run([py, "-m", "mpremote", "connect", port, "run", esp_file],
                          capture_output=True, text=True, timeout=20)
        if "CAP_OK" in r.stdout:
            for line in r.stdout.split("\n"):
                if "CAP_OK" in line:
                    print(f"   ✅ {line.strip()}")
                    ok = True
        else:
            print(f"   ⚠ 采集异常: {r.stdout[-100:]}")
    except subprocess.TimeoutExpired:
        print("   ⚠ 超时")
    except Exception as e:
        print(f"   ❌ {e}")
    finally:
        try: os.unlink(esp_file)
        except: pass

    if not ok:
        input("\n采集失败，按回车退出...")
        return

    # 4. 下载
    print("\n📥 下载数据 ...")
    raw = "/tmp/_raw.txt"
    lines = 0
    try:
        with open(raw, "w") as f:
            for chunk in range(4):
                s = chunk * 450
                rr = subprocess.run(
                    [py, "-m", "mpremote", "connect", port, "exec",
                     f"f=open('btn_cap.txt');"
                     f"[f.readline() for _ in range({s})];"
                     f"[print(l.strip()) for l in [f.readline() for _ in range(450)] if l];"
                     f"f.close()"],
                    capture_output=True, text=True, timeout=12
                )
                for l in rr.stdout.split("\n"):
                    if re.match(r'\d+\s+[01]', l.strip()):
                        f.write(l.strip() + "\n")
        lines = sum(1 for _ in open(raw))
        print(f"   ✅ {lines} 行")
    except Exception as e:
        print(f"   ❌ {e}")

    # 5. 分析
    print("\n🔍 分析 ...")

    data = []
    with open(raw) as f:
        for l in f:
            m = re.match(r'(\d+)\s+([01])', l.strip())
            if m: data.append((int(m.group(1)), int(m.group(2))))

    # 脉冲宽度
    widths = []
    for j in range(1, len(data)):
        if data[j-1][1] == 1 and data[j][1] == 0:
            widths.append(data[j][0] - data[j-1][0])

    from collections import Counter
    wb = Counter()
    for w in widths:
        if w < 500: wb['<500'] += 1
        elif w < 700: wb['~485'] += 1
        elif w < 1000: wb['700-1000'] += 1
        elif w < 1200: wb['~975'] += 1
        elif w < 1600: wb['1200-1600'] += 1
        elif w < 3000: wb['1600-3000'] += 1
        elif w < 5000: wb['3000-5000'] += 1
        else: wb['>5000(F)'] += 1

    # 写报告
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("=" * 50 + "\n")
        f.write(f"  温度- 采集报告 ({NOW})\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"边沿: {len(data)}  脉冲: {len(widths)}  时长: {data[-1][0]/1e6:.1f}秒\n\n")
        f.write("脉冲宽度分布:\n")
        for k in ['<500','~485','700-1000','~975','1200-1600','1600-3000','3000-5000','>5000(F)']:
            n = wb.get(k, 0)
            if n > 0:
                f.write(f"  {k:>10}: {n:4d}\n")

        # 判断信号是否正常
        if wb.get('~485', 0) > 10 and wb.get('~975', 0) > 10:
            f.write("\n✅ 信号正常 — 有标准0/1脉冲\n")
        elif wb.get('1600-3000', 0) > 50:
            f.write("\n⚠️  信号异常 — 读到了载波，可能IR接收器接线松动\n")
            f.write("   检查: VCC→3.3V / GND→GND / OUT→GPIO33\n")
        else:
            f.write("\n❓ 信号模式不明确\n")

    # 打印
    print()
    with open(REPORT, encoding="utf-8") as f:
        print(f.read())

    print(f"\n📄 报告: {REPORT}")
    try: subprocess.run(["open", REPORT])
    except: pass

    input("\n按回车退出...")

if __name__ == "__main__":
    main()
