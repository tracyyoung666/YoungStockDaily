#!/usr/bin/env python3
"""
fetch_sparkline.py - 获取自选股最近7个交易日 OHLC K线数据
输出到 data/sparkline.json，供前端 7 日 K 线图使用。

每次生成日报时调用此脚本更新数据。
"""
import json
import subprocess
import sys
from pathlib import Path

WESTOCK_SCRIPT = "/data/workspace/.agent/skills/westock-data/scripts/index.js"
WESTOCK_CWD = "/data/workspace/.agent/skills/westock-data"

SYMBOLS = {
    "MU": "usMU.OQ",
    "AMD": "usAMD.OQ",
    "INTC": "usINTC.OQ",
    "NBIS": "usNBIS.OQ",
    "CRWV": "usCRWV.OQ",
    "CRCL": "usCRCL.N",
    "MSTR": "usMSTR.OQ",
    "TSLA": "usTSLA.OQ",
    "XPEV": "usXPEV.N",
    "GOOG": "usGOOG.OQ",
}


def fetch_kline(code: str, limit: int = 7) -> list:
    """获取单只股票最近 N 天 K 线。返回 [{date, open, close, high, low, volume}]"""
    try:
        proc = subprocess.run(
            ["node", WESTOCK_SCRIPT, "kline", code, "--period", "day", "--limit", str(limit)],
            capture_output=True, text=True, timeout=30,
            cwd=WESTOCK_CWD
        )
        results = []
        for line in proc.stdout.split("\n"):
            if not line.startswith("| 2"):
                continue
            parts = [p.strip() for p in line.split("|")[1:-1]]
            if len(parts) < 6:
                continue
            try:
                results.append({
                    "date": parts[0],
                    "open": float(parts[1]),
                    "close": float(parts[2]),
                    "high": float(parts[3]),
                    "low": float(parts[4]),
                    "volume": int(parts[5]),
                })
            except (ValueError, IndexError):
                continue
        # 按日期正序
        results.sort(key=lambda x: x["date"])
        return results
    except Exception as e:
        print(f"[warn] {code} kline fetch failed: {e}", file=sys.stderr)
        return []


def main():
    from datetime import datetime

    output_path = sys.argv[1] if len(sys.argv) > 1 else "/data/workspace/YoungStockDaily/data/sparkline.json"

    sparkline_data = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "period": "day",
        "days": 7,
        "stocks": {}
    }

    for sym, code in SYMBOLS.items():
        klines = fetch_kline(code, limit=7)
        if klines:
            sparkline_data["stocks"][sym] = klines
            print(f"  ✅ {sym}: {len(klines)} days ({klines[0]['date']} ~ {klines[-1]['date']})")
        else:
            print(f"  ⚠️ {sym}: no data")

    # 写入
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    json.dump(sparkline_data, open(out, "w"), ensure_ascii=False, indent=2)
    print(f"\n✅ sparkline.json written: {out} ({len(sparkline_data['stocks'])} stocks)")


if __name__ == "__main__":
    main()
