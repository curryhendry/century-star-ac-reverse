#!/usr/bin/env python3
"""空调协议解码 - 以E脉冲为帧锚点的系统性分析"""
import re, sys
from collections import Counter

def classify(hw):
    if hw < 700: return '0'
    if hw < 1200: return '1'
    if hw < 1600: return 'E'
    if hw >= 4000: return 'F'
    return '?'

def load_pulses(path):
    data=[]
    with open(path) as f:
        for l in f:
            m=re.match(r'(\d+)\s+([01])',l.strip())
            if m: data.append((int(m.group(1)),int(m.group(2))))
    pulses=[]
    for j in range(1,len(data)):
        if data[j-1][1]==1 and data[j][1]==0:
            hw=data[j][0]-data[j-1][0]
            pulses.append((data[j][0],hw,classify(hw)))
    return pulses

def extract_frames(pulses):
    """按F脉冲切帧"""
    frames,cur=[],[]
    for t,hw,s in pulses:
        if s=='F':
            if cur: frames.append((cur[0][0],cur))
            cur=[]
        else: cur.append((t,hw,s))
    if cur: frames.append((cur[0][0],cur))
    return frames

def strip_e(bits_list):
    """剥离E，只留0/1"""
    return [(t,hw,s) for t,hw,s in bits_list if s in '01']

# ===== 分析 TEMP+ vs TEMP- =====
print('='*70)
print('  TEMP+ vs TEMP- — 以E为锚点的帧结构分析')
print('='*70)

datadir='/Users/guoli/Projects/century-star-ac-reverse/data'
tp_pulses=load_pulses(f'{datadir}/tempplus.txt')
tm_pulses=load_pulses(f'{datadir}/tempminus.txt')

tp_frames=extract_frames(tp_pulses)
tm_frames=extract_frames(tm_pulses)

# TEMP+帧的E脉冲位置模式
print('\n=== TEMP+ 帧E脉冲分布（最高温基准）===')
tp_e_frames=[]
for t,f in tp_frames:
    bits=''.join(s for _,_,s in f)
    if 'E' in bits:
        epos=[i for i,c in enumerate(bits) if c=='E']
        pure01=''.join(s for _,_,s in f if s in '01')
        tp_e_frames.append((t/1000,bits,len(bits),epos,pure01))
        if len(tp_e_frames)<=15:
            print(f'  @{t/1000:6.0f}ms [{bits:10s}] sz={len(bits):2d} E@{epos} 01=[{pure01}]')

# E轮转统计
tp_epos_seq=[epos for _,_,_,epos,_ in tp_e_frames]
print(f'\n  TEMP+ E轮转: {tp_epos_seq}')
print(f'  全零: {all(len(p)==0 for _,_,_,_,p in tp_e_frames if len(p)>0)}')

# TEMP-帧的E脉冲分布
print('\n=== TEMP- 帧E脉冲分布 ===')
tm_e_frames=[]
for t,f in tm_frames:
    bits=''.join(s for _,_,s in f)
    if 'E' in bits and any(s in '01' for _,_,s in f):
        epos=[i for i,c in enumerate(bits) if c=='E']
        pure01=''.join(s for _,_,s in f if s in '01')
        tm_e_frames.append((t/1000,bits,len(bits),epos,pure01))

# 按E位置分组
from collections import defaultdict
by_epos=defaultdict(list)
for t,bits,sz,epos,pure01 in tm_e_frames:
    key=tuple(epos)
    by_epos[key].append((t,sz,pure01))

print('\n  按E位置分组:')
for epos,frames in sorted(by_epos.items()):
    pure01_samples=[p for _,_,p in frames[:5]]
    print(f'  E@{list(epos)}: {len(frames)}帧, 样本01={pure01_samples}')

# ===== 核心结论：E是3行扫描标记 =====
# 假设: pos0=E → 扫描行0, pos3=E → 扫描行1, pos5=E → 扫描行2
# 每行扫描期间，其他6个位置是数据位（6位×3行=18位状态寄存器）

print('\n' + '='*70)
print('  模型: E = 3行扫描标记(pos0/3/5轮转)')
print('  每行6个数据位(非E位置) → 6x3=18位状态寄存器')
print('='*70)

# TEMP+: 所有行数据位=0 → 18位全零 = 最高温
# TEMP-: 行数据位有1 → 18位中有非零值 = 较低温

# 验证：找TEMP-中E@pos3的帧，提取数据位
print('\n=== TEMP-: E@[3] 帧的数据位 ===')
count=0
for t,f in tm_frames:
    bits=[s for _,_,s in f]
    if len(bits)==7 and bits[3]=='E':
        row_data=[bits[i] for i in [0,1,2,4,5,6]]
        pure=''.join(c for c in row_data if c in '01')
        count+=1
        if count<=10:
            print(f'  @{t/1000:6.0f}ms [{pure}]')

print(f'\n  共{count}个E@[3]帧')

# ===== 按扫描行对齐后提取18位 =====
print('\n=== 尝试提取完整18位状态字 ===')
# 收集三行数据
rows={0:[],3:[],5:[]}
for t,f in tm_frames:
    bits=[s for _,_,s in f]
    for e_pos in [0,3,5]:
        if len(bits)==7 and e_pos < len(bits) and bits[e_pos]=='E':
            row_data=[bits[i] for i in range(7) if i!=e_pos]
            row_bits=''.join(c for c in row_data if c in '01')
            if len(row_bits)==6:
                rows[e_pos].append((t/1000,row_bits))

for pos in [0,3,5]:
    print(f'  行{pos}: {len(rows[pos])}帧')
    if rows[pos]:
        # 看最常见的值
        vals=[v for _,v in rows[pos]]
        for v,c in Counter(vals).most_common(5):
            print(f'    [{v}] ×{c}')

# ===== TEMP+ 18位全零验证 =====
print('\n=== TEMP+: 验证18位全零 ===')
for pos in [0,3,5]:
    rows_tp={pos:[]}
    for t,f in tp_frames:
        bits=[s for _,_,s in f]
        if len(bits)==7 and pos < len(bits) and bits[pos]=='E':
            row_data=[bits[i] for i in range(7) if i!=pos]
            row_bits=''.join(c for c in row_data if c in '01')
            if len(row_bits)==6:
                rows_tp[pos].append((t/1000,row_bits))
    vals=[v for _,v in rows_tp[pos]]
    if vals:
        unique=set(vals)
        print(f'  行{pos}: {len(vals)}帧, 唯一值={unique}')
    else:
        print(f'  行{pos}: 无有效帧')
