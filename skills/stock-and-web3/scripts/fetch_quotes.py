#!/usr/bin/env python3
"""
美股实时行情 + 盘前/盘后/盘中统一抓取工具（stock-and-web3 技能专用）v4

v4 新增（2026-04-30）：
  1. 盘中实时场景（北京 21:30-04:00 = 美东 09:30-16:00）
  2. RSI6 极端值自动预警（>85 或 <15）
  3. 新闻质量过滤（过滤纯成交额/成交量播报）
  4. 数据验证护栏（validate_report 函数）
  5. 关键事件日历（财报/除权日）
  6. 机构评级变动监控
  7. 板块关联分析（按赛道聚合）

时段策略：
    北京 07:00-15:00 工作日 → 获取盘后价 [21]
    北京 15:00-21:30 工作日 → 获取盘前价 [21]
    北京 21:30-04:00 (次日) → 盘中实时 [1]（此时 [1] 是盘中动态更新的实时价）
    北京 04:00-07:00         → 盘后 [21]
    周六/周日               → 周五收盘+盘后
"""
import json
import os
import re
import subprocess
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from pathlib import Path

# westock-data 代码映射
WESTOCK_CODE_MAP = {
    "MU":   "usMU.OQ",
    "AMD":  "usAMD.OQ",
    "INTC": "usINTC.OQ",
    "GOOG": "usGOOG.OQ",
    "NVDA": "usNVDA.OQ",
    "NBIS": "usNBIS.OQ",
    "CRWV": "usCRWV.OQ",
    "CRCL": "usCRCL.N",
    "MSTR": "usMSTR.OQ",
    "TSLA": "usTSLA.OQ",
    "XPEV": "usXPEV.N",
}

# 板块分组
SECTOR_MAP = {
    "半导体": ["MU", "AMD", "INTC", "NVDA"],
    "科技巨头": ["GOOG"],
    "AI基建": ["NBIS", "CRWV"],
    "Crypto": ["CRCL", "MSTR"],
    "新能源车": ["TSLA", "XPEV"],
}

WESTOCK_SCRIPT = "/data/workspace/.agent/skills/westock-data/scripts/index.js"

# 新闻过滤关键词（这些是无意义的成交额/成交量播报）
NEWS_FILTER_KEYWORDS = [
    "成交额为", "成交量为", "成交额达", "成交量达",
    "日成交额", "日成交量",
]


def detect_market_session() -> Dict:
    """根据北京时间判断时段，新增盘中实时支持。"""
    bj_now = datetime.now(timezone(timedelta(hours=8)))
    et_now = bj_now.astimezone(timezone(timedelta(hours=-4)))
    h = bj_now.hour + bj_now.minute / 60
    weekday = bj_now.weekday()

    if weekday >= 5:
        return {
            "session": "weekend_afterhours",
            "session_label": "周末休市 → 获取周五收盘+盘后",
            "extended_type": "afterhours",
            "bj_time": bj_now.strftime("%Y-%m-%d %H:%M:%S CST"),
            "et_time": et_now.strftime("%Y-%m-%d %H:%M:%S EDT"),
            "bj_weekday": weekday,
        }

    # 盘中实时：北京 21:30-次日 04:00（美东 09:30-16:00）
    if h >= 21.5 or h < 4:
        return {
            "session": "fetch_realtime",
            "session_label": f"美股盘中(BJ {bj_now.strftime('%H:%M')}) → 获取实时价",
            "extended_type": "realtime",
            "bj_time": bj_now.strftime("%Y-%m-%d %H:%M:%S CST"),
            "et_time": et_now.strftime("%Y-%m-%d %H:%M:%S EDT"),
            "bj_weekday": weekday,
        }

    # 盘后：北京 04:00-07:00
    if 4 <= h < 7:
        return {
            "session": "fetch_afterhours",
            "session_label": f"盘后(BJ {bj_now.strftime('%H:%M')}) → 获取盘后价",
            "extended_type": "afterhours",
            "bj_time": bj_now.strftime("%Y-%m-%d %H:%M:%S CST"),
            "et_time": et_now.strftime("%Y-%m-%d %H:%M:%S EDT"),
            "bj_weekday": weekday,
        }

    # 白天休市+盘后数据：07:00-15:00
    if 7 <= h < 15:
        return {
            "session": "fetch_afterhours",
            "session_label": f"工作日白天(BJ {bj_now.strftime('%H:%M')}) → 获取盘后价",
            "extended_type": "afterhours",
            "bj_time": bj_now.strftime("%Y-%m-%d %H:%M:%S CST"),
            "et_time": et_now.strftime("%Y-%m-%d %H:%M:%S EDT"),
            "bj_weekday": weekday,
        }

    # 盘前：15:00-21:30
    return {
        "session": "fetch_premarket",
        "session_label": f"工作日晚间(BJ {bj_now.strftime('%H:%M')}) → 获取盘前价",
        "extended_type": "premarket",
        "bj_time": bj_now.strftime("%Y-%m-%d %H:%M:%S CST"),
        "et_time": et_now.strftime("%Y-%m-%d %H:%M:%S EDT"),
        "bj_weekday": weekday,
    }


