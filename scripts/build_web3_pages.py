#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_web3_pages.py
从 /data/workspace/web3-archive/digests/*.json 批量生成：
- YoungStockDaily/web3/YYYY-MM-DD.html（详情页）
- YoungStockDaily/data/web3.json（列表索引）

单次运行可全量重建，也可由定时任务追加新日期（会覆盖已存在的同日文件）。
"""
import json
import os
import re
import sys
import datetime
from pathlib import Path

ARCHIVE_DIR = Path('/data/workspace/web3-archive/digests')
REPO_DIR = Path('/data/workspace/YoungStockDaily')
WEB3_DIR = REPO_DIR / 'web3'
DATA_INDEX = REPO_DIR / 'data' / 'web3.json'

HTML_TPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0">
  <meta name="theme-color" content="#f7f9fc">
  <title>Web3 日报 · {date} · Young's Stock Daily</title>
  <link rel="stylesheet" href="../assets/style.css">
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='14' fill='%23f7931a'/%3E%3Ctext x='32' y='44' font-size='38' text-anchor='middle' fill='white' font-family='Arial' font-weight='bold'%3E₿%3C/text%3E%3C/svg%3E">
</head>
<body>
  <header class="site-header">
    <div class="inner">
      <div class="brand">
        <span class="logo" style="background:linear-gradient(135deg,#f7931a,#ffb758)">₿</span>
        <div>
          Young's Stock Daily
          <small>Web3 日报归档</small>
        </div>
      </div>
      <nav class="nav-links">
        <a href="../index.html">🏠 首页</a>
        <a href="../index.html#web3">🪙 Web3 列表</a>
      </nav>
    </div>
  </header>

  <main>
    <a class="back-link" href="../index.html#web3">← 返回 Web3 列表</a>
    <div class="report-meta">
      <span class="category">🪙 Web3 日报</span>
      <span>生成时间：{generated_at}</span>
    </div>
    <h1 class="report-title">📅 Web3 日报 · {date}</h1>

    <div class="report-content" id="digest-body">
{body_html}
    </div>

    <details style="margin-top:20px;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius);padding:14px 18px;">
      <summary style="cursor:pointer;font-weight:600;color:var(--text-sub)">📋 微信推送纯文本版（点击展开，可直接复制）</summary>
      <pre style="white-space:pre-wrap;word-break:break-word;background:var(--bg-card-alt);padding:14px;border-radius:var(--radius-sm);font-size:13px;margin-top:10px;line-height:1.7;">{wechat_text}</pre>
    </details>

    <div style="margin-top:16px;color:var(--text-muted);font-size:12px;text-align:center">
      数据来源：{source}
    </div>
  </main>

  <footer>
    © Young's Stock Daily · 本站内容仅为个人投资备忘，不构成任何投资建议
  </footer>
</body>
</html>
"""

def md_to_html(md: str) -> str:
    """极简 Markdown → HTML（满足 web3 日报常见语法：标题/粗体/列表/表格/引用/分隔线）。"""
    lines = md.split('\n')
    out = []
    in_table = False
    table_rows = []
    in_list = False

    def flush_table():
        nonlocal in_table, table_rows
        if not in_table:
            return
        if len(table_rows) >= 2:
            header = table_rows[0]
            body = table_rows[2:]  # 跳过分隔行
            out.append('<table><thead><tr>')
            for c in header:
                out.append(f'<th>{c}</th>')
            out.append('</tr></thead><tbody>')
            for row in body:
                out.append('<tr>')
                for c in row:
                    out.append(f'<td>{c}</td>')
                out.append('</tr>')
            out.append('</tbody></table>')
        in_table = False
        table_rows = []

    def flush_list():
        nonlocal in_list
        if in_list:
            out.append('</ul>')
            in_list = False

    def inline(s):
        # 粗体
        s = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s)
        # 斜体
        s = re.sub(r'(?<!\*)\*([^\*]+)\*(?!\*)', r'<em>\1</em>', s)
        # 行内代码
        s = re.sub(r'`([^`]+)`', r'<code>\1</code>', s)
        # 链接 [text](url)
        s = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)
        return s

    for raw in lines:
        line = raw.rstrip()
        # 表格
        if '|' in line and line.strip().startswith('|'):
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            if not in_table:
                flush_list()
                in_table = True
                table_rows = []
            table_rows.append([inline(c) for c in cells])
            continue
        else:
            flush_table()

        if not line.strip():
            flush_list()
            out.append('')
            continue

        # 标题
        m = re.match(r'^(#{1,6})\s+(.*)$', line)
        if m:
            flush_list()
            lvl = len(m.group(1))
            out.append(f'<h{lvl}>{inline(m.group(2))}</h{lvl}>')
            continue

        # 分隔线
        if re.match(r'^[-=*_]{3,}$', line.strip()):
            flush_list()
            out.append('<hr>')
            continue

        # 引用
        if line.startswith('>'):
            flush_list()
            out.append(f'<blockquote>{inline(line.lstrip("> ").strip())}</blockquote>')
            continue

        # 列表
        if re.match(r'^\s*[-*+]\s+', line):
            if not in_list:
                in_list = True
                out.append('<ul>')
            item = re.sub(r'^\s*[-*+]\s+', '', line)
            out.append(f'<li>{inline(item)}</li>')
            continue
        if re.match(r'^\s*\d+\.\s+', line):
            if not in_list:
                in_list = True
                out.append('<ul>')
            item = re.sub(r'^\s*\d+\.\s+', '', line)
            out.append(f'<li>{inline(item)}</li>')
            continue
        flush_list()

        out.append(f'<p>{inline(line)}</p>')

    flush_table()
    flush_list()
    return '\n'.join(out)


def escape_html(s: str) -> str:
    return (s.replace('&', '&amp;')
             .replace('<', '&lt;')
             .replace('>', '&gt;'))


def extract_title_summary(md: str) -> tuple:
    """从 md 中提取标题和摘要。"""
    title = 'Web3 日报'
    summary = ''
    for line in md.split('\n'):
        line = line.strip()
        if not line:
            continue
        if line.startswith('#'):
            title = line.lstrip('#').strip() or title
            continue
        # 第一段非标题文字作摘要
        if not summary and not line.startswith('|') and not line.startswith('-'):
            summary = re.sub(r'[*_`#>]', '', line)[:120]
            break
    return title, summary


def build():
    WEB3_DIR.mkdir(parents=True, exist_ok=True)
    index = []
    for jf in sorted(ARCHIVE_DIR.glob('*.json')):
        with open(jf, encoding='utf-8') as f:
            d = json.load(f)
        date = d.get('date') or jf.stem
        md = d.get('digest_md', '') or ''
        wechat = d.get('digest_wechat', '') or ''
        generated_at = d.get('generated_at', '')
        source = d.get('source', '')

        body_html = md_to_html(md) if md else f'<pre>{escape_html(wechat)}</pre>'
        title, summary = extract_title_summary(md or wechat)

        html = HTML_TPL.format(
            date=date,
            generated_at=generated_at or '未知',
            body_html=body_html,
            wechat_text=escape_html(wechat or md),
            source=source or 'j4y-production.up.railway.app',
        )
        out_path = WEB3_DIR / f'{date}.html'
        out_path.write_text(html, encoding='utf-8')
        index.append({
            'date': date,
            'title': title,
            'summary': summary,
            'generated_at': generated_at,
        })
        print(f'[ok] {out_path}  ({len(html)} bytes)')

    # 写索引（倒序）
    index.sort(key=lambda x: x['date'], reverse=True)
    DATA_INDEX.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_INDEX, 'w', encoding='utf-8') as f:
        json.dump({
            'updated_at': datetime.datetime.now().isoformat(timespec='seconds'),
            'count': len(index),
            'digests': index,
        }, f, ensure_ascii=False, indent=2)
    print(f'[ok] index written: {DATA_INDEX} ({len(index)} entries)')


if __name__ == '__main__':
    build()
