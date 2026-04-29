#!/usr/bin/env python3
"""
一次性迁移脚本：
- 扫描 reports/YYYY-MM-DD.html + web3/YYYY-MM-DD.html，
  以日期为 key 合并为新格式 daily/daily_YYYYMMDD_HHMM.{json,html}
- 图片 images/YYYY-MM-DD.png → images/daily_YYYYMMDD_HHMM.png
- 生成统一索引 data/daily.json
- 用文件 mtime 推断生成时间戳；找不到就取 00:00

⚠️ 本脚本只应运行一次；运行后 reports/ 和 web3/ 目录可删除。
"""
import os, re, json, shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT / "reports"
WEB3_DIR    = ROOT / "web3"
IMG_DIR     = ROOT / "images"
DAILY_DIR   = ROOT / "daily"
DATA_DIR    = ROOT / "data"

DAILY_DIR.mkdir(exist_ok=True)

def extract_stock_body(html):
    """从股票详情页里抽出主体 HTML（不含 site-header/footer）
    优先匹配 <article class="report-content">...</article>，
    其次匹配 <section class="stock-report">...</section>，
    再其次退化抓 <main> 内部。"""
    m = re.search(r'<article[^>]*class="report-content"[^>]*>([\s\S]*?)</article>', html, re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r'<section[^>]*class="stock-report"[^>]*>([\s\S]*?)</section>\s*(?=</main>|</body>|<footer|<script|$)', html, re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r'<main[^>]*>([\s\S]*?)</main>', html, re.I)
    if m:
        return m.group(1).strip()
    return ''

def extract_web3_body(html):
    m = re.search(r'<div[^>]*id="digest-body"[^>]*>([\s\S]*?)</div>\s*(?=<details|</main>|</body>)', html, re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r'<main[^>]*>([\s\S]*?)</main>', html, re.I)
    if m:
        return m.group(1).strip()
    return ''

def rewrite_image_paths(body, old_img, new_img):
    """把原来的 ../images/2026-04-29.png 等引用改为 ../images/daily_xxx.png"""
    body = body.replace(f'../images/{old_img}', f'../images/{new_img}')
    body = body.replace(f'../../images/{old_img}', f'../images/{new_img}')
    body = body.replace(f'images/{old_img}', f'../images/{new_img}')
    return body

def strip_hero_figure(body):
    """移除 body 内部的 <figure class="hero-image">...</figure>，避免与外层预览图重复"""
    return re.sub(r'<figure[^>]*class="hero-image"[^>]*>[\s\S]*?</figure>', '', body, flags=re.I)

def file_mtime_ts(path):
    ts = datetime.fromtimestamp(path.stat().st_mtime)
    return ts

def make_slug(date_str, time_obj):
    """daily_20260429_0903"""
    d = date_str.replace('-', '')
    t = time_obj.strftime('%H%M')
    return f'daily_{d}_{t}'

def build_one_daily_html(slug, date_str, gen_time, stock_body, web3_body, has_img):
    """生成独立详情页（直接访问用），样式延用首页 CSS"""
    gen_time_str = gen_time.strftime('%Y-%m-%d %H:%M:%S')
    img_html = f'''
    <figure class="hero-image-plain">
      <img src="../images/{slug}.png" alt="{date_str} 异常信号总览" loading="lazy">
      <figcaption>异常信号总览 · 点击可查看大图</figcaption>
    </figure>''' if has_img else ''
    stock_section = f'''
    <section class="daily-block">
      <h2 class="daily-block-title">📈 自选股实时行情分析</h2>
      <div class="daily-block-body">{stock_body}</div>
    </section>''' if stock_body else ''
    web3_section = f'''
    <section class="daily-block">
      <h2 class="daily-block-title">🪙 Web3 加密日报</h2>
      <div class="daily-block-body">{web3_body}</div>
    </section>''' if web3_body else ''
    nav_html = ''
    if stock_body and web3_body:
        nav_html = '''
    <div class="daily-anchor-nav">
      <a href="#stock-section">📈 自选股</a>
      <a href="#web3-section">🪙 Web3</a>
    </div>'''
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0">
  <meta name="theme-color" content="#f7f9fc">
  <title>{date_str} · 投研日报 · Young's Stock Daily</title>
  <link rel="stylesheet" href="../assets/style.css">
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='14' fill='%232563eb'/%3E%3Ctext x='32' y='42' font-size='34' text-anchor='middle' fill='white' font-family='Arial' font-weight='bold'%3EY%3C/text%3E%3C/svg%3E">
</head>
<body>
  <header class="site-header">
    <div class="inner">
      <div class="brand">
        <span class="logo">Y</span>
        <div>
          Young's Stock Daily
          <small>股票 &amp; Web3 投研日志</small>
        </div>
      </div>
      <nav class="nav-links">
        <a href="../index.html">← 返回首页</a>
      </nav>
    </div>
  </header>
  <main>
    <div class="daily-page-head">
      <h1>{date_str} · 投研日报</h1>
      <div class="daily-meta">🕒 生成于 {gen_time_str}</div>
    </div>
    {img_html}
    {nav_html}
    {stock_section.replace('<section class="daily-block">', '<section class="daily-block" id="stock-section">')}
    {web3_section.replace('<section class="daily-block">', '<section class="daily-block" id="web3-section">')}
  </main>
  <footer>© Young's Stock Daily</footer>