def _run_westock(cmd_args: List[str], timeout: int = 30) -> str:
    """运行 westock-data 命令并返回 stdout。"""
    proc = subprocess.run(
        ["node", WESTOCK_SCRIPT] + cmd_args,
        capture_output=True, text=True, timeout=timeout,
        cwd="/data/workspace/.agent/skills/westock-data"
    )
    return proc.stdout


def fetch_westock_quote(symbols: List[str]) -> Dict[str, Dict]:
    """通过 westock-data 获取最新收盘行情。"""
    codes = [WESTOCK_CODE_MAP.get(s.upper(), s) for s in symbols]
    result = {}
    try:
        stdout = _run_westock(["quote", ",".join(codes)])
        lines = [l for l in stdout.split("\n") if l.startswith("| us")]
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


def fetch_westock_technical(symbols: List[str]) -> Dict[str, Dict]:
    """获取技术指标（RSI6 / KDJ / MA 等）。"""
    codes = [WESTOCK_CODE_MAP.get(s.upper(), s) for s in symbols]
    result = {}
    try:
        stdout = _run_westock(["technical", ",".join(codes)])
        # 找表头确认 RSI6 位置
        header_line = None
        data_lines = []
        for line in stdout.split("\n"):
            if line.startswith("| code"):
                header_line = line
            elif line.startswith("| us"):
                data_lines.append(line)

        if not header_line:
            return result

        headers = [h.strip() for h in header_line.split("|")[1:-1]]
        rsi6_idx = None
        kdj_k_idx = None
        for i, h in enumerate(headers):
            if h == "rsi.RSI_6":
                rsi6_idx = i
            elif h == "kdj.KDJ_K":
                kdj_k_idx = i

        for line in data_lines:
            parts = [p.strip() for p in line.split("|")[1:-1]]
            sym = parts[0].replace("us", "").split(".")[0]
            try:
                rsi6 = float(parts[rsi6_idx]) if rsi6_idx and parts[rsi6_idx] not in ['-', ''] else None
                kdj_k = float(parts[kdj_k_idx]) if kdj_k_idx and parts[kdj_k_idx] not in ['-', ''] else None
                result[sym] = {"rsi6": rsi6, "kdj_k": kdj_k}
            except (ValueError, IndexError):
                pass
    except Exception:
        pass
    return result


