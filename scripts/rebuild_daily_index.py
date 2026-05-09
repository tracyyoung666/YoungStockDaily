#!/usr/bin/env python3
"""从 daily/*.json 重建 data/daily.json 统一索引。
任何时候发现首页列表跟 daily/ 目录不一致，都可以安全地运行这个脚本。"""
import json, glob, sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
DAILY_DIR = ROOT / 'daily'
DATA_DIR  = ROOT / 'data'

def main():
    entries = []
    # 扫描日报 daily_*.json 和周报 weekly_*.json
    all_files = sorted(DAILY_DIR.glob('daily_*.json')) + sorted(DAILY_DIR.glob('weekly_*.json'))
    for f in all_files:
        try:
            d = json.loads(f.read_text(encoding='utf-8'))
        except Exception as e:
            print(f'[skip] {f.name}: {e}', file=sys.stderr)
            continue
        entries.append({
            "slug":         d["slug"],
            "date":         d["date"],
            "generated_at": d["generated_at"],
            "title":        d.get("title", ''),
            "summary":      d.get("summary", ''),
            "tickers":      d.get("tickers", []),
            "image":        d.get("image"),
            "has_stock":    d.get("has_stock", False),
            "has_web3":     d.get("has_web3", False),
        })
    entries.sort(key=lambda x: (x['date'], x['generated_at']), reverse=True)
    idx = {
        "updated_at": datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
        "dailies": entries,
    }
    (DATA_DIR / 'daily.json').write_text(
        json.dumps(idx, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'✅ data/daily.json 已重建，共 {len(entries)} 条')
    for e in entries:
        print(f"   · {e['slug']}  stock={e['has_stock']} web3={e['has_web3']} img={'Y' if e['image'] else 'N'}")

if __name__ == '__main__':
    main()
