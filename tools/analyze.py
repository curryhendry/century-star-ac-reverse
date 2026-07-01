# analyze.py — 世纪星空调协议统一分析器
# 用法：
#   单文件: py analyze.py data/idle.txt
#   多文件对比: py analyze.py data/idle.txt data/mode.txt data/tempplus.txt
# 分析内容：脉冲分类(0/1/E/F) → 7-bit帧结构 → 二维符号统计 → 跨文件对比

import sys, os
from collections import Counter, defaultdict

# ═══════════════════════════════════════════════════
# 脉冲宽度阈值（微秒）
# ═══════════════════════════════════════════════════
THRESHOLDS = {
    '0': (0, 700),       # ~485μs
    '1': (800, 1200),    # ~975μs
    'E': (1200, 1600),   # 第三态/行扫描标记
    'F': (4000, None),   # 帧心跳分隔符
}

# 二维符号分档
H_BUCKETS = [('a', 0, 600), ('b', 600, 800), ('c', 800, 1100),
             ('d', 1100, 1500), ('e', 1500, 4000), ('f', 4000, float('inf'))]
L_BUCKETS = [('1', 0, 400), ('2', 400, 600), ('3', 600, 1000),
             ('4', 1000, 2000), ('5', 2000, 5000), ('6', 5000, 10000),
             ('7', 10000, float('inf'))]