def fetch_westock_news(symbols: List[str]) -> Dict[str, List[str]]:
    """获取新闻并过滤低质量内容。"""
    codes = [WESTOCK_CODE_MAP.get(s.upper(), s) for s in symbols]
    result = {s.upper(): [] for s in symbols}
    try:
        stdout = _run_westock(["news", ",".join(codes), "--type", "3", "--limit", "4"])
        current_sym = None
        for line in stdout.split("\n"):
            m = re.match(r'\*\*(us(\w+)\.\w+)\*\*', line)
            if m:
                current_sym = m.group(2)
                continue
            if current_sym and line.startswith("|") and "time" not in line and "---" not in line:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) > 5 and parts[5]:
                    title = parts[5][:100]
                    # 过滤低质量新闻
                    if not any(kw in title for kw in NEWS_FILTER_KEYWORDS):
                        if current_sym in result and len(result[current_sym]) < 2:
                            result[current_sym].append(title)
    except Exception:
        pass
    return result


def fetch_westock_rating(symbols: List[str]) -> Dict[str, Dict]:
    """获取机构评级。"""
    codes = [WESTOCK_CODE_MAP.get(s.upper(), s) for s in symbols]
    result = {}
    try:
        stdout = _run_westock(["rating", ",".join(codes)])
        current_sym = None
        for line in stdout.split("\n"):
            m = re.match(r'\*\*(us(\w+)\.\w+)\*\*', line)
            if m:
                current_sym = m.group(2)
                continue
            if current_sym and line.startswith("|") and "---" not in line and "time" not in line:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) > 6 and parts[1] and current_sym not in result:
                    result[current_sym] = {
                        "date": parts[1][:10] if len(parts) > 1 else "",
                        "institution": parts[3][:20] if len(parts) > 3 else "",
                        "rating": parts[4] if len(parts) > 4 else "",
                        "target_price": parts[5] if len(parts) > 5 else "",
                    }
    except Exception:
        pass
    return result


def fetch_westock_events(symbols: List[str]) -> Dict[str, List[Dict]]:
    """获取关键事件日历（财报披露日 + 分红除权日）。"""
    codes = [WESTOCK_CODE_MAP.get(s.upper(), s) for s in symbols]
    result = {s.upper(): [] for s in symbols}
    try:
        # 财报披露日
        stdout = _run_westock(["reserve", ",".join(codes)])
        current_sym = None
        for line in stdout.split("\n"):
            m = re.match(r'\*\*(us(\w+)\.\w+)\*\*', line)
            if m:
                current_sym = m.group(2)
                continue
            if current_sym and line.startswith("|") and "---" not in line and "date" not in line.lower():
                parts = [p.strip() for p in line.split("|")]
                if len(parts) > 2 and parts[1]:
                    result.setdefault(current_sym, []).append({
                        "type": "earnings",
                        "date": parts[1][:10],
                        "detail": parts[2] if len(parts) > 2 else "",
                    })
    except Exception:
        pass

    try:
        # 分红除权日
        stdout = _run_westock(["exdiv", ",".join(codes)])
        current_sym = None
        for line in stdout.split("\n"):
            m = re.match(r'\*\*(us(\w+)\.\w+)\*\*', line)
            if m:
                current_sym = m.group(2)
                continue
            if current_sym and line.startswith("|") and "---" not in line and "date" not in line.lower():
                parts = [p.strip() for p in line.split("|")]
                if len(parts) > 2 and parts[1]:
                    result.setdefault(current_sym, []).append({
                        "type": "exdiv",
                        "date": parts[1][:10],
                        "detail": parts[2] if len(parts) > 2 else "",
                    })
    except Exception:
        pass
    return result


