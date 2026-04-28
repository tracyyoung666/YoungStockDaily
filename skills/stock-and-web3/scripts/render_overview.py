#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render_overview.py · v2（修复版）
数据驱动生成【异常信号总览 + 组合总结 + 行动清单】亮色竖屏 PNG，手机微信友好。

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
    from matplotlib.patches import FancyBboxPatch, Rectangle
    from matplotlib import font_manager
except ImportError:
    sys.stderr.write('需要安装 matplotlib: pip install matplotlib\n')
    sys.exit(2)


# ---------- 中文字体（强制注入） ----------
def setup_font():
    """按优先级查找 CJK 字体，确保中文不变方框。"""
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
        # 同时设置全局 family 和 rcParams，避免某些文字对象走默认
        plt.rcParams['font.family'] = ['sans-serif']
        plt.rcParams['font.sans-serif'] = [chosen, 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
    return chosen


# ---------- 配色（亮色系） ----------
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
SIG = {'fire': C['fire'], 'warn': C['orange'], 'ok': C['ok']}


def fmt_pct(v):
    if v is None:
        return '--'
    sign = '+' if v > 0 else ''
    return f'{sign}{v:.2f}%'


def color_change(v):
    if v is None:
        return C['muted']
    return C['green'] if v < 0 else C['red']


# ---------- 主渲染 ----------
def render(data, out_path):
    setup_font()

    rows = data.get('rows', [])
    summary = data.get('portfolio_summary', [])
    actions = data.get('action_list', [])
    phase = data.get('phase', '盘前')
    date = data.get('date', '')

    # ====== 布局参数（单位：像素，1 inch = 100 dpi 下） ======
    W = 1080                      # 画布宽度 px
    PAD_X = 36                    # 左右 padding
    HEADER_H = 130                # 顶部标题
    TABLE_HEADER_H = 52           # 表头高度
    ROW_H = 64                    # 每行高度
    SECTION_GAP = 30              # 节之间间距
    SECTION_TITLE_H = 44          # 节标题高度
    SUMMARY_LINE_H = 36           # 总结每行
    ACTION_LINE_H = 64            # 每条行动（两行文字：动作+标的 / 详情）
    CARD_PAD = 18                 # 卡片内 padding
    FOOTER_H = 52                 # 底部

    table_h = TABLE_HEADER_H + ROW_H * len(rows)
    summary_card_h = 0
    if summary:
        summary_card_h = SECTION_TITLE_H + CARD_PAD * 2 + SUMMARY_LINE_H * len(summary)
    actions_card_h = 0
    if actions:
        actions_card_h = SECTION_TITLE_H + CARD_PAD * 2 + ACTION_LINE_H * len(actions)

    H = (HEADER_H + table_h + SECTION_GAP
         + summary_card_h + (SECTION_GAP if summary else 0)
         + actions_card_h + (SECTION_GAP if actions else 0)
         + FOOTER_H + 20)

    # matplotlib: figsize 以英寸为单位，dpi=100 -> 1 inch = 100 px
    DPI = 100
    fig = plt.figure(figsize=(W / DPI, H / DPI), facecolor=C['bg'], dpi=DPI)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.invert_yaxis()       # 让 y=0 在顶部，向下增长，更直观
    ax.axis('off')

    y = 0  # 从顶部开始

    # ===== 顶部标题 =====
    y += 40
    ax.text(PAD_X, y, f'■ 自选股行情 · {phase}总览',
            fontsize=22, fontweight='bold', color=C['blue'],
            va='top', ha='left')
    ax.text(W - PAD_X, y + 8, date,
            fontsize=14, color=C['muted'],
            va='top', ha='right')
    y = HEADER_H  # 进入表格区

    # ===== 表格表头 =====
    # 7 列的 x 中心坐标（基于 W=1080 分配）
    # 代码(90) | 昨收(170) | 昨涨跌(170) | 盘前价(180) | 盘前%(180) | 距52W(150) | 信号(～140)
    cols_x = [95, 215, 385, 555, 725, 870, 1000]
    cols_name = ['代码', '昨收', '昨涨跌', '盘前价', '盘前%', '距52W高', '信号']

    # 表头背景
    ax.add_patch(FancyBboxPatch(
        (PAD_X, y), W - 2 * PAD_X, TABLE_HEADER_H,
        boxstyle='round,pad=0,rounding_size=8',
        linewidth=1, edgecolor=C['border'], facecolor=C['header_bg']))
    for name, cx in zip(cols_name, cols_x):
        ax.text(cx, y + TABLE_HEADER_H / 2, name,
                fontsize=13, fontweight='bold', color=C['text'],
                va='center', ha='center')
    y += TABLE_HEADER_H

    # ===== 每行数据 =====
    for i, r in enumerate(rows):
        row_y = y
        row_bg = C['alt'] if i % 2 == 0 else C['card']
        ax.add_patch(Rectangle((PAD_X, row_y), W - 2 * PAD_X, ROW_H,
                               facecolor=row_bg, edgecolor='none', linewidth=0))
        # 左侧色条（信号等级）
        level = r.get('signal_level', 'ok')
        ax.add_patch(Rectangle((PAD_X, row_y), 8, ROW_H,
                               facecolor=SIG.get(level, C['ok']),
                               edgecolor='none', linewidth=0))
        # 底部分隔线
        ax.add_patch(Rectangle((PAD_X, row_y + ROW_H - 1),
                               W - 2 * PAD_X, 1,
                               facecolor=C['border'], edgecolor='none', linewidth=0))

        cy = row_y + ROW_H / 2

        # 1 代码
        ax.text(cols_x[0], cy, r.get('symbol', ''),
                fontsize=15, fontweight='bold', color=C['text'],
                va='center', ha='center')

        # 2 昨收
        pc = r.get('prev_close')
        ax.text(cols_x[1], cy, f'${pc:.2f}' if pc else '--',
                fontsize=13, color=C['sub'], va='center', ha='center')

        # 3 昨涨跌
        pcp = r.get('prev_change_pct')
        ax.text(cols_x[2], cy, fmt_pct(pcp),
                fontsize=13, fontweight='bold', color=color_change(pcp),
                va='center', ha='center')

        # 4 盘前价
        pm = r.get('premarket_price')
        ax.text(cols_x[3], cy, f'${pm:.2f}' if pm else '--',
                fontsize=13, fontweight='bold', color=C['text'],
                va='center', ha='center')

        # 5 盘前%
        pmp = r.get('premarket_change_pct')
        ax.text(cols_x[4], cy, fmt_pct(pmp),
                fontsize=13, fontweight='bold', color=color_change(pmp),
                va='center', ha='center')

        # 6 距52W高
        d52 = r.get('dist_52w_high_pct')
        if d52 is not None and abs(d52) < 0.1:
            d52_text, d52_color = '★ 新高', C['red']
        elif d52 is not None:
            d52_text = fmt_pct(d52)
            d52_color = C['sub']
        else:
            d52_text, d52_color = '--', C['muted']
        ax.text(cols_x[5], cy, d52_text,
                fontsize=12, color=d52_color, va='center', ha='center')

        # 7 信号标签
        label = r.get('signal_label', '')
        # 自动换行：超过 10 个字符切断
        if len(label) > 12:
            label = label[:11] + '…'
        ax.text(cols_x[6], cy, label,
                fontsize=11, fontweight='bold',
                color=SIG.get(level, C['sub']),
                va='center', ha='center')

        y += ROW_H

    y += SECTION_GAP

    # ===== 组合层面总结 =====
    if summary:
        ax.text(PAD_X, y, '■ 组合层面总结',
                fontsize=16, fontweight='bold', color=C['blue'],
                va='top', ha='left')
        y += SECTION_TITLE_H

        card_h = CARD_PAD * 2 + SUMMARY_LINE_H * len(summary)
        ax.add_patch(FancyBboxPatch(
            (PAD_X, y), W - 2 * PAD_X, card_h,
            boxstyle='round,pad=0,rounding_size=10',
            linewidth=1, edgecolor=C['border'], facecolor=C['card']))

        ty = y + CARD_PAD + SUMMARY_LINE_H / 2
        for s in summary:
            # 限制长度防溢出
            if len(s) > 50:
                s = s[:49] + '…'
            ax.text(PAD_X + 20, ty, f'• {s}',
                    fontsize=13, color=C['sub'], va='center', ha='left')
            ty += SUMMARY_LINE_H
        y += card_h + SECTION_GAP

    # ===== 开盘前行动清单 =====
    if actions:
        ax.text(PAD_X, y, '■ 开盘前行动清单',
                fontsize=16, fontweight='bold', color=C['blue'],
                va='top', ha='left')
        y += SECTION_TITLE_H

        card_h = CARD_PAD * 2 + ACTION_LINE_H * len(actions)
        ax.add_patch(FancyBboxPatch(
            (PAD_X, y), W - 2 * PAD_X, card_h,
            boxstyle='round,pad=0,rounding_size=10',
            linewidth=1, edgecolor=C['border'], facecolor=C['card']))

        action_color_map = {
            '减仓': C['fire'], '卖出': C['fire'], '止损': C['fire'],
            '加仓': C['green'], '建仓': C['green'], '买入': C['green'],
            '观望': C['orange'], '持有': C['blue'],
        }

        ty = y + CARD_PAD + ACTION_LINE_H / 2
        for a in actions:
            act = a.get('action', '')
            tgt = a.get('target', '')
            det = a.get('detail', '')
            col = action_color_map.get(act, C['sub'])
            # 第 1 行：[动作] 标的
            tag_x = PAD_X + 20
            ax.text(tag_x, ty - 12, f'[{act}]',
                    fontsize=12.5, fontweight='bold', color=col,
                    va='center', ha='left')
            ax.text(tag_x + 80, ty - 12, tgt,
                    fontsize=13.5, fontweight='bold', color=C['text'],
                    va='center', ha='left')
            # 第 2 行：详情（超长截断）
            if len(det) > 70:
                det = det[:69] + '…'
            ax.text(tag_x, ty + 12, det,
                    fontsize=12, color=C['sub'],
                    va='center', ha='left')
            ty += ACTION_LINE_H
        y += card_h + SECTION_GAP

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
    ap.add_argument('--input', required=True, help='overview_data.json')
    ap.add_argument('--output', required=True, help='output png path')
    args = ap.parse_args()

    with open(args.input, encoding='utf-8') as f:
        data = json.load(f)
    render(data, args.output)


if __name__ == '__main__':
    main()
