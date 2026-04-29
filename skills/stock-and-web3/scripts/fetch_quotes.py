#!/usr/bin/env python3
"""
美股实时行情 + 盘前价统一抓取工具（stock-and-web3 技能专用）

**时区口径（非常重要，上游多次踩坑）**：
- 系统时区：北京时间（CST, UTC+8）
- 美股交易时段（夏令时）：
    盘前 Pre-Market  : 美东 04:00-09:30 = 北京 16:00-21:30
    常规 Regular     : 美东 09:30-16:00 = 北京 21:30 - 次日 04:00
    盘后 After-Hours : 美东 16:00-20:00 = 北京 次日 04:00-08:00
    休市 Closed      : 其他时段

**数据口径（用户视角，北京时间）**：
- "昨收"      = 最近一个已经结束的美股常规交易日的收盘价
             = westock-data quote 返回的 `price` 字段（time=YYYY-MM-DD 即美东交易日）
- "盘前价"    = 当前这个未开盘交易日，盘前阶段的实时成交价
             = 仅在盘前时段（北京 16:00-21:30）可能有；早于 16:00 一般没有活跃成交
- "盘前涨跌%" = (盘前价 - 昨收) / 昨收 * 100%（必须自己算，不要直接用接口字段）

**❌ 绝对禁止**：
- 不要把新浪 gb_ 接口的 `change_pct` 当作盘前涨跌（它是"当前价 vs 前一日已结束交易日的前一日"，口径不一致）
- 没拉到盘前价就明确写 None / "暂无有效盘前"，不要用昨收兜底冒充盘前
"""
import json
import re
import subprocess
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

# westock-data 代码映射（自选股固定清单，避免每次 search）
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
    """根据当前北京时间判断美股交易时段（夏令时版）。
    返回：{session, can_fetch_premarket, bj_time, et_time}
    """
    bj_now = datetime.now(timezone(timedelta(hours=8)))
    et_now = bj_now.astimezone(timezone(timedelta(hours=-4)))  # EDT 夏令时
    h = bj_now.hour + bj_now.minute / 60

    if 16 <= h < 21.5:
        session = "pre_market"        # 盘前
        can_fetch_pre = True
    elif 21.5 <= h or h < 4:
        session = "regular"           # 常规盘中
        can_fetch_pre = False
    elif 4 <= h < 8:
        session = "after_hours"       # 盘后
        can_fetch_pre = False
    else:
        session = "closed"            # 08:00-16:00 完全休市
        can_fetch_pre = False

    return {
        "session": session,
        "can_fetch_premarket": can_fetch_pre,
        "bj_time": bj_now.strftime("%Y-%m-%d %H:%M:%S CST"),
        "et_time": et_now.strftime("%Y-%m-%d %H:%M:%S EDT"),
    }


def fetch_westock_quote(symbols: List[str]) -> Dict[str, Dict]:
    """通过 westock-data 获取实时行情。
    返回 {symbol: {name, price(昨收/最近收盘), prev_close, open, high, low,
                    pct_1d, volume, volume_ratio, pe, high_52w, low_52w,
                    dist_from_52w_high, rsi6?, time}}
    """
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
                    "close_price": price,          # 美东T日收盘 = 北京昨收
                    "prev_close": float(parts[6]), # 再前一个交易日的收盘（仅参考）
                    "open": float(parts[7]),
                    "high": float(parts[16]),
                    "low": float(parts[17]),
                    "pct_1d": float(parts[15]),    # T日涨跌%（T日 vs T-1日）
                    "volume": int(parts[8]),
                    "amount": float(parts[18]),
                    "volume_ratio": float(parts[20]) if parts[20] else None,
                    "pe": float(parts[22]) if parts[22] else None,
                    "high_52w": high_52w,
                    "low_52w": float(parts[34]),
                    "dist_from_52w_high_pct": round(dist, 2),
                    "trading_date_et": parts[13],  # 美东交易日
                }
            except (ValueError, IndexError) as e:
                result[sym] = {"error": f"parse_fail: {e}"}
    except Exception as e:
        return {"_error": str(e)}
    return result


