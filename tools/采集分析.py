#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
空调协议采集工具
双击运行 → 自动检测ESP32 → 倒计时提示 → 采集 → 分析 → 报告输出到Downloads
"""

import os, sys, subprocess, datetime, re, time as _time
from collections import Counter

DOWNLOADS = os.path.expanduser("~/Downloads")
REPORT = os.path.join(DOWNLOADS, f"空调采集报告_{datetime.datetime.now().strftime('%m%d_%H%M')}.txt")

def find_esp32():
    import glob
    ports = glob.glob("/dev/cu.wchusb*") + glob.glob("/dev/cu.usbserial*") + glob.glob("/dev/cu.SLAB*")
    if sys.platform == "win32":
        try:
            import serial.tools.list_ports
            ports = [p.device for p in serial.tools.list_ports.comports()]
        except:
            pass
    return ports[0] if ports else None

def find_python():
    for py in [sys.executable,
               "/Users/guoli/Library/Application Support/QClaw/openclaw/config/bin/python/python3",
               "/usr/local/bin/python3", "/usr/bin/python3", "python3", "python"]:
        try:
            r = subprocess.run([py, "-m", "mpremote", "--help"],
                             capture_output=True, timeout=8)
            if r.returncode == 0:
                return py
        except:
            continue
    return None

ESP_CODE = '''
from machine import Pin
import time

pin = Pin(33, Pin.IN)
f = open("btn_cap.txt", "w")
prev = pin.value()
start = time.ticks_us()
changes = 0

deadline = time.ticks_add(start, 15_000_000)
while time.ticks_diff(time.ticks_us(), deadline) < 0:
    v = pin.value()
    if v != prev:
        now = time.ticks_diff(time.ticks_us(), start)
        f.write(str(now) + " " + str(v) + "\\n")
        prev = v
        changes += 1

f.close()
print("CAP_END", changes, "edges")
'''

def classify(hw):
    if hw < 700: return '0'
    if hw < 1200: return '1'
    if hw < 1600: return 'E'
    if hw >= 4000: return 'F'
    return '?'

def analyze_file(filepath):
    data = []
    with open(filepath, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = re.match(r'(\d+)\s+([01])', line.strip())
            if m:
                data.append((int(m.group(1)), int(m.group(2))))
    if len(data) < 10:
        return None

    pulses = []
    for j in range(1, len(data)):
        if data[j-1][1] == 1 and data[j][1] == 0:
            hw = data[j][0] - data[j-1][0]
            pulses.append((data[j][0], hw, classify(hw)))

    sym_dist = Counter(s for _,_,s in pulses)

    frames, cur = [], []
    for t, hw, s in pulses:
        if s == 'F':
            if cur: frames.append(cur)
            cur = []
        else: cur.append((t,hw,s))
    if cur: frames.append(cur)

    complex_frames = []
    for i, f in enumerate(frames):
        if len(f) >= 4:
            bits = ''.join(s for _,_,s in f)
            t = f[0][0] / 1000
            complex_frames.append((i, t, bits))

    return {
        'edges': len(data), 'pulses': len(pulses),
        'symbols': dict(sym_dist), 'frames': len(frames),
        'complex_frames': complex_frames,
        'duration': data[-1][0] / 1e6 if data else 0,
    }

def main():
    print()
    print("=" * 60)
    print("  世纪星空调协议采集工具 v2")
    print("=" * 60)
    print()

    # ── 环境检测 ──
    print("🔌 检测 ESP32 ...")
    port = find_esp32()
    if not port:
        print("❌ 未检测到 ESP32 串口！")
        print("   1. 确认 USB 已插好")
        print("   2. 确认 CH340 驱动已装")
        print("   3. 终端运行: ls /dev/cu.wchusb* 看看有没有设备")
        input("\n按回车退出...")
        return
    print(f"   ✅ 已连接: {port}")

    print("🐍 检测 Python 环境 ...")
    py = find_python()
    if not py:
        print("❌ 未找到可用的 mpremote")
        print("   请运行: pip3 install mpremote")
        input("\n按回车退出...")
        return
    print(f"   ✅ Python: {py}")

    # ── 倒计时 ──
    print()
    print("=" * 60)
    print("  ⚠️  采集将在倒计时结束后开始（共15秒）")
    print()
    print("  操作：去面板前站好 → 倒计时到0 → 立即按按钮松手")
    print("=" * 60)
    print()

    for i in range(5, 0, -1):
        print(f"  ⏳ {i} ...", flush=True)
        _time.sleep(1)

    print()
    print("  🎬 开始采集！现在去按按钮！")
    print()

    # ── 上传并采集 ──
    esp_file = "/tmp/esp_cap_script.py"
    with open(esp_file, "w") as f:
        f.write(ESP_CODE)

    try:
        result = subprocess.run(
            [py, "-m", "mpremote", "connect", port, "run", esp_file],
            capture_output=True, text=True, timeout=30
        )
        os.unlink(esp_file)
        output = result.stdout + result.stderr
        edges_found = "?"
        for line in output.split("\n"):
            if "CAP_END" in line:
                edges_found = line.strip()
        print(f"   ✅ 采集完成: {edges_found}")
    except subprocess.TimeoutExpired:
        print("   ⚠️  采集超时")
        os.unlink(esp_file)
    except Exception as e:
        print(f"   ❌ 采集失败: {e}")

    # ── 下载 ──
    print()
    print("📥 下载数据 ...")
    raw_file = "/tmp/esp_raw_data.txt"

    try:
        with open(raw_file, "w") as f:
            for chunk in range(5):
                start = chunk * 560
                r = subprocess.run(
                    [py, "-m", "mpremote", "connect", port, "exec",
                     f"f=open('btn_cap.txt');"
                     f"[f.readline() for _ in range({start})];"
                     f"[print(l.strip()) for l in [f.readline() for _ in range(560)] if l];"
                     f"f.close()"],
                    capture_output=True, text=True, timeout=12
                )
                for line in r.stdout.split("\n"):
                    if re.match(r'\d+\s+[01]', line.strip()):
                        f.write(line.strip() + "\n")
        lines = sum(1 for _ in open(raw_file))
        print(f"   ✅ 下载完成: {lines} 行")
    except Exception as e:
        print(f"   ❌ 下载失败: {e}")

    # ── 分析 ──
    print()
    print("🔍 分析 ...")
    result = analyze_file(raw_file)

    # ── 写报告 ──
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n")
        f.write(f"  空调协议采集报告\n")
        f.write(f"  时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 60 + "\n\n")

        f.write(f"  ESP32: {port}\n")
        f.write(f"  Python: {py}\n\n")

        if result:
            f.write(f"  边沿数: {result['edges']}\n")
            f.write(f"  脉冲数: {result['pulses']}\n")
            f.write(f"  时长: {result['duration']:.1f} 秒\n")
            f.write(f"  符号分布: 0={result['symbols'].get('0',0)}  1={result['symbols'].get('1',0)}  E={result['symbols'].get('E',0)}  F={result['symbols'].get('F',0)}\n")
            f.write(f"  帧数: {result['frames']}\n\n")

            if result['complex_frames']:
                f.write(f"  📌 完整数据帧 ({len(result['complex_frames'])}个):\n")
                for i, t, bits in result['complex_frames']:
                    f.write(f"    F{i} @{t:.0f}ms: [{bits}]\n")

                # 做XOR差分
                if len(result['complex_frames']) >= 2:
                    f.write(f"\n  帧间差分:\n")
                    prev_bits = None
                    for _, _, bits in result['complex_frames']:
                        if prev_bits and len(bits) == len(prev_bits):
                            diff = ''.join('X' if a!=b else '.' for a,b in zip(prev_bits, bits))
                            f.write(f"    [{prev_bits}]\n")
                            f.write(f"    [{bits}]  →  [{diff}]\n\n")
                        prev_bits = bits
            else:
                f.write(f"  ⚠ 未检测到完整数据帧\n")
                d0 = result['symbols'].get('0', 0)
                d1 = result['symbols'].get('1', 0)
                if d0 + d1 > 50:
                    f.write(f"  → 有数据位但帧结构异常\n")
                else:
                    f.write(f"  → 面板处于idle扫描状态（无按键操作）\n")
        else:
            f.write(f"  ❌ 数据无效\n")

    # ── 输出 ──
    print()
    with open(REPORT, encoding="utf-8") as f:
        for line in f:
            print(line, end="")

    print(f"\n📄 完整报告: {REPORT}")
    subprocess.run(["open", REPORT])
    input("\n按回车退出...")

if __name__ == "__main__":
    main()
