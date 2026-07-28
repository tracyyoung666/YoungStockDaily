#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render_overview.py · v4
数据驱动生成【自选股行情总览】亮色竖屏 PNG，手机微信友好。红涨绿跌。

用法：
  python3 render_overview.py --input overview_data.json --output images/daily_YYYYMMDD_HHMM.png

输入 JSON 格式（由 fetch_quotes.py 生成后简单包装）：
{
  "title": "自选股行情总览",
  "generated_at": "2026-05-01 19:02",
  "session": "盘前",                      // 或 "盘后"/"盘中"
  "session_label": "盘前",                // 也接受此字段
  "stocks": [
    {
      "symbol": "MU", "name": "美光科技",
      "close_price": 517.16,              // 或 "close": 517.16（兼容旧名）
      "pct_1d": -0.25,
      "extended_price": 507.75,           // 或 "premarket": 507.75（兼容旧名）
      "extended_pct": -1.82,              // 或 "premarket_pct": -1.82（兼容旧名）
      "dist_from_52w_high_pct": -3.42,    // 或 "dist_52w_high": -3.42（兼容旧名）
      "signals": ["日跌>4%"]              // 数组
    }, ...
  ]
}
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch, Rectangle
    from matplotlib import font_manager
except ImportError:
    sys.stderr.write('需要安装 matplotlib: pip install matplotlib\n')
    sys.exit(2)