</body>
</html>
'''

def main():
    # 收集所有日期
    dates = set()
    for p in REPORTS_DIR.glob('*.html'):
        dates.add(p.stem)
    for p in WEB3_DIR.glob('*.html'):
        dates.add(p.stem)
    dates = sorted(dates)

    index = {"updated_at": datetime.now().strftime('%Y-%m-%dT%H:%M:%S'), "dailies": []}
    portfolio_data = json.loads((DATA_DIR / 'portfolio.json').read_text(encoding='utf-8')) if (DATA_DIR / 'portfolio.json').exists() else {}

    for date_str in dates:
        stock_html_path = REPORTS_DIR / f'{date_str}.html'
        web3_html_path  = WEB3_DIR / f'{date_str}.html'
        img_src_path    = IMG_DIR / f'{date_str}.png'

        stock_html = stock_html_path.read_text(encoding='utf-8') if stock_html_path.exists() else ''
        web3_html  = web3_html_path.read_text(encoding='utf-8') if web3_html_path.exists() else ''

        # 生成时间戳：取两个文件的较新 mtime 作为生成时间
        mtimes = []
        if stock_html_path.exists(): mtimes.append(file_mtime_ts(stock_html_path))
        if web3_html_path.exists():  mtimes.append(file_mtime_ts(web3_html_path))
        gen_time = max(mtimes) if mtimes else datetime.strptime(date_str, '%Y-%m-%d')

        slug = make_slug(date_str, gen_time)

        stock_body = extract_stock_body(stock_html) if stock_html else ''
        web3_body  = extract_web3_body(web3_html)   if web3_html  else ''

        # 把旧图片路径改写
        old_img = f'{date_str}.png'
        new_img = f'{slug}.png'
        if stock_body:
            stock_body = rewrite_image_paths(stock_body, old_img, new_img)
            stock_body = strip_hero_figure(stock_body)

        # 图片改名
        has_img = False
        if img_src_path.exists():
            dst = IMG_DIR / new_img
            if not dst.exists():
                shutil.copy(img_src_path, dst)
            has_img = True

        # 从股票报告里提取摘要/标题/tickers（尝试沿用 reports.json）
        meta_stock = None
        if (DATA_DIR / 'reports.json').exists():
            r = json.loads((DATA_DIR / 'reports.json').read_text(encoding='utf-8'))
            for x in r.get('reports', []):
                if x.get('date') == date_str:
                    meta_stock = x; break
        meta_web3 = None
        if (DATA_DIR / 'web3.json').exists():
            w = json.loads((DATA_DIR / 'web3.json').read_text(encoding='utf-8'))
            for x in w.get('digests', []):
                if x.get('date') == date_str:
                    meta_web3 = x; break

        title_parts = []
        if meta_stock: title_parts.append(meta_stock.get('title', ''))
        if meta_web3:  title_parts.append('Web3 日报')
        title = ' + '.join([t for t in title_parts if t]) or f'{date_str} 投研日报'
        summary_parts = []
        if meta_stock: summary_parts.append(meta_stock.get('summary', ''))
        if meta_web3:  summary_parts.append(meta_web3.get('summary', ''))
        summary = ' · '.join([s for s in summary_parts if s])
        tickers = meta_stock.get('tickers', []) if meta_stock else []

        # 写 JSON 数据
        data = {
            "slug": slug,
            "date": date_str,
            "generated_at": gen_time.strftime('%Y-%m-%d %H:%M:%S'),
            "title": title,
            "summary": summary,
            "tickers": tickers,
            "image": f'images/{new_img}' if has_img else None,
            "has_stock": bool(stock_body),
            "has_web3":  bool(web3_body),
            "stock_body_html": stock_body,
            "web3_body_html":  web3_body,
        }
        (DAILY_DIR / f'{slug}.json').write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

        # 写独立详情页
        html = build_one_daily_html(slug, date_str, gen_time, stock_body, web3_body, has_img)
        (DAILY_DIR / f'{slug}.html').write_text(html, encoding='utf-8')

        index['dailies'].append({
            "slug": slug,
            "date": date_str,
            "generated_at": data['generated_at'],
            "title": title,
            "summary": summary,
            "tickers": tickers,
            "image": data['image'],
            "has_stock": data['has_stock'],
            "has_web3":  data['has_web3'],
        })
        print(f'[OK] {date_str} → {slug}  stock={bool(stock_body)} web3={bool(web3_body)} img={has_img}')

    # 按时间倒序
    index['dailies'].sort(key=lambda x: (x['date'], x['generated_at']), reverse=True)
    (DATA_DIR / 'daily.json').write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\n共生成 {len(index["dailies"])} 条 daily 记录')

if __name__ == '__main__':
    main()
