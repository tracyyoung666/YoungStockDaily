#!/usr/bin/env python3
"""
美股实时行情 + 盘前/盘后价统一抓取工具（stock-and-web3 技能专用）v3

**时区口径（2026-04-30 大修）**：
- 系统时区：北京时间（CST, UTC+8）
- 美股交易时段（夏令时，4月适用）：
    盘前 Pre-Market  : 美东 04:00-09:30 = 北京 16:00-21:30
    常规 Regular     : 美东 09:30-16:00 = 北京 21:30 - 次日 04:00
    盘后 After-Hours : 美东 16:00-20:00 = 北京 次日 04:00-08:00
    休市 Closed      : 其他时段

**新浪 gb_ 接口字段映射（36 字段，逐字段交叉验算确认）**：
    [0]  名称
    [1]  ⭐ 最新已完成交易日的收盘价（动态更新：美东收盘后就切换为当天的收盘）
    [2]  [1] vs [26] 的涨跌%（基准是 T-1，⚠️不可直接用作盘前/盘后涨跌%）
    [3]  北京时间戳
    [5]  常规开盘价  [6] 常规最高  [7] 常规最低
    [8]  52w高  [9] 52w低  [10] 常规成交量
    [21] ⭐ 动态扩展价格 —— 盘前阶段=盘前价，盘后阶段=盘后价
    [22] ⭐ [21] 对比 [1] 的涨跌%
    [23] ⭐ [21] 对比 [1] 的涨跌额
    [24] ⭐ 美东扩展时段时间戳（如 "Apr 29 07:40AM EDT" 或 "Apr 29 08:01PM EDT"）
    [25] 常规收盘时间戳（如 "Apr 29 04:00PM EDT"）
    [26] 前一交易日收盘价（T-1）
    [27] ⭐ 扩展时段成交量
    [31] 扩展时段最高  [32] 扩展时段最低  [33] 扩展时段成交额

**任务触发时段与数据策略**：
    北京时间 07:00-15:00 工作日 → 美东夜间 → 获取「今日收盘价 [1]」+「盘后价 [21]」
    北京时间 15:00-23:00        → 美东盘前 → 获取「昨收 [1]」+「盘前价 [21]」
    周六/周日                    → 休市   → 获取「周五收盘价 [1]」+「周五盘后价 [21]」
"""
import json
import re
import subprocess
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

# westock-data 代码映射
WESTOCK_CODE_MAP = {
    "MU":   "usMU.OQ",
    "AMD":  "usAMD.OQ",
    "INTC": "usINTC.OQ",
    "NBIS": "usNBIS.OQ",
    "CRWV": "usCRWV.OQ",
    "CRCL": "usCRCL.N",
    "MSTR": "usMSTR.OQ",
    "TSLA": "usTSLA.OQ",
    "XPEV": "usXPEV.N",
}

WESTOCK_SCRIPT = "/data/workspace/.agent/skills/westock-data/scripts/index.js"


def detect_market_session() -> Dict:
    """根据当前北京时间判断应获取什么类型的扩展时段数据。

    返回：{
        session: 'fetch_afterhours' | 'fetch_premarket' | 'weekend_afterhours',
        session_label: 人类可读描述,
        extended_type: 'afterhours' | 'premarket',
        bj_time, et_time
    }
    """
    bj_now = datetime.now(timezone(timedelta(hours=8)))
    et_now = bj_now.astimezone(timezone(timedelta(hours=-4)))  # EDT 夏令时
    h = bj_now.hour + bj_now.minute / 60
    weekday = bj_now.weekday()  # 0=Mon ... 6=Sun

    # 周六(5) 或 周日(6)
    if weekday >= 5:
        return {
            "session": "weekend_afterhours",
            "session_label": "周末休市 → 获取周五收盘+盘后",
            "extended_type": "afterhours",
            "bj_time": bj_now.strftime("%Y-%m-%d %H:%M:%S CST"),
            "et_time": et_now.strftime("%Y-%m-%d %H:%M:%S EDT"),
            "bj_weekday": weekday,
        }

    # 工作日 07:00-15:00 → 获取盘后价
    if 7 <= h < 15:
        return {
            "session": "fetch_afterhours",
            "session_label": f"工作日白天(BJ {bj_now.strftime('%H:%M')}) → 获取盘后价",
            "extended_type": "afterhours",
            "bj_time": bj_now.strftime("%Y-%m-%d %H:%M:%S CST"),
            "et_time": et_now.strftime("%Y-%m-%d %H:%M:%S EDT"),
            "bj_weekday": weekday,
        }

    # 工作日 15:00-23:00 → 获取盘前价
    if 15 <= h < 23:
        return {
            "session": "fetch_premarket",
            "session_label": f"工作日晚间(BJ {bj_now.strftime('%H:%M')}) → 获取盘前价",
            "extended_type": "premarket",
            "bj_time": bj_now.strftime("%Y-%m-%d %H:%M:%S CST"),
            "et_time": et_now.strftime("%Y-%m-%d %H:%M:%S EDT"),
            "bj_weekday": weekday,
        }

    # 其他时段（23:00-07:00）→ 美股盘中或盘后早期 → 获取盘后
    return {
        "session": "fetch_afterhours",
        "session_label": f"夜间/盘后(BJ {bj_now.strftime('%H:%M')}) → 获取盘后价",
        "extended_type": "afterhours",
        "bj_time": bj_now.strftime("%Y-%m-%d %H:%M:%S CST"),
        "et_time": et_now.strftime("%Y-%m-%d %H:%M:%S EDT"),
        "bj_weekday": weekday,
    }


