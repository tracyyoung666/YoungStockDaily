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
    **关键**：只在盘前时段调用；拉到的盘前价必须跟"昨收"对比后才算真盘前涨跌。

    新浪 gb_ 接口字段顺序（36 字段）：
        [0] 名称            [1] 当前报价（盘前/盘中/盘后实时）
        [2] 累计涨跌%       [3] 时间戳（北京时间）
        [4] 涨跌额          [5] 今开      [6] 最高     [7] 最低
        [8] 52w高           [9] 52w低     [10] 成交量  [11] 均量
        ...
        [25] 美东时间      [26] 美东前收盘价（T-1交易日收盘）
        ...
        [-4] 盘前一笔价    [-3] 盘前累计额  [-2] 盘前高  [-1] 盘前最新价

    **重要**：当前处于盘前阶段时，[1] 可能仍是 T日收盘价（即北京昨收），
    真正的盘前实时价要看最后 4 个字段（-4 ~ -1）。若最后几个字段与 [1] 完全一致，
    说明盘前尚无有效成交，返回 None。
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
            if len(parts) < 30:
                result[sym] = {"premarket_price": None, "reason": "fields_insufficient"}
                continue

            # 最新报价字段 [1]（可能是盘前/盘中/盘后）
            current_price = float(parts[1]) if parts[1] else None
            timestamp = parts[3]  # 北京时间
            # 盘前/盘后最新一笔 —— 最后一个数字字段
            pre_last = None
            for candidate in reversed(parts):
                try:
                    pre_last = float(candidate.strip())
                    break
                except ValueError:
                    continue
            # 判断：如果 [1] 与最后一笔价完全一致，认为没有真盘前成交
            if current_price is not None and pre_last is not None and abs(current_price - pre_last) < 0.001:
                # 但也要看 [1] 对应的时间戳是否就是今天 —— 若时间戳是今天，而其他迹象也说明盘前无成交，返回 None
                result[sym] = {
                    "sina_current": current_price,
                    "premarket_price": None,
                    "timestamp": timestamp,
                    "reason": "no_premarket_activity",
                }
            else:
                result[sym] = {
                    "sina_current": current_price,
                    "premarket_price": pre_last,
                    "timestamp": timestamp,
                    "reason": "ok",
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
        pre_price_raw = pre.get("premarket_price")

        # 二次校验：如果盘前价与昨收完全一致（差值 < 1 分），视为盘前无有效成交
        pre_price = None
        pre_pct = None
        pre_note = pre.get("reason")
        if pre_price_raw is not None and close_price:
            if abs(pre_price_raw - close_price) < 0.01:
                pre_note = "no_premarket_activity"
            else:
                pre_price = pre_price_raw
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
