#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render_overview.py · v3
数据驱动生成【自选股行情总览】亮色竖屏 PNG，手机微信友好。

用法：
  python3 render_overview.py --input overview_data.json --output images/daily_YYYYMMDD_HHMM.png

输入 JSON 格式（由 fetch_quotes.py 生成后简单包装）：
{
  "title": "自选股行情总览",            // 可选，默认"自选股行情总览"
  "generated_at": "2026-04-30 10:40",
  "session": "盘后 After-Hours",        // 盘前/盘后/常规
  "stocks": [
    {
      "symbol": "MU", "name": "美光科技",
      "close": 518.46, "pct_1d": 2.81,
      "premarket": 523.16, "premarket_pct": 0.91,   // 可为 null
      "dist_52w_high": -2.4, "volume_ratio": 1.19,
      "signals": ["盘后>4%(+4.24%)"]                // 数组
    }, ...
  ]
}
"""
import argparse
import json
import os
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


# ---------- 主渲染 ----------
def render(data, out_path):
    setup_font()

    stocks = data.get('stocks', [])
    if not stocks:
        print('[warn] stocks 数组为空，无数据可渲染')
        # 仍然生成一个空图避免报错

    session = data.get('session', '')
    gen_at = data.get('generated_at', '')

    # 判断是盘前还是盘后（决定列名）
    is_afterhours = '盘后' in session or 'After' in session
    ext_label = '盘后' if is_afterhours else '盘前'

    # ====== 布局参数 ======
    W = 1080
    PAD_X = 36
    HEADER_H = 110
    TABLE_HEADER_H = 52
    ROW_H = 60
    FOOTER_H = 52

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
    # 7 列布局
    cols_x = [80, 205, 360, 520, 680, 840, 985]
    cols_name = ['代码', '收盘价', '今日涨跌', f'{ext_label}价', f'{ext_label}%', '距52W高', '信号']

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

        # 信号等级色条
        signals = s.get('signals', [])
        has_fire = any('>4%' in sig for sig in signals)
        has_warn = len(signals) > 0
        level_color = C['fire'] if has_fire else (C['orange'] if has_warn else C['ok'])
        ax.add_patch(Rectangle((PAD_X, row_y), 6, ROW_H,
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

        # 2 收盘价
        close = s.get('close')
        ax.text(cols_x[1], cy, f'${close:.2f}' if close else '--',
                fontsize=13, color=C['sub'], va='center', ha='center')

        # 3 今日涨跌
        pct_1d = s.get('pct_1d')
        ax.text(cols_x[2], cy, fmt_pct(pct_1d),
                fontsize=13, fontweight='bold', color=color_pct(pct_1d),
                va='center', ha='center')

        # 4 盘前/盘后价
        ext_price = s.get('premarket')
        ax.text(cols_x[3], cy, f'${ext_price:.2f}' if ext_price else '--',
                fontsize=13, fontweight='bold', color=C['text'],
                va='center', ha='center')

        # 5 盘前/盘后%
        ext_pct = s.get('premarket_pct')
        ax.text(cols_x[4], cy, fmt_pct(ext_pct),
                fontsize=13, fontweight='bold', color=color_pct(ext_pct),
                va='center', ha='center')

        # 6 距52W高
        d52 = s.get('dist_52w_high')
        if d52 is not None and d52 > -0.5:
            d52_text, d52_color = '★新高', C['fire']
        elif d52 is not None:
            d52_text = f'{d52:.1f}%'
            d52_color = C['sub']
        else:
            d52_text, d52_color = '--', C['muted']
        ax.text(cols_x[5], cy, d52_text,
                fontsize=12, color=d52_color, va='center', ha='center')

        # 7 信号
        if signals:
            label = signals[0]
            if len(label) > 14:
                label = label[:13] + '…'
        else:
            label = '正常'
        label_color = C['fire'] if has_fire else (C['orange'] if has_warn else C['ok'])
        ax.text(cols_x[6], cy, label,
                fontsize=11, fontweight='bold', color=label_color,
                va='center', ha='center')

        y += ROW_H

    # ===== 底部 =====
    ax.text(W / 2, H - 22,
            "Young's Stock Daily · 仅为个人投资备忘，不构成投资建议",
            fontsize=10.5, color=C['muted'],
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