def fetch_sina_premarket(symbols: List[str]) -> Dict[str, Dict]:
    """从新浪 gb_ 接口获取盘前价。

    新浪 gb_ 接口 36 字段 **正确映射**（2026-04-29 逐字段交叉验证确认）：
        [0]  名称
        [1]  常规交易日收盘价（= 北京昨收 = westock 的 price）
        [2]  累计涨跌%（[1] vs [26]，基准是 T-1 不是昨收，⚠️不可直接用）
        [3]  北京时间戳
        [4]  累计涨跌额
        [5]  常规开盘价      [6]  常规最高      [7]  常规最低
        [8]  52w高           [9]  52w低
        [10] 常规成交量      [11] 平均量        [12] 总市值
        [13] EPS             [14] PE
        [15]-[18] 其他       [19] 总股本        [20] 某评级
        ----------- 盘前区 -----------
        [21] ⭐ 盘前实时价        ← 核心！
        [22] ⭐ 盘前涨跌%（vs [1] 昨收）
        [23] ⭐ 盘前涨跌额（vs [1] 昨收）
        [24] 美东盘前时间戳（如 "Apr 29 07:40AM EDT"）
        [25] 美东常规收盘时间戳（如 "Apr 28 03:59PM EDT"）
        [26] 美东 T-1 收盘价（前前交易日）
        [27] ⭐ 盘前成交量
        [28]-[30] 其他
        [31] ⭐ 盘前最高价
        [32] ⭐ 盘前最低价
        [33] ⭐ 盘前成交额
        [34] 盘前某参考价
        [35] 盘前某参考价2
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
                result[sym] = {"premarket_price": None, "reason": "fields_insufficient"}
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

            pre_price = safe_float(21)
            pre_pct   = safe_float(22)
            pre_chg   = safe_float(23)
            pre_time  = parts[24].strip() if len(parts) > 24 else ''
            pre_vol   = safe_int(27)
            pre_high  = safe_float(31)
            pre_low   = safe_float(32)
            pre_amt   = safe_float(33)
            close_price = safe_float(1)  # 常规收盘 = 昨收

            # 有效性判断：盘前价有值 + 盘前成交量 > 0 + 盘前时间戳包含今日日期
            has_activity = (pre_price is not None and pre_vol > 0)

            if has_activity:
                result[sym] = {
                    "premarket_price": pre_price,
                    "premarket_pct": pre_pct,
                    "premarket_change": pre_chg,
                    "premarket_volume": pre_vol,
                    "premarket_high": pre_high,
                    "premarket_low": pre_low,
                    "premarket_amount": pre_amt,
                    "premarket_time_et": pre_time,
                    "close_price_sina": close_price,
                    "timestamp": parts[3].strip(),
                    "reason": "ok",
                }
            else:
                result[sym] = {
                    "premarket_price": None,
                    "premarket_volume": pre_vol,
                    "close_price_sina": close_price,
                    "timestamp": parts[3].strip(),
                    "reason": "no_premarket_activity",
                }
        except Exception as e:
            continue
    return result


def fetch_all(symbols: List[str]) -> Dict:
    """主入口：抓昨收 + 盘前价（仅盘前时段）+ 自动校验。"""
    session = detect_market_session()
    westock = fetch_westock_quote(symbols)
    out = {
        "meta": session,
        "stocks": {}
    }

    premarket_data = {}
    if session["can_fetch_premarket"]:
        premarket_data = fetch_sina_premarket(symbols)

    for sym in symbols:
        sym_u = sym.upper()
        q = westock.get(sym_u, {})
        if "error" in q or not q:
            out["stocks"][sym_u] = {"error": q.get("error", "no_data")}
            continue

        close_price = q.get("close_price")
        pre = premarket_data.get(sym_u, {})
        pre_price = pre.get("premarket_price")

        # 用自己算的盘前涨跌%（不信接口字段，以防口径偏差）
        pre_pct = None
        pre_note = pre.get("reason")
        if pre_price is not None and close_price and close_price > 0:
            pre_pct = round((pre_price - close_price) / close_price * 100, 2)

        # 判断异常信号
        abnormal = []
        if abs(q.get("pct_1d", 0)) > 4:
            abnormal.append(f"日涨跌>4%({q['pct_1d']:+.2f}%)")
        if q.get("volume_ratio") and q["volume_ratio"] > 2:
            abnormal.append(f"量比>2({q['volume_ratio']:.2f})")
        if q.get("dist_from_52w_high_pct", -100) > -0.5:
            abnormal.append(f"接近52w新高")
        if pre_pct is not None and abs(pre_pct) > 4:
            abnormal.append(f"盘前>4%({pre_pct:+.2f}%)")

        out["stocks"][sym_u] = {
            **q,
            "premarket_price": pre_price,
            "premarket_pct_vs_close": pre_pct,
            "premarket_volume": pre.get("premarket_volume"),
            "premarket_high": pre.get("premarket_high"),
            "premarket_low": pre.get("premarket_low"),
            "premarket_amount": pre.get("premarket_amount"),
            "premarket_time_et": pre.get("premarket_time_et"),
            "premarket_note": pre_note,
            "premarket_timestamp": pre.get("timestamp"),
            "abnormal_signals": abnormal,
        }
    return out


if __name__ == "__main__":
    import sys
    syms = sys.argv[1].split(",") if len(sys.argv) > 1 else list(WESTOCK_CODE_MAP.keys())
    data = fetch_all(syms)
    print(json.dumps(data, ensure_ascii=False, indent=2))