# ═══════════════════════════════════════════════════
# 数据读取
# ═══════════════════════════════════════════════════
def read_raw(filepath):
    """读取边沿捕获文件（格式: timestamp_us value）"""
    data = []
    with open(filepath, encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            data.append((int(parts[0]), int(parts[1])))
    return data

# ═══════════════════════════════════════════════════
# 脉冲分类
# ═══════════════════════════════════════════════════
def classify_pulse(hw):
    """将脉宽分类为 0/1/E/F/?"""
    if hw < 700:
        return '0'
    elif hw < 1200:
        return '1'
    elif hw < 1600:
        return 'E'
    elif hw >= 4000:
        return 'F'
    return '?'

def extract_pulses(data):
    """从边沿数据提取脉冲列表 (相对时间ms, 类别, 脉宽μs, 紧随的LOW间隔μs)"""
    pulses = []
    start_us = data[0][0]
    n = len(data)
    for j in range(1, n):
        if data[j-1][1] == 1 and data[j][1] == 0:
            hw = data[j][0] - data[j-1][0]  # HIGH宽度
            lw = 0
            if j+1 < n and data[j][1] == 0 and data[j+1][1] == 1:
                lw = data[j+1][0] - data[j][0]  # LOW间隔
            rel_ms = (data[j-1][0] - start_us) / 1000
            cls = classify_pulse(hw)
            pulses.append((rel_ms, cls, hw, lw))
    return pulses

# ═══════════════════════════════════════════════════
# 二维符号
# ═══════════════════════════════════════════════════
def bucket_2d(hw, lw):
    """(HIGH宽度, LOW间隔) → 二维符号如 a2, f5"""
    hb = '?'
    for name, lo, hi in H_BUCKETS:
        if lo <= hw < hi:
            hb = name
            break
    lb = '?'
    for name, lo, hi in L_BUCKETS:
        if lo <= lw < hi:
            lb = name
            break
    return hb + lb

# ═══════════════════════════════════════════════════
# 单文件分析
# ═══════════════════════════════════════════════════
def analyze_one(filepath):
    """对单个捕获文件做全分析，返回结构化结果"""
    data = read_raw(filepath)
    pulses = extract_pulses(data)
    
    result = {'label': os.path.basename(filepath).replace('.txt', ''),
              'total_pulses': len(pulses)}
    
    # --- 脉冲类型分布 ---
    type_counts = Counter(cls for _, cls, _, _ in pulses)
    result['type_counts'] = type_counts
    
    # --- 7-bit帧 ---
    data_bits = [cls for _, cls, _, _ in pulses if cls in '01E']
    groups_7 = []
    i = 0
    while i + 7 <= len(data_bits):
        groups_7.append(''.join(data_bits[i:i+7]))
        i += 7
    result['groups_7'] = groups_7
    result['n_groups_7'] = len(groups_7)
    
    gc = Counter(groups_7)
    result['unique_7bit'] = len(gc)
    result['top_patterns'] = gc.most_common(10)
    
    # E位置分布
    epos = Counter()
    for pat in groups_7:
        for idx, ch in enumerate(pat):
            if ch == 'E':
                epos[idx] += 1
    result['e_positions'] = epos
    
    # 纯数据帧（无E）
    pure = [p for p in groups_7 if 'E' not in p]
    result['pure_frames'] = pure
    result['n_pure'] = len(pure)
    
    # 全零帧
    result['all_zero'] = gc.get('0000000', 0)
    result['has_1'] = any('1' in p for p in groups_7)
    
    # --- 二维符号 ---
    symbols_2d = []
    for _, cls, hw, lw in pulses:
        symbols_2d.append(bucket_2d(hw, lw))
    sc = Counter(symbols_2d)
    result['symbols_2d'] = symbols_2d
    result['unique_symbols'] = len(sc)
    result['top_symbols'] = sc.most_common(10)
    result['dominance'] = sum(c for _, c in sc.most_common(3)) / len(symbols_2d) * 100 if symbols_2d else 0
    
    return result

# ═══════════════════════════════════════════════════
# 格式化输出
# ═══════════════════════════════════════════════════
def print_result(r):
    """打印单个文件分析结果"""
    label = r['label']
    total = r['total_pulses']
    tc = r['type_counts']
    
    print(f"\n{'='*60}")
    print(f"  {label}（{total} 个脉冲）")
    print(f"{'='*60}")
    
    # 脉冲类型
    print(f"\n  脉冲类型:")
    for t in ['0', '1', 'E', 'F']:
        c = tc.get(t, 0)
        print(f"    {t}: {c:5d} ({c/total*100:5.1f}%)")
    
    # 7-bit帧
    groups = r['groups_7']
    print(f"\n  7-bit帧: {r['n_groups_7']} 个, {r['unique_7bit']} 种")
    
    if r['top_patterns']:
        print(f"  Top 10:")
        for pat, cnt in r['top_patterns']:
            pct = cnt / len(groups) * 100 if groups else 0
            bar = '█' * int(pct/2)
            epos_str = ','.join(str(i) for i,b in enumerate(pat) if b=='E')
            note = f"  E@{epos_str}" if epos_str else ""
            print(f"    [{pat}] ×{cnt:3d} ({pct:5.1f}%) {bar}{note}")
    
    # E位置
    if r['e_positions']:
        print(f"\n  E脉冲位置:")
        for pos in range(7):
            c = r['e_positions'].get(pos, 0)
            pct = c / len(groups) * 100 if groups else 0
            print(f"    pos{pos}: {c:3d} ({pct:5.1f}%)  {'█'*int(pct/2)}")
    
    # 纯数据帧
    pure = r['pure_frames']
    if pure:
        pc = Counter(pure)
        print(f"\n  纯数据帧（无E）: {r['n_pure']} 个, {len(pc)} 种")
        for pat, cnt in pc.most_common(5):
            print(f"    [{pat}] ×{cnt}")
    
    # 二维符号
    print(f"\n  二维符号: {r['unique_symbols']} 种 (集中度 {r['dominance']:.0f}%)")
    print(f"  Top 5:")
    for sym, cnt in r['top_symbols'][:5]:
        if len(sym) < 2: continue
        pct = cnt / len(r['symbols_2d']) * 100
        bar = '█' * int(pct/2)
        h_name = {'a':'短','b':'较短','c':'中','d':'长','e':'特长','f':'极长','?':'?'}
        l_name = {'1':'极紧','2':'紧','3':'近','4':'中','5':'宽','6':'长','7':'极稀','?':'?'}
        print(f"    {sym} ({h_name.get(sym[0],'?')}+{l_name.get(sym[1],'?')}): {cnt:4d} ({pct:5.1f}%) {bar}")
    
    # 总结
    print(f"\n  总结:")
    print(f"    全零帧(0000000): {r['all_zero']}/{r['n_groups_7']}")
    print(f"    含数据位(1):    {'是' if r['has_1'] else '否（全零/仅E）'}")

def print_cross_comparison(results):
    """跨文件对比"""
    if len(results) < 2:
        return
    
    print(f"\n{'='*60}")
    print(f"  跨文件对比")
    print(f"{'='*60}")
    
    # 脉冲类型对比
    print(f"\n  脉冲类型分布对比:")
    print(f"  {'标签':<10} {'0':>6} {'1':>6} {'E':>6} {'F':>6}")
    for r in results:
        tc = r['type_counts']
        total = r['total_pulses']
        print(f"  {r['label']:<10} {tc.get('0',0)/total*100:5.1f}% {tc.get('1',0)/total*100:5.1f}% "
              f"{tc.get('E',0)/total*100:5.1f}% {tc.get('F',0)/total*100:5.1f}%")
    
    # 7-bit帧唯一性对比
    print(f"\n  7-bit帧概况:")
    print(f"  {'标签':<10} {'总帧数':>6} {'唯一帧':>6} {'纯数据':>6} {'全零':>6}")
    for r in results:
        print(f"  {r['label']:<10} {r['n_groups_7']:>6} {r['unique_7bit']:>6} "
              f"{r['n_pure']:>6} {r['all_zero']:>6}")
    
    # 二维符号对比
    print(f"\n  二维符号概况:")
    print(f"  {'标签':<10} {'符号种数':>8} {'集中度':>8}  Top1")
    for r in results:
        top1 = r['top_symbols'][0][0] if r['top_symbols'] else '?'
        print(f"  {r['label']:<10} {r['unique_symbols']:>8} {r['dominance']:>7.0f}%  {top1}")
    
    # 共通纯数据帧
    pure_sets = {r['label']: set(r['pure_frames']) for r in results}
    labels = list(pure_sets.keys())
    if len(labels) >= 2:
        shared = pure_sets[labels[0]] & pure_sets[labels[1]]
        if shared:
            print(f"\n  {labels[0]} & {labels[1]} 共通帧: {len(shared)}")
            for f in sorted(shared)[:10]:
                print(f"    [{f}]")

# ═══════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════
if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法:")
        print("  单文件: py analyze.py <捕获文件>")
        print("  多文件: py analyze.py <文件1> <文件2> ...")
        print("  示例:   py analyze.py data/idle.txt")
        print("          py analyze.py data/idle.txt data/mode.txt data/tempplus.txt")
        sys.exit(1)
    
    files = sys.argv[1:]
    results = []
    
    for fp in files:
        if not os.path.isfile(fp):
            print(f"⚠ 文件不存在: {fp}")
            continue
        r = analyze_one(fp)
        results.append(r)
        print_result(r)
    
    if len(results) >= 2:
        print_cross_comparison(results)
