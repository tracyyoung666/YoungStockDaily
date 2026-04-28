#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render_overview.py
读取 overview_data JSON，渲染【异常信号总览 + 组合总结 + 行动清单】竖版手机友好 PNG（亮色系）。

用法：
  python3 render_overview.py --input overview_data.json --output images/YYYY-MM-DD.png

JSON schema 见技能 references/data-schemas.md#overview_data。
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
    from matplotlib.patches import FancyBboxPatch
except ImportError:
    sys.stderr.write('需要安装 matplotlib: pip install matplotlib\n')
    sys.exit(2)


# ---------- 字体（中文 + 符号兜底） ----------
def setup_font():
    candidates = [
        'Noto Sans CJK SC', 'Noto Sans CJK JP',
        'Source Han Sans CN', 'WenQuanYi Zen Hei',
        'PingFang SC', 'Microsoft YaHei',
        'DejaVu Sans',
    ]
    from matplotlib import font_manager
    installed = {f.name for f in font_manager.fontManager.ttflist}
    for c in candidates:
        if c in installed:
            plt.rcParams['font.sans-serif'] = [c, 'DejaVu Sans']
            break
    plt.rcParams['axes.unicode_minus'] = False


COLORS = {
    'bg': '#f7f9fc',
    'card': '#ffffff',
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
}

SIGNAL_COLORS = {'fire': COLORS['fire'], 'warn': COLORS['orange'], 'ok': COLORS['ok']}
SIGNAL_EMOJI = {'fire': '▲', 'warn': '!', 'ok': '✓'}


def fmt_pct(v):
    if v is None:
        return '--'
    sign = '+' if v > 0 else ''
    return f'{sign}{v:.2f}%'


def color_for_change(v):
    if v is None:
        return COLORS['muted']
    return COLORS['green'] if v < 0 else COLORS['red']


