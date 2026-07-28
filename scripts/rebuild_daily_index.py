#!/usr/bin/env python3
"""从 daily/*.json 重建 data/daily.json 统一索引。
任何时候发现首页列表跟 daily/ 目录不一致，都可以安全地运行这个脚本。"""
import json, glob, sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
DAILY_DIR = ROOT / 'daily'
DATA_DIR  = ROOT / 'data'

# 特别报告（纯 HTML 页，无对应 JSON）：不常驻首页，但需出现在"分析日报"列表中
# 新增专题页时在此登记即可，external_url 相对站点根目录
SPECIAL_REPORTS = [
    {
        "slug": "midyear_20260701",
        "date": "2026-07-01",
        "generated_at": "2026-07-01 12:00",
        "title": "📌 2026 年中小结：Flag 立于年初，账已过半",
        "summary": "三账户 +50% 目标进度 · 候选标的半年成绩单 · 复盘与下半年候选池。"
                   "FT +9.8% / LongB -35.4% / Chars +107.7% / 整体 +22.7%。",
        "tickers": ["NBIS", "RKLB", "TSLA", "CRCL", "XPEV"],
        "image": None,
        "has_stock": True,
        "has_web3": False,
        "external_url": "daily/midyear_20260701.html",
    },
]

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
        # tickers 兼容：可能是字符串数组或对象数组，统一存为字符串数组
        raw_tickers = d.get("tickers", [])
        if raw_tickers and isinstance(raw_tickers[0], dict):
            tickers = [t.get("symbol", "") for t in raw_tickers if t.get("symbol")]
        else:
            tickers = raw_tickers
        entries.append({
            "slug":         d["slug"],
            "date":         d["date"],
            "generated_at": d["generated_at"],
            "title":        d.get("title", ''),
            "summary":      d.get("summary", ''),
            "tickers":      tickers,
            "image":        d.get("image"),
            "has_stock":    d.get("has_stock", False),
            "has_web3":     d.get("has_web3", False),
        })
    # 合并特别报告（纯 HTML 专题），仅当文件确实存在时才加入索引
    for sp in SPECIAL_REPORTS:
        html_path = ROOT / sp["external_url"]
        if not html_path.exists():
            print(f'[skip] 特别报告文件不存在: {sp["external_url"]}', file=sys.stderr)
            continue
        entries.append(dict(sp))

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
