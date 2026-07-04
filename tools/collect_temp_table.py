#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
空调温度编码表采集 — 双击运行
逐级采集17°C→24°C（按TEMP+升1度→等稳定→采5秒idle），自动分析
"""

import os, sys, subprocess, datetime, re, time

DOWNLOADS = os.path.expanduser("~/Downloads")
DATA_DIR = os.path.join(DOWNLOADS, "空调温度编码")
os.makedirs(DATA_DIR, exist_ok=True)

# ESP32 上传码
ESP_CODE = '''
from machine import Pin
import time
pin=Pin(33,Pin.IN)
f=open("btn_cap.txt","w")
prev=pin.value()
start=time.ticks_us()
changes=0
deadline=time.ticks_add(start,5000000)
while time.ticks_diff(time.ticks_us(),deadline)<0:
    v=pin.value()
    if v!=prev:
        now=time.ticks_diff(time.ticks_us(),start)
        f.write(str(now)+" "+str(v)+"\\n")
        prev=v
        changes+=1
f.close()
print("CAP_OK",changes)
'''

PYTHON = "/Users/guoli/Library/Application Support/QClaw/openclaw/config/bin/python/python3"
PORT = "/dev/cu.wchusbserial141200"


def log(msg):
    now = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] {msg}")


def mpremote(cmd, timeout=15):
    r = subprocess.run([PYTHON, "-m", "mpremote", "connect", PORT] + cmd.split(),
                       capture_output=True, text=True, timeout=timeout)
    return r.stdout.strip(), r.stderr.strip()


def check_esp32():
    out, err = mpremote("exec print('OK')", timeout=5)
    return "OK" in out


def upload_code():
    esp_file = os.path.join(DOWNLOADS, "_esp_temp_idle.py")
    with open(esp_file, "w") as f:
        f.write(ESP_CODE)
    out, err = mpremote(f"fs cp {esp_file} :_esp_temp_idle.py")
    os.remove(esp_file)
    return "cp" in out


def run_collect():
    out, err = mpremote("run /tmp或项目用的临时文件" + ".py", timeout=15)  # placeholder
    # Actually use run
    out, _ = mpremote("run " + os.path.join(DOWNLOADS, "_esp_temp_idle.py"), timeout=15)
    return out


def collect_one(label, filename):
    """采集一次5秒idle"""
    log(f"上传到ESP32...")
    if not upload_code():
        log("❌ 上传失败")
        return None
    
    log(f"采集 {label} — 等5秒...")
    
    esp_file = os.path.join(DOWNLOADS, "_esp_temp_idle.py")
    out, err = subprocess.run([PYTHON, "-m", "mpremote", "connect", PORT, "run", f"/Users/guoli/Library/Application Support/QClaw/openclaw/config/bin/python/python3"], 
                              capture_output=True, text=True, timeout=15)
    
    # Do it right
    with open(os.path.join(DOWNLOADS, "_esp_temp_idle.py"), "w") as f:
        f.write(ESP_CODE)
    
    out, err = mpremote("run " + os.path.join(DOWNLOADS, "_esp_temp_idle.py"), timeout=15)
    log(f"捕获完成: {out}")
    
    # 下载数据
    target = os.path.join(DATA_DIR, filename)
    cmd = f"fs cp :btn_cap.txt {target}"
    out, err = mpremote(cmd, timeout=10)
    
    if os.path.exists(target):
        lines = 0
        with open(target) as f:
            lines = sum(1 for _ in f)
        log(f"✅ {label} → {filename} ({lines}行) 已存 {DATA_DIR}")
        return target
    else:
        log(f"❌ 下载失败")
        return None


def analyze(filepath):
    """分析单文件：提取比特流"""
    d = []
    with open(filepath) as f:
        for l in f:
            m = re.match(r'(\d+)\s+([01])', l.strip())
            if m: d.append((int(m.group(1)), int(m.group(2))))
    bits = []
    for j in range(1, len(d)):
        if d[j-1][1] == 1 and d[j][1] == 0:
            hw = d[j][0] - d[j-1][0]
            if hw < 1200:
                bits.append(('0' if hw < 700 else '1'))
    s = ''.join(bits)
    # 统计0/1比例，最常见6位片段
    from collections import Counter
    chunks6 = [s[i:i+6] for i in range(0, len(s)-5)]
    top6 = Counter(chunks6).most_common(3)
    return {
        'total': len(bits),
        'ones': s.count('1'),
        'ratio': s.count('1') / max(len(s), 1) * 100,
        'top6': top6,
        'stream': s
    }


# ═══ 主流程 ═══
def main():
    print("=" * 60)
    print("  空调温度编码表采集工具")
    print("  逐级采集 17°C → 24°C idle 比特流")
    print("=" * 60)
    print()
    
    if not check_esp32():
        print("❌ ESP32 未连接")
        print("  请检查: 1) USB线 2) 驱动 3) 端口 /dev/cu.wchusbserial141200")
        print()
        input("按回车退出...")
        sys.exit(1)
    
    print("✅ ESP32 已连接")
    print()
    print("操作说明：")
    print("  1. 确保面板当前显示温度")
    print("  2. 本工具会引导你逐级按 TEMP+ 升1度")
    print("  3. 按后等面板稳定（不闪），按回车继续")
    print("  4. 工具自动采集5秒idle信号")
    print("  5. 重复直到24°C")
    print()
    print(f"数据保存在 {DATA_DIR}")
    print()
    print("按回车开始...")
    try:
        input()
    except EOFError:
        pass
    
    results = {}
    temp_labels = ["17C", "18C", "19C", "20C", "21C", "22C", "23C", "24C"]
    
    for i, label in enumerate(temp_labels):
        if i == 0:
            log(f"假设面板当前是 {label}，开始采集...")
        else:
            log(f"请按 TEMP+ 升到 {label}（按1次），等面板稳定（不闪）")
            log("按回车继续...")
            try:
                input()
            except EOFError:
                pass
        
        fname = f"temp_{label}_{datetime.datetime.now().strftime('%m%d_%H%M%S')}.txt"
        path = collect_one(label, fname)
        if path:
            r = analyze(path)
            results[label] = r
            log(f"  分析: {r['total']}位, 1占比={r['ratio']:.1f}%")
            log(f"  Top6: {r['top6']}")
        print()
    
    # ═══ 最终报告 ═══
    print()
    print("=" * 60)
    print("  编码对比报告")
    print("=" * 60)
    print()
    print(f"{'温度':>6} {'总位数':>6} {'1占比':>8} {'最常见6位码'}")
    print("-" * 50)
    for label in temp_labels:
        if label in results:
            r = results[label]
            top = r['top6'][0][0] if r['top6'] else '—'
            print(f"{label:>6} {r['total']:>6} {r['ratio']:>7.1f}% {top}")
    
    stream_file = os.path.join(DATA_DIR, "全部比特流.txt")
    with open(stream_file, "w") as f:
        f.write("温度编码比特流 (5秒idle每级)\n")
        f.write("=" * 50 + "\n\n")
        for label in temp_labels:
            if label in results:
                r = results[label]
                f.write(f"\n[{label}] {r['total']}位, 1占比={r['ratio']:.1f}%\n")
                f.write(r['stream'] + "\n")
    log(f"📄 完整比特流 → {stream_file}")
    
    report_file = os.path.join(DATA_DIR, "采集报告.txt")
    with open(report_file, "w") as f:
        f.write(f"采集时间: {datetime.datetime.now()}\n")
        f.write(f"{'温度':>6} {'总位数':>6} {'1占比':>8} {'最常见6位码'}\n")
        f.write("-" * 50 + "\n")
        for label in temp_labels:
            if label in results:
                r = results[label]
                top = r['top6'][0][0] if r['top6'] else '—'
                f.write(f"{label:>6} {r['total']:>6} {r['ratio']:>7.1f}% {top}\n")
    
    print()
    log("✅ 完成")
    log(f"报告 → {report_file}")
    print()
    try:
        input("按回车退出...")
    except EOFError:
        pass


if __name__ == "__main__":
    main()
