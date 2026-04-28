#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
publish_site.py
一键把本次生成的内容沉淀到仓库并 push：
  1. 同步 watchlist.json → data/portfolio.json
  2. 扫描 /data/workspace/web3-archive/digests/ 重建 web3 详情页 + data/web3.json
  3. （可选）把本次股票报告 HTML 写入 reports/YYYY-MM-DD.html 并更新 data/reports.json
  4. （可选）把异常信号总览 PNG 复制到 images/YYYY-MM-DD.png
  5. git add / commit / push

用法示例：
  python3 publish_site.py \
    --repo-dir /data/workspace/YoungStockDaily \
    --date 2026-04-28 \
    --stock-report /tmp/stock_report.html \
    --stock-summary "9 只盘前全线翻绿，均跌 -4.2%" \
    --stock-title "自选股实时行情分析 · 盘前" \
    --stock-category "实时行情分析" \
    --tickers MU,AMD,INTC \
    --overview-png /tmp/overview.png

环境变量（优先级高于命令行默认值）：
  REPO_URL / REPO_DIR / GITHUB_TOKEN
"""
import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# 把同目录下的 build_web3_pages 作为模块导入
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
try:
    import build_web3_pages
except Exception:
    build_web3_pages = None


def run(cmd, cwd=None, check=True, env=None, capture=True):
    r = subprocess.run(cmd, cwd=cwd, shell=isinstance(cmd, str),
                        env=env, capture_output=capture, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f'cmd failed: {cmd}\nstdout: {r.stdout}\nstderr: {r.stderr}')
    return r


def ensure_repo(repo_url, repo_dir, token):
    repo_dir = Path(repo_dir)
    if not (repo_dir / '.git').exists():
        repo_dir.parent.mkdir(parents=True, exist_ok=True)
        url = repo_url
        if token:
            url = repo_url.replace('https://', f'https://x-access-token:{token}@')
        run(['git', 'clone', url, str(repo_dir)])
    else:
        # pull 最新，避免落后 origin
        run(['git', 'fetch', 'origin'], cwd=str(repo_dir), check=False)
    return repo_dir


def sync_portfolio(repo_dir):
    src = Path('/data/workspace/portfolio/watchlist.json')
    if not src.exists():
        return False
    dst = repo_dir / 'data' / 'portfolio.json'
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def rebuild_web3(repo_dir):
    if build_web3_pages is None:
        return False
    # 临时重置模块内的常量，指向当前仓库
    build_web3_pages.REPO_DIR = repo_dir
    build_web3_pages.WEB3_DIR = repo_dir / 'web3'
    build_web3_pages.DATA_INDEX = repo_dir / 'data' / 'web3.json'
    build_web3_pages.build()
    return True


def write_stock_report(repo_dir, date, html_path, title, category, summary,
                       tickers, image_rel):
    reports_dir = repo_dir / 'reports'
    reports_dir.mkdir(exist_ok=True)

    if html_path and Path(html_path).exists():
        shutil.copy2(html_path, reports_dir / f'{date}.html')

    index_path = repo_dir / 'data' / 'reports.json'
    if index_path.exists():
        data = json.load(open(index_path, encoding='utf-8'))
    else:
        data = {'updated_at': '', 'reports': []}

    entry = {
        'date': date,
        'title': title or f'股票分析 · {date}',
        'category': category or '实时行情分析',
        'summary': summary or '',
        'tickers': tickers,
        'image': image_rel or '',
    }
    # 覆盖或追加
    others = [r for r in data.get('reports', []) if r.get('date') != date]
    reports = [entry] + others
    reports.sort(key=lambda x: x.get('date', ''), reverse=True)
    data['reports'] = reports
    data['updated_at'] = datetime.datetime.now().isoformat(timespec='seconds')
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def copy_overview(repo_dir, date, png_path):
    if not png_path:
        return None
    src = Path(png_path)
    if not src.exists():
        return None
    dst = repo_dir / 'images' / f'{date}.png'
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return f'images/{date}.png'


def git_push(repo_dir, repo_url, token, message):
    # 配置 user（如未配置）
    run(['git', 'config', 'user.email', 'knot@anydev.local'], cwd=str(repo_dir), check=False)
    run(['git', 'config', 'user.name', 'Knot Agent'], cwd=str(repo_dir), check=False)

    run(['git', 'add', '-A'], cwd=str(repo_dir))
    # 检查有无改动
    r = run(['git', 'status', '--porcelain'], cwd=str(repo_dir))
    if not r.stdout.strip():
        return {'pushed': False, 'reason': 'no changes'}

    run(['git', 'commit', '-m', message], cwd=str(repo_dir))

    push_url = repo_url
    if token:
        push_url = repo_url.replace('https://', f'https://x-access-token:{token}@')
    r = run(['git', 'push', push_url, 'HEAD:main'], cwd=str(repo_dir), check=False)
    # 脱敏输出
    stdout = (r.stdout or '') + (r.stderr or '')
    if token:
        stdout = stdout.replace(token, '***TOKEN***')
    if r.returncode != 0:
        raise RuntimeError(f'git push failed:\n{stdout}')
    return {'pushed': True, 'output': stdout.strip()}


def load_token(token_file):
    if os.environ.get('GITHUB_TOKEN'):
        return os.environ['GITHUB_TOKEN'].strip()
    if token_file:
        tf = Path(os.path.expanduser(token_file))
        if tf.exists():
            return tf.read_text().strip()
    return ''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo-url', default=os.environ.get('REPO_URL', 'https://github.com/tracyyoung666/YoungStockDaily.git'))
    ap.add_argument('--repo-dir', default=os.environ.get('REPO_DIR', '/data/workspace/YoungStockDaily'))
    ap.add_argument('--token-file', default='~/.config/knot/github_token')
    ap.add_argument('--date', default=datetime.date.today().isoformat())
    ap.add_argument('--stock-report', default='', help='本次股票 HTML 完整路径（可选）')
    ap.add_argument('--stock-title', default='')
    ap.add_argument('--stock-category', default='实时行情分析')
    ap.add_argument('--stock-summary', default='')
    ap.add_argument('--tickers', default='', help='逗号分隔')
    ap.add_argument('--overview-png', default='', help='异常信号总览 PNG 路径（可选）')
    ap.add_argument('--commit-msg', default='')
    ap.add_argument('--skip-web3', action='store_true')
    ap.add_argument('--skip-stock', action='store_true')
    args = ap.parse_args()

    token = load_token(args.token_file)
    if not token:
        sys.stderr.write('warning: no GitHub token available, push may fail\n')

    repo_dir = ensure_repo(args.repo_url, args.repo_dir, token)

    sync_portfolio(repo_dir)

    if not args.skip_web3:
        rebuild_web3(repo_dir)

    image_rel = None
    if args.overview_png:
        image_rel = copy_overview(repo_dir, args.date, args.overview_png)

    if not args.skip_stock and args.stock_report:
        tickers_list = [t.strip() for t in args.tickers.split(',') if t.strip()]
        write_stock_report(repo_dir, args.date, args.stock_report,
                           args.stock_title, args.stock_category,
                           args.stock_summary, tickers_list, image_rel)

    msg = args.commit_msg or f'chore: update {args.date} 股票分析 + Web3 日报'
    result = git_push(repo_dir, args.repo_url, token, msg)

    print(json.dumps({
        'ok': True,
        'date': args.date,
        'image_rel': image_rel,
        'git': result,
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