def render(data, out_path):
    setup_font()

    rows = data.get('rows', [])
    summary = data.get('portfolio_summary', [])
    actions = data.get('action_list', [])
    phase = data.get('phase', '盘前')
    date = data.get('date', '')

    # 高度估算：头部 120 + 每行 52 + 总结 (行数*30+60) + 行动 (行数*34+80) + 底部 60
    row_h = 0.48
    base_h = 2.1
    total_h = base_h + len(rows) * row_h + len(summary) * 0.32 + len(actions) * 0.38

    fig = plt.figure(figsize=(10, total_h), facecolor=COLORS['bg'], dpi=130)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, total_h * 10)
    ax.axis('off')

    y_cursor = total_h * 10

    # ---------- 标题卡片 ----------
    y_cursor -= 1.2
    ax.text(5, y_cursor, f'📈 自选股行情 · {phase}总览', fontsize=19,
            fontweight='bold', color=COLORS['text'], va='center')
    y_cursor -= 0.8
    ax.text(5, y_cursor, date, fontsize=12, color=COLORS['muted'], va='center')

    y_cursor -= 1.0

    # ---------- 表头 ----------
    header_y = y_cursor
    header = FancyBboxPatch((3, header_y - 0.5), 94, 1.0,
                             boxstyle='round,pad=0.0,rounding_size=0.4',
                             linewidth=1, edgecolor=COLORS['border'],
                             facecolor='#eef2f8', zorder=1)
    ax.add_patch(header)
    cols = [
        ('代码', 8),
        ('昨收', 22),
        ('昨涨跌', 38),
        ('盘前价', 52),
        ('盘前%', 66),
        ('距52W高', 80),
        ('信号', 92),
    ]
    for text, x in cols:
        ax.text(x, header_y, text, fontsize=11, color=COLORS['text'],
                fontweight='bold', ha='center', va='center')
    y_cursor -= 1.2

    # ---------- 每行 ----------
    for i, r in enumerate(rows):
        row_y = y_cursor
        # 背景（交替）
        bg_color = '#fafbfd' if i % 2 == 0 else '#ffffff'
        ax.add_patch(FancyBboxPatch((3, row_y - 0.32), 94, 0.9,
                                     boxstyle='round,pad=0.0,rounding_size=0.25',
                                     linewidth=0, facecolor=bg_color, zorder=1))
        # 左色条（信号级别）
        level = r.get('signal_level', 'ok')
        ax.add_patch(plt.Rectangle((3, row_y - 0.32), 0.8, 0.9,
                                    facecolor=SIGNAL_COLORS.get(level, COLORS['ok']),
                                    linewidth=0, zorder=2))

        sym = r.get('symbol', '')
        ax.text(8, row_y, sym, fontsize=12, color=COLORS['text'],
                fontweight='bold', ha='center', va='center')

        pc = r.get('prev_close')
        ax.text(22, row_y, f"${pc:.2f}" if pc else '--', fontsize=11,
                color=COLORS['sub'], ha='center', va='center')

        pcp = r.get('prev_change_pct')
        ax.text(38, row_y, fmt_pct(pcp), fontsize=11,
                color=color_for_change(pcp), fontweight='bold',
                ha='center', va='center')

        pm = r.get('premarket_price')
        ax.text(52, row_y, f"${pm:.2f}" if pm else '--', fontsize=11,
                color=COLORS['text'], fontweight='bold',
                ha='center', va='center')

        pmp = r.get('premarket_change_pct')
        ax.text(66, row_y, fmt_pct(pmp), fontsize=11,
                color=color_for_change(pmp), fontweight='bold',
                ha='center', va='center')

        d52 = r.get('dist_52w_high_pct')
        d52_text = '新高' if d52 is not None and abs(d52) < 0.1 else (fmt_pct(d52) if d52 is not None else '--')
        d52_color = COLORS['red'] if d52 is not None and abs(d52) < 0.1 else COLORS['sub']
        ax.text(80, row_y, d52_text, fontsize=11, color=d52_color,
                ha='center', va='center')

        label = r.get('signal_label', '')
        ax.text(92, row_y, label, fontsize=10, color=SIGNAL_COLORS.get(level, COLORS['sub']),
                fontweight='bold', ha='center', va='center')

        y_cursor -= row_h

    y_cursor -= 0.4

    # ---------- 组合总结 ----------
    if summary:
        ax.text(5, y_cursor, '📊 组合层面总结', fontsize=14,
                fontweight='bold', color=COLORS['text'], va='center')
        y_cursor -= 0.5
        # 卡片底色
        card_top = y_cursor + 0.2
        card_h = len(summary) * 0.32 + 0.4
        ax.add_patch(FancyBboxPatch((3, card_top - card_h), 94, card_h,
                                     boxstyle='round,pad=0.0,rounding_size=0.4',
                                     linewidth=1, edgecolor=COLORS['border'],
                                     facecolor=COLORS['card'], zorder=1))
        y_cursor -= 0.1
        for s in summary:
            ax.text(6, y_cursor, f'• {s}', fontsize=11,
                    color=COLORS['sub'], va='center')
            y_cursor -= 0.32
        y_cursor -= 0.3

    # ---------- 行动清单 ----------
    if actions:
        ax.text(5, y_cursor, '🎯 开盘前行动清单', fontsize=14,
                fontweight='bold', color=COLORS['text'], va='center')
        y_cursor -= 0.5
        card_top = y_cursor + 0.2
        card_h = len(actions) * 0.38 + 0.4
        ax.add_patch(FancyBboxPatch((3, card_top - card_h), 94, card_h,
                                     boxstyle='round,pad=0.0,rounding_size=0.4',
                                     linewidth=1, edgecolor=COLORS['border'],
                                     facecolor=COLORS['card'], zorder=1))
        y_cursor -= 0.1
        action_color = {
            '减仓': COLORS['fire'], '卖出': COLORS['fire'],
            '加仓': COLORS['green'], '建仓': COLORS['green'], '买入': COLORS['green'],
            '观望': COLORS['orange'], '持有': COLORS['blue'],
        }
        for a in actions:
            act = a.get('action', '')
            tgt = a.get('target', '')
            det = a.get('detail', '')
            col = action_color.get(act, COLORS['sub'])
            ax.text(6, y_cursor, f'[{act}]', fontsize=11,
                    color=col, fontweight='bold', va='center')
            ax.text(16, y_cursor, tgt, fontsize=11,
                    color=COLORS['text'], fontweight='bold', va='center')
            ax.text(26, y_cursor, det, fontsize=10.5,
                    color=COLORS['sub'], va='center')
            y_cursor -= 0.38
        y_cursor -= 0.2

    # ---------- 底部 ----------
    ax.text(50, 0.3, 'Young\'s Stock Daily · 仅为个人投资备忘', fontsize=9,
            color=COLORS['muted'], ha='center', va='center')

    # 保存
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, facecolor=COLORS['bg'], dpi=130,
                bbox_inches=None, pad_inches=0)
    plt.close(fig)
    print(f'[ok] rendered {out_path}  ({out_path.stat().st_size} bytes)')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', required=True, help='overview_data.json')
    ap.add_argument('--output', required=True, help='output png path')
    args = ap.parse_args()

    with open(args.input, encoding='utf-8') as f:
        data = json.load(f)
    render(data, args.output)


if __name__ == '__main__':
    main()