def fetch_sina_extended(symbols: List[str], extended_type: str) -> Dict[str, Dict]:
    """从新浪 gb_ 接口获取扩展时段价格（盘前/盘后/盘中实时）。"""
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

            close_price = safe_float(1)
            ext_time = parts[24].strip() if len(parts) > 24 else ''
            close_time = parts[25].strip() if len(parts) > 25 else ''

            if extended_type == "realtime":
                # 盘中实时：[1] 就是实时价，不需要 [21]
                result[sym] = {
                    "close_price_sina": close_price,
                    "extended_price": close_price,  # 盘中 [1] = 实时价
                    "extended_pct": safe_float(2),   # [2] vs prev_close
                    "extended_change": safe_float(4),
                    "extended_volume": safe_int(10),
                    "extended_high": safe_float(6),
                    "extended_low": safe_float(7),
                    "extended_amount": None,
                    "extended_time_et": close_time or ext_time,
                    "close_time_et": close_time,
                    "timestamp": parts[3].strip(),
                    "extended_type": "realtime",
                    "reason": "ok" if close_price else "no_data",
                }
            else:
                ext_price = safe_float(21)
                ext_pct = safe_float(22)
                ext_chg = safe_float(23)
                ext_vol = safe_int(27)
                ext_high = safe_float(31)
                ext_low = safe_float(32)
                ext_amt = safe_float(33)
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
        except Exception:
            continue
    return result


def compute_sector_analysis(stocks: Dict) -> List[Dict]:
    """板块关联分析：按赛道聚合涨跌。"""
    sectors = []
    for sector_name, syms in SECTOR_MAP.items():
        pcts = []
        details = []
        for s in syms:
            if s in stocks and "error" not in stocks[s]:
                pct = stocks[s].get("pct_1d", 0)
                pcts.append(pct)
                details.append(f"{s} {pct:+.2f}%")
        if pcts:
            avg = sum(pcts) / len(pcts)
            sectors.append({
                "sector": sector_name,
                "avg_pct": round(avg, 2),
                "stocks": details,
                "count": len(pcts),
            })
    sectors.sort(key=lambda x: x["avg_pct"], reverse=True)
    return sectors


def fetch_all(symbols: List[str], include_extras: bool = True) -> Dict:
    """主入口：根据时段自动选择抓取策略。
    
    Args:
        include_extras: 是否获取技术指标/新闻/评级/事件（周报场景可关闭以加速）
    """
    session = detect_market_session()
    ext_type = session["extended_type"]

    westock = fetch_westock_quote(symbols)
    sina_ext = fetch_sina_extended(symbols, ext_type)

    # 可选数据
    tech_data = {}
    news_data = {}
    rating_data = {}
    events_data = {}
    if include_extras:
        tech_data = fetch_westock_technical(symbols)
        news_data = fetch_westock_news(symbols)
        rating_data = fetch_westock_rating(symbols)
        events_data = fetch_westock_events(symbols)

    out = {"meta": session, "stocks": {}}

    for sym in symbols:
        sym_u = sym.upper()
        q = westock.get(sym_u, {})
        if "error" in q or not q:
            out["stocks"][sym_u] = {"error": q.get("error", "no_data")}
            continue

        ext = sina_ext.get(sym_u, {})
        ext_price = ext.get("extended_price")
        close_price = q.get("close_price")

        # 新浪 [1] 更新优先
        sina_close = ext.get("close_price_sina")
        if sina_close and close_price and abs(sina_close - close_price) > 0.5:
            close_price = sina_close
            q["close_price"] = sina_close
            if q.get("high_52w"):
                q["dist_from_52w_high_pct"] = round(
                    (close_price - q["high_52w"]) / q["high_52w"] * 100, 2)

        # 自算扩展时段涨跌%
        ext_pct = None
        ext_note = ext.get("reason")
        if ext_type == "realtime":
            # 盘中实时：涨跌% 直接用接口的（[2] = 当前价 vs 昨收）
            ext_pct = ext.get("extended_pct")
        elif ext_price is not None and close_price and close_price > 0:
            ext_pct = round((ext_price - close_price) / close_price * 100, 2)

        # 技术指标
        tech = tech_data.get(sym_u, {})
        rsi6 = tech.get("rsi6")

        # 异常信号（新增 RSI6 极端值）
        abnormal = []
        if abs(q.get("pct_1d", 0)) > 4:
            abnormal.append(f"日涨跌>4%({q['pct_1d']:+.2f}%)")
        if q.get("volume_ratio") and q["volume_ratio"] > 2:
            abnormal.append(f"量比>2({q['volume_ratio']:.2f})")
        if q.get("dist_from_52w_high_pct", -100) > -0.5:
            abnormal.append("接近52w新高")
        if rsi6 is not None and rsi6 > 85:
            abnormal.append(f"RSI6超买({rsi6:.1f})")
        if rsi6 is not None and rsi6 < 15:
            abnormal.append(f"RSI6超卖({rsi6:.1f})")
        if ext_pct is not None and abs(ext_pct) > 4:
            label = {"premarket": "盘前", "afterhours": "盘后", "realtime": "盘中"}.get(ext_type, "")
            abnormal.append(f"{label}>4%({ext_pct:+.2f}%)")

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
            "rsi6": rsi6,
            "kdj_k": tech.get("kdj_k"),
            "news": news_data.get(sym_u, []),
            "latest_rating": rating_data.get(sym_u),
            "upcoming_events": events_data.get(sym_u, []),
            "abnormal_signals": abnormal,
        }

        # 兼容旧字段名
        if ext_type == "premarket":
            stock_out["premarket_price"] = ext_price
            stock_out["premarket_pct_vs_close"] = ext_pct
            stock_out["premarket_note"] = ext_note
        elif ext_type == "afterhours":
            stock_out["afterhours_price"] = ext_price
            stock_out["afterhours_pct_vs_close"] = ext_pct
            stock_out["afterhours_note"] = ext_note
        else:
            stock_out["realtime_price"] = ext_price
            stock_out["realtime_pct"] = ext_pct

        out["stocks"][sym_u] = stock_out

    # 板块关联分析
    out["sector_analysis"] = compute_sector_analysis(out["stocks"])

    return out