# ---------- 中文字体 ----------
def setup_font():
    candidates = [
        'Noto Sans CJK SC', 'Noto Sans CJK JP', 'Noto Sans CJK TC',
        'Source Han Sans CN', 'Source Han Sans SC',
        'WenQuanYi Zen Hei', 'WenQuanYi Micro Hei',
        'PingFang SC', 'Microsoft YaHei', 'SimHei',
    ]
    installed = {f.name for f in font_manager.fontManager.ttflist}
    chosen = None
    for c in candidates:
        if c in installed:
            chosen = c
            break
    if chosen:
        plt.rcParams['font.family'] = ['sans-serif']
        plt.rcParams['font.sans-serif'] = [chosen, 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
    return chosen


# ---------- 配色 ----------
C = {
    'bg': '#f7f9fc',
    'card': '#ffffff',
    'alt': '#fafbfd',
    'border': '#dbe3ee',
    'text': '#1a2332',
    'sub': '#4a5568',
    'muted': '#8894a8',
    'blue': '#2563eb',
    'red': '#e03e3e',
    'green': '#16a34a',
    'orange': '#f59e0b',
    'fire': '#ef4444',
    'ok': '#10b981',
    'header_bg': '#eef2f8',
    # 左侧"异常等级条"专用中性色阶（刻意避开红/绿，防止与红涨绿跌混淆）
    'level_none': '#cbd5e1',   # 浅灰：无异常
    'level_warn': '#f59e0b',   # 琥珀：一般异常（量比/RSI极端/52周新高）
    'level_high': '#1d4ed8',   # 深蓝：重大异常（大幅波动 >4%）
}


def fmt_pct(v):
    if v is None:
        return '--'
    sign = '+' if v > 0 else ''
    return f'{sign}{v:.2f}%'


def color_pct(v):
    if v is None:
        return C['muted']
    return C['red'] if v > 0 else C['green'] if v < 0 else C['sub']


# ---------- 定投买卖点判定（与 SKILL.md 步骤 2.55 口径一致） ----------
# 五档标签与配色
ADV = {
    'strong_buy':  ('Strong Buy▲▲', '#b91c1c'),   # 深红：极端超卖/深度回撤，重仓抄底
    'buy':         ('定投Buy▲',      '#dc2626'),   # 红：常规定投买入
    'hold':        ('观望—',         '#6b7280'),   # 灰：信号中性
    'sell':        ('定投Sell▼',     '#16a34a'),   # 绿：常规定投卖出
    'strong_sell': ('Strong Sell▼▼', '#15803d'),  # 深绿：极端超买/破顶，重仓止盈
}


def advice_key(s):
    """返回五档 key：strong_buy / buy / hold / sell / strong_sell。"""
    # 若上游已算好标签，直接映射
    lbl = s.get('advice_key')
    if lbl in ADV:
        return lbl
    raw = s.get('advice_label') or s.get('advice')
    if raw:
        low = str(raw).lower()
        if 'strong' in low and ('buy' in low or '买' in raw):
            return 'strong_buy'
        if 'strong' in low and ('sell' in low or '卖' in raw):
            return 'strong_sell'
        if 'buy' in low or '买' in raw:
            return 'buy'
        if 'sell' in low or '卖' in raw:
            return 'sell'
        return 'hold'

    rsi = s.get('rsi6')
    d52h = s.get('dist_52w_high') if s.get('dist_52w_high') is not None else s.get('dist_from_52w_high_pct')
    pct1d = s.get('pct_1d')
    ext = s.get('extended_pct')
    if ext is None:
        ext = s.get('premarket_pct')
    if ext is None:
        ext = s.get('extended_pct_vs_close')
    vals = [x for x in (pct1d, ext) if x is not None]
    drop = -min(vals) if vals else None   # 最大跌幅（正数）
    rise = max(vals) if vals else None    # 最大涨幅

    if rsi is not None:
        # ---- 卖出侧（优先）----
        if rsi > 92:
            return 'strong_sell'
        if rsi > 85 and d52h is not None and d52h > -2:
            return 'strong_sell'
        if rsi > 85 and rise is not None and rise > 10:
            return 'strong_sell'
        if rsi > 85:
            return 'sell'
        if d52h is not None and d52h > -2 and rsi > 70:
            return 'sell'
        if rise is not None and rise > 10 and rsi > 75:
            return 'sell'
        # ---- 买入侧 ----
        if rsi < 12:
            return 'strong_buy'
        if rsi < 20 and d52h is not None and d52h < -30:
            return 'strong_buy'
        if rsi < 20 and drop is not None and drop > 6:
            return 'strong_buy'
        if d52h is not None and d52h < -40 and rsi < 30:
            return 'strong_buy'
        if rsi < 20:
            return 'buy'
        if d52h is not None and d52h < -20 and rsi < 45:
            return 'buy'
        if drop is not None and drop > 6 and rsi < 40:
            return 'buy'
        return 'hold'

    # ---- RSI 缺失：降级为纯价格判定（保守，不轻易发 Strong 档）----
    # ⚠️ 仅"距52周高点跌得深"不等于抄底良机——趋势崩坏的标的往往跌最深。
    #    因此纯价格判定下 Strong Buy 必须同时具备"深度回撤 + 当下恐慌下跌"。
    if d52h is not None and d52h < -40 and drop is not None and drop > 6:
        return 'strong_buy'
    if drop is not None and drop > 6:
        return 'buy'
    if d52h is not None and d52h < -20 and drop is not None and drop > 0:
        return 'buy'
    if d52h is not None and d52h > -2 and rise is not None and rise > 6:
        return 'strong_sell'
    if d52h is not None and d52h > -2:
        return 'sell'
    return 'hold'


def compute_advice(s):
    """返回 (label, color)。"""
    return ADV[advice_key(s)]


# ---------- 主渲染 ----------
def render(data, out_path):
    setup_font()

    stocks = data.get('stocks', [])
    if not stocks:
        print('[warn] stocks 数组为空，无数据可渲染')
        # 仍然生成一个空图避免报错

    session = data.get('session', '') or data.get('session_label', '')
    gen_at = data.get('generated_at', '')

    # 判断是盘前还是盘后还是盘中（决定列名）
    is_afterhours = '盘后' in session or 'After' in session
    is_realtime = '盘中' in session or 'realtime' in session.lower()
    ext_label = '盘后' if is_afterhours else ('盘中' if is_realtime else '盘前')

    # ====== 布局参数 ======
    W = 1090
    PAD_X = 36
    HEADER_H = 110
    TABLE_HEADER_H = 52
    ROW_H = 60
    FOOTER_H = 118          # 含三条精简投资铁律小字

    n_rows = len(stocks)
    table_h = TABLE_HEADER_H + ROW_H * n_rows
    H = HEADER_H + table_h + FOOTER_H + 20

    DPI = 100
    fig = plt.figure(figsize=(W / DPI, H / DPI), facecolor=C['bg'], dpi=DPI)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.invert_yaxis()
    ax.axis('off')

    y = 0

    # ===== 固定标题："自选股行情总览" =====
    y += 36
    ax.text(PAD_X, y, '■ 自选股行情总览',
            fontsize=22, fontweight='bold', color=C['blue'],
            va='top', ha='left')
    # 右侧副标题：时段 + 时间
    sub_text = f'{ext_label} · {gen_at}' if gen_at else ext_label
    ax.text(W - PAD_X, y + 8, sub_text,
            fontsize=13, color=C['muted'],
            va='top', ha='right')
    y = HEADER_H

    # ===== 表头 =====
    # 8 列布局：按内容宽度分配，代码列避开左侧色条，末列信号已精简文案故可收窄
    # 表格可用区 x ∈ [36, 1054]，色条占 36~43
    cols_x = [92, 196, 305, 415, 515, 618, 738, 900]
    cols_name = ['代码', '收盘价', '今日涨跌', f'{ext_label}价', f'{ext_label}%', '距52W高', '定投', '信号']

    ax.add_patch(FancyBboxPatch(
        (PAD_X, y), W - 2 * PAD_X, TABLE_HEADER_H,
        boxstyle='round,pad=0,rounding_size=8',
        linewidth=1, edgecolor=C['border'], facecolor=C['header_bg']))
    for name, cx in zip(cols_name, cols_x):
        ax.text(cx, y + TABLE_HEADER_H / 2, name,
                fontsize=13, fontweight='bold', color=C['text'],
                va='center', ha='center')
    y += TABLE_HEADER_H

    # ===== 数据行 =====
    for i, s in enumerate(stocks):
        row_y = y
        row_bg = C['alt'] if i % 2 == 0 else C['card']
        ax.add_patch(Rectangle((PAD_X, row_y), W - 2 * PAD_X, ROW_H,
                               facecolor=row_bg, edgecolor='none'))

        # 异常等级色条（中性色阶：浅灰=无异常 / 琥珀=一般异常 / 深蓝=重大波动）
        signals = s.get('signals', [])
        has_fire = any('>4%' in sig for sig in signals)
        has_warn = len(signals) > 0
        level_color = (C['level_high'] if has_fire
                       else (C['level_warn'] if has_warn else C['level_none']))
        ax.add_patch(Rectangle((PAD_X, row_y), 7, ROW_H,
                               facecolor=level_color, edgecolor='none'))

        # 底部分隔线
        ax.add_patch(Rectangle((PAD_X, row_y + ROW_H - 1),
                               W - 2 * PAD_X, 1,
                               facecolor=C['border'], edgecolor='none'))

        cy = row_y + ROW_H / 2

        # 1 代码
        ax.text(cols_x[0], cy, s.get('symbol', ''),
                fontsize=14, fontweight='bold', color=C['text'],
                va='center', ha='center')

        # 2 收盘价（兼容 close / close_price 两种字段名）
        close = s.get('close') or s.get('close_price')
        ax.text(cols_x[1], cy, f'${close:.2f}' if close else '--',
                fontsize=13, color=C['sub'], va='center', ha='center')

        # 3 今日涨跌
        pct_1d = s.get('pct_1d')
        ax.text(cols_x[2], cy, fmt_pct(pct_1d),
                fontsize=13, fontweight='bold', color=color_pct(pct_1d),
                va='center', ha='center')

        # 4 盘前/盘后价（兼容 premarket / extended_price）
        ext_price = s.get('premarket') or s.get('extended_price')
        ax.text(cols_x[3], cy, f'${ext_price:.2f}' if ext_price else '--',
                fontsize=13, fontweight='bold', color=C['text'],
                va='center', ha='center')

        # 5 盘前/盘后%（兼容 premarket_pct / extended_pct）
        ext_pct = s.get('premarket_pct') or s.get('extended_pct')
        ax.text(cols_x[4], cy, fmt_pct(ext_pct),
                fontsize=13, fontweight='bold', color=color_pct(ext_pct),
                va='center', ha='center')

        # 6 距52W高（兼容 dist_52w_high / dist_from_52w_high_pct）
        d52 = s.get('dist_52w_high') if s.get('dist_52w_high') is not None else s.get('dist_from_52w_high_pct')
        if d52 is not None and d52 > -0.5:
            d52_text, d52_color = '★新高', C['fire']
        elif d52 is not None:
            d52_text = f'{d52:.1f}%'
            d52_color = C['sub']
        else:
            d52_text, d52_color = '--', C['muted']
        ax.text(cols_x[5], cy, d52_text,
                fontsize=12, color=d52_color, va='center', ha='center')

        # 7 定投买卖建议
        adv_label, adv_color = compute_advice(s)
        ax.text(cols_x[6], cy, adv_label,
                fontsize=12, fontweight='bold', color=adv_color,
                va='center', ha='center')

        # 8 信号（精简文案：去掉括号内百分比，避免与"今日涨跌"列重复占宽）
        if signals:
            label = signals[0]
            label = re.sub(r'\s*\([^)]*\)', '', label)   # 去掉 (±X.XX%)
            label = (label.replace('日涨跌>4%', '波动>4%')
                          .replace('接近52w新高', '近52W高')
                          .replace('接近52W新高', '近52W高')
                          .replace('创52周新高', '52W新高')
                          .replace('创52周新低', '52W新低')
                          .replace('量比>2', '放量'))
            if len(signals) > 1:
                label += f'+{len(signals) - 1}'
            if len(label) > 11:
                label = label[:10] + '…'
        else:
            label = '正常'
        # 与色条同一套中性色阶：正常=浅灰字 / 一般异常=琥珀 / 重大波动=深蓝
        label_color = (C['level_high'] if has_fire
                       else (C['level_warn'] if has_warn else C['muted']))
        ax.text(cols_x[7], cy, label,
                fontsize=11, fontweight='bold', color=label_color,
                va='center', ha='center')

        y += ROW_H

    # ===== 底部：投资铁律（小字但红色醒目） + 免责声明 =====
    rules_top = HEADER_H + table_h + 18
    # 细分隔线
    ax.add_patch(Rectangle((PAD_X, rules_top), W - 2 * PAD_X, 1,
                           facecolor=C['border'], edgecolor='none'))
    ry = rules_top + 18
    ax.text(PAD_X + 4, ry, '⚠ 投资铁律',
            fontsize=9.5, fontweight='bold', color='#b91c1c',
            va='center', ha='left')
    IRON_RULES = [
        '连续冲高后回调 5% 必须开始止盈',
        '买入逻辑未按预期兑现，及时卖出',
        '小仓位打野同样必须止损，不可当价值股死扛',
    ]
    rx = PAD_X + 92
    for i, txt in enumerate(IRON_RULES):
        ax.text(rx, ry, f'{i + 1}. {txt}',
                fontsize=9.5, color='#dc2626', va='center', ha='left')
        ry += 17

    ax.text(W / 2, H - 20,
            "Young's Stock Daily · 仅为个人投资备忘，不构成投资建议",
            fontsize=10, color='#b8c0cc',
            va='center', ha='center')

    # ===== 保存 =====
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, facecolor=C['bg'], dpi=DPI,
                bbox_inches=None, pad_inches=0)
    plt.close(fig)
    print(f'[ok] rendered {out_path}  ({out_path.stat().st_size} bytes, {W}x{H}px)')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', required=True)
    ap.add_argument('--output', required=True)
    args = ap.parse_args()

    with open(args.input, encoding='utf-8') as f:
        data = json.load(f)
    render(data, args.output)


if __name__ == '__main__':
    main()