def fetch_westock_quote(symbols: List[str]) -> Dict[str, Dict]:
    """通过 westock-data 获取最新收盘行情。"""
    codes = [WESTOCK_CODE_MAP.get(s.upper(), s) for s in symbols]
    code_str = ",".join(codes)
    result = {}
    try:
        proc = subprocess.run(
            ["node", WESTOCK_SCRIPT, "quote", code_str],
            capture_output=True, text=True, timeout=30,
            cwd="/data/workspace/.agent/skills/westock-data"
        )
        lines = [l for l in proc.stdout.split("\n") if l.startswith("| us")]
        for line in lines:
            parts = [p.strip() for p in line.split("|")[1:-1]]
            code = parts[0]
            sym = code.replace("us", "").split(".")[0]
            try:
                high_52w = float(parts[33])
                price = float(parts[5])
                dist = (price - high_52w) / high_52w * 100 if high_52w else 0
                result[sym] = {
                    "name": parts[3],
                    "close_price": price,
                    "prev_close": float(parts[6]),
                    "open": float(parts[7]),
                    "high": float(parts[16]),
                    "low": float(parts[17]),
                    "pct_1d": float(parts[15]),
                    "volume": int(parts[8]),
                    "amount": float(parts[18]),
                    "volume_ratio": float(parts[20]) if parts[20] else None,
                    "pe": float(parts[22]) if parts[22] else None,
                    "high_52w": high_52w,
                    "low_52w": float(parts[34]),
                    "dist_from_52w_high_pct": round(dist, 2),
                    "trading_date_et": parts[13],
                }
            except (ValueError, IndexError) as e:
                result[sym] = {"error": f"parse_fail: {e}"}
    except Exception as e:
        return {"_error": str(e)}
    return result


def fetch_sina_extended(symbols: List[str], extended_type: str) -> Dict[str, Dict]:
    """从新浪 gb_ 接口获取扩展时段价格（盘前 or 盘后）。

    [21] 是动态字段：盘前时段放盘前价，盘后时段放盘后价。
    [24] 的时间戳用来区分是 AM（盘前）还是 PM（盘后）。

    Args:
        extended_type: 'premarket' 或 'afterhours'，决定如何标注返回字段
    """
    sym_lower = ",".join([f"gb_{s.lower()}" for s in symbols])
    url = f"https://hq.sinajs.cn/list={sym_lower}"
    req = urllib.request.Request(url, headers={"Referer": "https://finance.sina.com.cn"})
    try:
        raw = urllib.request.urlopen(req, timeout=8).read().decode("gbk", errors="ignore")
    except Exception as e:
        return {"_error": f"sina_fetch_fail: {e}"}

    result = {}
    for line in raw.strip().split("\n"):
        if not line.startswith("var "):
            continue
        try:
            sym = line.split("=")[0].replace("var hq_str_gb_", "").strip().upper()
            data_str = line.split('"', 1)[1].rsplit('"', 1)[0]
            parts = data_str.split(",")
            if len(parts) < 34:
                result[sym] = {"extended_price": None, "reason": "fields_insufficient"}
                continue

            def safe_float(idx):
                v = parts[idx].strip() if idx < len(parts) else ''
                if not v or v == '--':
                    return None
                try:
                    return float(v)
                except ValueError:
                    return None

            def safe_int(idx):
                v = parts[idx].strip() if idx < len(parts) else ''
                try:
                    return int(v)
                except ValueError:
                    return 0

            close_price = safe_float(1)     # 最新收盘价
            ext_price   = safe_float(21)    # 盘前/盘后价（动态）
            ext_pct     = safe_float(22)    # 对比收盘的涨跌%
            ext_chg     = safe_float(23)    # 对比收盘的涨跌额
            ext_time    = parts[24].strip() if len(parts) > 24 else ''
            close_time  = parts[25].strip() if len(parts) > 25 else ''
            ext_vol     = safe_int(27)
            ext_high    = safe_float(31)
            ext_low     = safe_float(32)
            ext_amt     = safe_float(33)

            has_activity = (ext_price is not None and ext_vol > 0)

            if has_activity:
                result[sym] = {
                    "close_price_sina": close_price,
                    "extended_price": ext_price,
                    "extended_pct": ext_pct,
                    "extended_change": ext_chg,
                    "extended_volume": ext_vol,
                    "extended_high": ext_high,
                    "extended_low": ext_low,
                    "extended_amount": ext_amt,
                    "extended_time_et": ext_time,
                    "close_time_et": close_time,
                    "timestamp": parts[3].strip(),
                    "extended_type": extended_type,
                    "reason": "ok",
                }
            else:
                result[sym] = {
                    "close_price_sina": close_price,
                    "extended_price": None,
                    "extended_volume": ext_vol,
                    "extended_time_et": ext_time,
                    "timestamp": parts[3].strip(),
                    "extended_type": extended_type,
                    "reason": "no_extended_activity",
                }
        except Exception as e:
            continue
    return result


