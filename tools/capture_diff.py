#!/usr/bin/env python3
# capture_diff.py — 一键：上传→采集→下载→差分分析
# 用法: python3 capture_diff.py
# 序列: 基线5秒 → 操作15秒 → 恢复5秒

import subprocess, os, datetime

PROJECT = '/Users/guoli/Projects/century-star-ac-reverse'
DATA = os.path.join(PROJECT, 'data')
MPREMOTE = '/Users/guoli/Library/Application Support/QClaw/openclaw/config/bin/python/python3'
PORT = '/dev/cu.wchusbserial141200'

ESP_CODE = '''
from machine import Pin
import time

pin = Pin(33, Pin.IN)

def cap(filename, sec):
    f = open(filename, 'w')
    prev = pin.value()
    start = time.ticks_us()
    changes = 0
    deadline = time.ticks_add(start, sec * 1_000_000)
    while time.ticks_diff(time.ticks_us(), deadline) < 0:
        v = pin.value()
        if v != prev:
            now = time.ticks_diff(time.ticks_us(), start)
            f.write(str(now) + ' ' + str(v) + '\\n')
            prev = v
            changes += 1
    f.close()
    print(filename, changes, "edges")

cap("R00_baseline.txt", 5)
time.sleep(3)
cap("R01_op.txt", 15)
time.sleep(3)
cap("R02_post.txt", 5)
print("DONE")
'''

def classify(hw):
    if hw < 700: return '0'
    if hw < 1200: return '1'
    if hw < 1600: return 'E'
    if hw >= 4000: return 'F'
    return '?'

def read_raw(path):
    data = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            p = line.split()
            if len(p) >= 2:
                data.append((int(p[0]), int(p[1])))
    return data

def extract_frames(data):
    pulses = []
    for j in range(1, len(data)):
        if data[j-1][1] == 1 and data[j][1] == 0:
            hw = data[j][0] - data[j-1][0]
            pulses.append(classify(hw))
    bits = [p for p in pulses if p in '01E']
    frames = []
    for i in range(0, len(bits) - 6, 7):
        frames.append(''.join(bits[i:i+7]))
    return frames

def diff(label, before, after):
    print(f"\n{'='*60}")
    print(f"  {label}: {len(before)}帧 → {len(after)}帧")
    print(f"{'='*60}")
    new = set(after) - set(before)
    print(f"  新出现帧: {len(new)}")
    for f in sorted(new)[:15]:
        print(f"    [{f}] ×{after.count(f)}")
    if new:
        print(f"  Bit位1占比分析:")
        for pos in range(7):
            ones = sum(1 for f in new if pos < len(f) and f[pos] == '1')
            es = sum(1 for f in new if pos < len(f) and f[pos] == 'E')
            p1 = ones/max(len(new),1)*100
            pe = es/max(len(new),1)*100
            flag = '⭐<-翻转位' if p1 > 30 else ''
            print(f"    bit{pos}: 1={p1:.0f}%  E={pe:.0f}% {flag}")

def main():
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    prefix = f"diff_{ts}"
    
    # 写ESP32脚本到本地
    esp_file = '/tmp/esp_batch_cap.py'
    with open(esp_file, 'w') as f:
        f.write(ESP_CODE)
    
    print("🎬 采集序列: 基线5s → 去按按钮(15s) → 恢复5s")
    result = subprocess.run(
        [MPREMOTE, '-m', 'mpremote', 'connect', PORT, 'run', esp_file],
        capture_output=True, timeout=90
    )
    print(result.stdout.decode(errors='replace'))
    if result.stderr:
        print(result.stderr.decode(errors='replace'))
    
    os.unlink(esp_file)
    
    # 下载
    print("\n📥 下载...")
    files = {}
    for fn in ['R00_baseline.txt', 'R01_op.txt', 'R02_post.txt']:
        local = os.path.join(DATA, f"{prefix}_{fn}")
        subprocess.run(
            [MPREMOTE, '-m', 'mpremote', 'connect', PORT, 'cp', f':{fn}', local],
            capture_output=True, timeout=10
        )
        if os.path.exists(local):
            files[fn] = read_raw(local)
            print(f"  {fn}: {len(files[fn])} edges")
        else:
            print(f"  {fn}: MISSING")
    
    # 分析
    print(f"\n🔍 差分分析")
    b_frames = extract_frames(files.get('R00_baseline.txt', []))
    o_frames = extract_frames(files.get('R01_op.txt', []))
    p_frames = extract_frames(files.get('R02_post.txt', []))
    
    diff("基线 vs 操作", b_frames, o_frames)
    diff("操作 vs 恢复", o_frames, p_frames)
    
    print(f"\n✅ 数据: data/{prefix}_*.txt")

if __name__ == '__main__':
    main()