def validate_report(json_path: str, png_path: str, num_stocks: int = 9) -> List[str]:
    """数据验证护栏：检查报告 JSON 和图片完整性。返回错误列表（空=通过）。"""
    errors = []

    # 1. JSON 文件存在且可解析
    p = Path(json_path)
    if not p.exists():
        errors.append(f"JSON 不存在: {json_path}")
        return errors
    try:
        d = json.load(open(json_path))
    except Exception as e:
        errors.append(f"JSON 解析失败: {e}")
        return errors

    # 2. 必填字段
    required = ['slug', 'date', 'generated_at', 'title', 'has_stock', 'has_web3',
                 'image', 'stock_body_html', 'web3_body_html', 'tickers']
    for k in required:
        if k not in d:
            errors.append(f"JSON 缺少字段: {k}")

    # 3. has_stock / has_web3 必须是 bool
    if d.get('has_stock') is not True:
        errors.append(f"has_stock 不是 True: {d.get('has_stock')}")
    if d.get('has_web3') is not True:
        errors.append(f"has_web3 不是 True: {d.get('has_web3')}")

    # 4. stock_body_html 逐股详解数量
    h4_count = len(re.findall(r'<h4>', d.get('stock_body_html', '')))
    if h4_count < num_stocks:
        errors.append(f"逐股详解 <h4> 只有 {h4_count} 个，应为 {num_stocks}")

    # 5. stock_body_html 最小长度
    if len(d.get('stock_body_html', '')) < 3000:
        errors.append(f"stock_body_html 太短: {len(d.get('stock_body_html', ''))} 字符")

    # 6. 图片文件存在且 >= 20KB
    pp = Path(png_path)
    if not pp.exists():
        errors.append(f"图片不存在: {png_path}")
    elif pp.stat().st_size < 20 * 1024:
        errors.append(f"图片太小: {pp.stat().st_size} bytes (< 20KB)")

    return errors


if __name__ == "__main__":
    import sys
    syms = sys.argv[1].split(",") if len(sys.argv) > 1 else list(WESTOCK_CODE_MAP.keys())
    data = fetch_all(syms)
    print(json.dumps(data, ensure_ascii=False, indent=2))