def fetch_all(symbols: List[str]) -> Dict:
    """主入口：根据时段自动选择抓取盘前/盘后/周末数据。"""
    session = detect_market_session()
    ext_type = session["extended_type"]  # 'premarket' or 'afterhours'

    # 获取 westock-data 最新收盘行情
    westock = fetch_westock_quote(symbols)

    # 获取新浪扩展时段数据（盘前 or 盘后）
    sina_ext = fetch_sina_extended(symbols, ext_type)

    out = {
        "meta": session,
        "stocks": {}
    }

    for sym in symbols:
        sym_u = sym.upper()
        q = westock.get(sym_u, {})
        if "error" in q or not q:
            out["stocks"][sym_u] = {"error": q.get("error", "no_data")}
            continue

        ext = sina_ext.get(sym_u, {})
        ext_price = ext.get("extended_price")
        close_price = q.get("close_price")

        # 如果新浪的 [1] 收盘价比 westock 更新（例如盘后时段新浪已更新为当天收盘，westock 还没刷新）
        # 优先信任新浪的 [1]
        sina_close = ext.get("close_price_sina")
        if sina_close and close_price and abs(sina_close - close_price) > 0.5:
            # 新浪收盘价更新了，用新浪的
            close_price = sina_close
            q["close_price"] = sina_close
            # 重算距52w高
            if q.get("high_52w"):
                q["dist_from_52w_high_pct"] = round(
                    (close_price - q["high_52w"]) / q["high_52w"] * 100, 2)

        # 自算扩展时段涨跌%
        ext_pct = None
        ext_note = ext.get("reason")
        if ext_price is not None and close_price and close_price > 0:
            ext_pct = round((ext_price - close_price) / close_price * 100, 2)

        # 判断异常信号
        abnormal = []
        if abs(q.get("pct_1d", 0)) > 4:
            abnormal.append(f"日涨跌>4%({q['pct_1d']:+.2f}%)")
        if q.get("volume_ratio") and q["volume_ratio"] > 2:
            abnormal.append(f"量比>2({q['volume_ratio']:.2f})")
        if q.get("dist_from_52w_high_pct", -100) > -0.5:
            abnormal.append("接近52w新高")
        if ext_pct is not None and abs(ext_pct) > 4:
            label = "盘前" if ext_type == "premarket" else "盘后"
            abnormal.append(f"{label}>4%({ext_pct:+.2f}%)")

        # 统一输出字段名
        # 为兼容前端和上游，同时输出 premarket_* 和 afterhours_* 风格
        # 用 extended_* 作为统一前缀，再根据 ext_type 映射具体字段名
        stock_out = {
            **q,
            "extended_type": ext_type,
            "extended_price": ext_price,
            "extended_pct_vs_close": ext_pct,
            "extended_volume": ext.get("extended_volume"),
            "extended_high": ext.get("extended_high"),
            "extended_low": ext.get("extended_low"),
            "extended_amount": ext.get("extended_amount"),
            "extended_time_et": ext.get("extended_time_et"),
            "extended_note": ext_note,
            "extended_timestamp": ext.get("timestamp"),
            "abnormal_signals": abnormal,
        }

        # 兼容旧字段名（premarket_price / afterhours_price）
        if ext_type == "premarket":
            stock_out["premarket_price"] = ext_price
            stock_out["premarket_pct_vs_close"] = ext_pct
            stock_out["premarket_note"] = ext_note
        else:
            stock_out["afterhours_price"] = ext_price
            stock_out["afterhours_pct_vs_close"] = ext_pct
            stock_out["afterhours_note"] = ext_note

        out["stocks"][sym_u] = stock_out

    return out


if __name__ == "__main__":
    import sys
    syms = sys.argv[1].split(",") if len(sys.argv) > 1 else list(WESTOCK_CODE_MAP.keys())
    data = fetch_all(syms)
    print(json.dumps(data, ensure_ascii=False, indent=2))
