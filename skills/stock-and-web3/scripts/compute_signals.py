#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compute_signals.py · v1
择时分级下注信号引擎（SKILL.md 步骤 2.55）

在"纯指标超买超卖"之外引入 **趋势状态 + 右侧反弹/回调确认**，
输出六档信号与建议份额，解决三个原始缺陷：
  ① RSI 超卖钝化（下跌趋势中 RSI 长期趴低位，价格继续新低）
  ② 逻辑倒置（原规则把"暴跌中超卖"给最高档 = 接飞刀）
  ③ 无止损锚点（纯左侧买入无法回答"跌到哪算判断错了"）

档位与份额（1 份 = 单次计划投入基准金额）：
  Strong Buy▲▲  +2.0   择时·右侧确认（超卖 + 止跌 + 反弹确认 + 结构修复）
  定投Buy▲      +1.0   择时·左侧试探（超卖/深跌，反弹未确认；空头排列砍半 0.5）
  定投▲         +0.5   传统定投·机械扣款（无技术信号时保留参与度）
  观望—          0
  定投Sell▼     -1.0   冲高后回调达 5%（铁律一直译）
  Strong Sell▼▼ -2.0   冲高 + 回调达动态阈值 + 跌破 MA10

动态阈值（用户要求必须落在 5%~10%）：
  σ = 近20日日收益率标准差
  反弹确认 R = clamp(1.5σ, 5%, 10%)   买入侧（更严）
  回调确认 D = clamp(1.2σ, 5%, 10%)   卖出侧（更敏捷，避免利润回吐）
  实测 k=1.5 时 11/15 落在区间内，是最优系数（k=2.5 会让 11/15 全撞上限而退化）

用法：
  python3 compute_signals.py --quotes _quotes_raw.json \
      --performance ../../YoungStockDaily/data/performance.json \
      --state ../../portfolio/dca_state.json --out _signals.json
"""
import argparse
import json
import statistics as st
from datetime import datetime
from pathlib import Path

# ---------- 档位定义 ----------
TIERS = {
    'strong_buy':  {'label': 'Strong Buy▲▲', 'shares':  2.0, 'color': '#b91c1c'},
    'buy':         {'label': '定投Buy▲',      'shares':  1.0, 'color': '#dc2626'},
    'dca':         {'label': '定投▲',         'shares':  0.5, 'color': '#f59e0b'},
    'hold':        {'label': '观望—',         'shares':  0.0, 'color': '#6b7280'},
    'sell':        {'label': '定投Sell▼',     'shares': -1.0, 'color': '#16a34a'},
    'strong_sell': {'label': 'Strong Sell▼▼', 'shares': -2.0, 'color': '#15803d'},
}

# 空头排列下连续机械定投的上限，超过则暂停（防止在下跌趋势中被无限摊平）
BEAR_DCA_LIMIT = 4


# ---------- 基础工具 ----------
def ma(closes, n):
    """最近 n 日均值；数据不足时用现有最长（会在 notes 标注）。"""
    if not closes:
        return None
    seq = closes[-n:] if len(closes) >= n else closes
    return sum(seq) / len(seq)


def rsi_series(closes, period=6):
    """从收盘序列自算 RSI6，用于补齐 quote 的 rsi6 缺失，并支持"近5日内是否超卖"。"""
    if len(closes) < period + 1:
        return []
    out = []
    for i in range(period, len(closes)):
        gains, losses = [], []
        for j in range(i - period + 1, i + 1):
            ch = closes[j] - closes[j - 1]
            (gains if ch > 0 else losses).append(abs(ch))
        ag = sum(gains) / period
        al = sum(losses) / period
        if al == 0:
            out.append(100.0)
        else:
            rs = ag / al
            out.append(100 - 100 / (1 + rs))
    return out


def max_runup(closes):
    """区间内最大累计涨幅%（先低后高），用于判定"曾连续冲高"。"""
    best, lo = 0.0, closes[0]
    for c in closes[1:]:
        if c < lo:
            lo = c
        elif lo > 0:
            best = max(best, (c - lo) / lo * 100)
    return best


def is_fresh_surge(closes, window=10, recent=3, thresh=15.0, max_decline_days=3):
    """判定"当下刚冲高"：近 window 日内累计涨幅 > thresh，
    且区间最高点落在最近 recent 日内，且高点之后未出现连续 max_decline_days 天下跌。

    ⚠️ 两层时效约束都必要（2026-07-29 MU 实测踩坑）：
      · 只看"累计涨幅>15%"→ 早已结束的历史涨势会误判为当下冲高
      · 只加"高点在最近N日"→ 高点后已连跌数日、趋势确立的仍会漏网
        （MU 自 $990 连跌4天到 $820，高点恰卡在边界上通过，被误判 Strong Sell）
    冲高止盈保护的是"刚到顶的利润"，趋势已转跌的应交给买入侧或观望处理。
    """
    if len(closes) < 3:
        return False
    seg = closes[-window:]
    if max_runup(seg) <= thresh:
        return False
    hi_idx = seg.index(max(seg))
    if hi_idx < len(seg) - recent:
        return False
    # 高点之后连续下跌天数
    dec = 0
    for i in range(hi_idx + 1, len(seg)):
        if seg[i] < seg[i - 1]:
            dec += 1
        else:
            dec = 0
    return dec < max_decline_days


# ---------- 单只标的判定 ----------
def evaluate(sym, q, closes, dates, state, today):
    """返回该标的的完整信号 dict。q = _quotes_raw.json 中该股字段。"""
    notes = []
    cur = q.get('close_price')
    d52h = q.get('dist_from_52w_high_pct')
    pct1d = q.get('pct_1d')
    ext = q.get('extended_pct_vs_close')
    moves = [x for x in (pct1d, ext) if x is not None]
    drop_now = -min(moves) if moves else 0.0     # 当下最大跌幅（正数）
    red_flags = q.get('_red_flags', 0)           # 由基本面校验注入

    # ===== 序列与当前价对齐（关键：否则极值口径错乱）=====
    # performance.json 由逐日 quote --date 拼接，rate limit 会留下空洞导致序列滞后。
    # 若序列末日 ≠ 今日，必须把当前价并入，否则"当前价 < 序列最低点" → 反弹幅度算出负数。
    closes = list(closes)
    dates = list(dates)
    stale_days = None
    if cur is not None:
        if dates and dates[-1] == today:
            closes[-1] = cur                      # 同日则以最新价覆盖
        else:
            closes.append(cur)
            dates.append(today)
            if dates and len(dates) >= 2:
                stale_days = dates[-2]
    # 序列陈旧检测：末次有效日距今过远则趋势判定不可信
    if stale_days:
        try:
            gap = (datetime.strptime(today, '%Y-%m-%d')
                   - datetime.strptime(stale_days, '%Y-%m-%d')).days
        except Exception:
            gap = 0
        if gap > 5:
            notes.append(f'20日序列末次更新 {stale_days}（距今{gap}天），趋势判定降级')

    # ===== 数据充足性 =====
    enough = cur is not None and len(closes) >= 6
    if not enough:
        notes.append('20日序列缺失/不足6点，未做趋势确认')
    # 序列严重滞后（>5天）视同数据不足，禁止发 Strong 档
    seq_stale = bool(stale_days) and any('趋势判定降级' in n for n in notes)

    # ===== 波动率与动态阈值 =====
    sigma = R = D = None
    if enough:
        rets = [(closes[i] / closes[i - 1] - 1) * 100
                for i in range(1, len(closes)) if closes[i - 1]]
        if len(rets) >= 3:
            sigma = st.pstdev(rets)
            R = max(5.0, min(10.0, 1.5 * sigma))
            D = max(5.0, min(10.0, 1.2 * sigma))

    # ===== 均线与趋势 =====
    ma5 = ma10 = ma20 = None
    trend = 'unknown'
    if enough:
        ma5, ma10, ma20 = ma(closes, 5), ma(closes, 10), ma(closes, 20)
        if len(closes) < 20:
            notes.append(f'MA20 仅用 {len(closes)} 点近似')
        if None not in (ma5, ma10, ma20):
            if ma5 < ma10 < ma20 and cur < ma20:
                trend = 'bear'
            elif ma5 > ma10 > ma20 and cur > ma20:
                trend = 'bull'
            else:
                trend = 'range'

    # ===== 底部 / 顶部与反弹回调 =====
    L = H = None
    low_date = high_date = None
    rebound = pullback = None
    rebound_formed = False
    if enough:
        L = min(closes); low_date = dates[closes.index(L)] if dates else None
        H = max(closes); high_date = dates[closes.index(H)] if dates else None
        rebound = (cur - L) / L * 100 if L else None
        pullback = (H - cur) / H * 100 if H else None
        # 低点若出现在最近1个交易日内 → 反弹尚未形成
        idx_low = closes.index(L)
        rebound_formed = idx_low < len(closes) - 1
        if not rebound_formed:
            notes.append('低点出现在最近1个交易日，反弹尚未形成')

    # ===== RSI：优先用 quote，缺失则自算 =====
    rsi = q.get('rsi6')
    rsi_hist = rsi_series(closes) if enough else []
    if rsi is None and rsi_hist:
        rsi = rsi_hist[-1]
        notes.append('RSI6 由20日收盘自算补齐')
    was_oversold = bool(rsi_hist and min(rsi_hist[-5:]) < 25) or (rsi is not None and rsi < 25)

    # ===== 当下刚冲高（近10日累涨>15% 且高点在最近5日内）=====
    surged = enough and is_fresh_surge(closes)

    # ---------------- 卖出侧（优先判定，保护利润） ----------------
    key = None
    reasons = []
    # ⚠️ 空头排列下不发"冲高止盈"：下跌趋势中不存在"保护刚到顶利润"的场景，
    #    该情形应交由买入侧（超卖试探）或观望处理。
    if enough and surged and trend != 'bear' and pullback is not None:
        if D is not None and pullback >= D and ma10 is not None and cur < ma10:
            key = 'strong_sell'
            reasons.append(f'曾连续冲高，自20日高${H:.2f}回调{pullback:.1f}%（≥阈值{D:.1f}%）且跌破MA10${ma10:.2f}')
        elif pullback >= 5.0:
            key = 'sell'
            reasons.append(f'曾连续冲高，自高点回调{pullback:.1f}%（≥铁律一 5%）')
    if key is None and rsi is not None and rsi > 85 and ma5 is not None and cur < ma5:
        key = 'sell'
        reasons.append(f'RSI6={rsi:.1f}超买且已跌破MA5${ma5:.2f}，动能转弱')

    # 高位预警（不减仓，仅提示，解决"超买≠该卖"的语义混淆）
    high_warn = (key is None and
                 ((rsi is not None and rsi > 85) or (d52h is not None and d52h > -2)))

    # ---------------- 买入侧 ----------------
    if key is None:
        deep = d52h is not None and d52h < -20
        # Strong Buy：四条必须全中
        cond = {
            'deep': deep,
            'oversold': was_oversold,
            'rebound': (R is not None and rebound is not None
                        and rebound_formed and rebound >= R),
            'structure': ma10 is not None and cur >= ma10,
        }
        veto = []
        if trend == 'bear' and drop_now > 6:
            veto.append('空头排列+当日跌幅>6%（暴跌中接飞刀）')
        if red_flags >= 2:
            veto.append(f'基本面{red_flags}项RedFlag')
        if not enough:
            veto.append('数据不足未做趋势确认')
        if seq_stale:
            veto.append('20日序列严重滞后，趋势不可信')

        if all(cond.values()) and not veto:
            key = 'strong_buy'
            reasons.append(
                f'距52W高{d52h:.1f}%（<-20%）+ 近5日曾超卖 + 自20日低${L:.2f}反弹'
                f'{rebound:.1f}%（≥阈值{R:.1f}%）+ 收盘${cur:.2f}≥MA10${ma10:.2f}结构修复')
        else:
            # 退而判 Buy
            hit = []
            if rsi is not None and rsi < 20:
                hit.append(f'RSI6={rsi:.1f}<20超卖')
            if deep and rsi is not None and rsi < 45:
                hit.append(f'距52W高{d52h:.1f}%且RSI6={rsi:.1f}<45')
            if drop_now > 6 and rsi is not None and rsi < 40:
                hit.append(f'当下跌{drop_now:.1f}%且RSI6={rsi:.1f}<40')
            if hit:
                key = 'buy'
                reasons.append(' / '.join(hit))
                miss = [k for k, v in cond.items() if not v]
                if miss:
                    zh = {'deep': '回撤未达-20%', 'oversold': '近5日未超卖',
                          'rebound': '反弹未确认', 'structure': '未站上MA10'}
                    reasons.append('未升级Strong Buy：' + '、'.join(zh[m] for m in miss))
                if veto:
                    reasons.append('否决项：' + '、'.join(veto))

    # ---------------- 机械定投兜底 ----------------
    if key is None:
        if red_flags >= 2:
            key = 'hold'
            reasons.append(f'基本面{red_flags}项RedFlag，不做机械定投')
        else:
            key = 'dca'
            reasons.append('无技术信号，按周期机械定投，保留参与度')

    # ---------------- 份额与降级 ----------------
    shares = TIERS[key]['shares']
    if key == 'buy':
        if trend == 'bear':
            shares = 0.5
            reasons.append('空头排列 → 份额砍半，逆势试探')
        if red_flags >= 2:
            shares = 0.3
            reasons.append('基本面恶化 → 份额压至0.3')
        if not enough:
            reasons.append('数据不足，最高只给 Buy')

    # ---------------- 空头排列连续定投熔断（跨日报持久化） ----------------
    stt = state.setdefault(sym, {'bear_dca_count': 0, 'last_date': None})
    if key == 'dca' and trend == 'bear':
        if stt.get('last_date') != today:      # 同一天两次运行只计一次
            stt['bear_dca_count'] = stt.get('bear_dca_count', 0) + 1
            stt['last_date'] = today
        if stt['bear_dca_count'] > BEAR_DCA_LIMIT:
            key, shares = 'hold', 0.0
            reasons.append(
                f'空头排列下已连续机械定投{stt["bear_dca_count"]}次（>{BEAR_DCA_LIMIT}），'
                f'暂停定投待趋势转好')
    elif trend != 'bear' or key != 'dca':
        if stt.get('bear_dca_count'):
            reasons.append(f'趋势/信号改善，重置连续定投计数（原{stt["bear_dca_count"]}次）')
        stt['bear_dca_count'] = 0
        stt['last_date'] = today

    return {
        'symbol': sym,
        'advice_key': key,
        'advice_label': TIERS[key]['label'],
        'shares': round(shares, 2),
        'color': TIERS[key]['color'],
        'trend': trend,
        'sigma': round(sigma, 2) if sigma is not None else None,
        'rebound_threshold': round(R, 2) if R is not None else None,
        'pullback_threshold': round(D, 2) if D is not None else None,
        'rebound_pct': round(rebound, 2) if rebound is not None else None,
        'pullback_pct': round(pullback, 2) if pullback is not None else None,
        'low_20d': L, 'low_date': low_date,
        'high_20d': H, 'high_date': high_date,
        'ma5': round(ma5, 2) if ma5 else None,
        'ma10': round(ma10, 2) if ma10 else None,
        'ma20': round(ma20, 2) if ma20 else None,
        'rsi6': round(rsi, 1) if rsi is not None else None,
        'was_oversold_5d': was_oversold,
        'surged_10d': surged,
        'high_warning': high_warn,
        'stop_loss_anchor': L,          # 止损锚点：跌破即判断失败（对应铁律三）
        'data_enough': enough,
        'reason': '；'.join(reasons),
        'notes': notes,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--quotes', required=True)
    ap.add_argument('--performance', required=True)
    ap.add_argument('--state', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    quotes = json.loads(Path(args.quotes).read_text(encoding='utf-8'))['stocks']
    perf = json.loads(Path(args.performance).read_text(encoding='utf-8'))['stocks']

    state_path = Path(args.state)
    state = (json.loads(state_path.read_text(encoding='utf-8'))
             if state_path.exists() else {})

    today = datetime.now().strftime('%Y-%m-%d')
    results = {}
    for sym, q in quotes.items():
        pts = perf.get(sym) or []
        closes = [p['close'] for p in pts if p.get('close')]
        dates = [p['date'] for p in pts if p.get('close')]
        results[sym] = evaluate(sym, q, closes, dates, state, today)

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    Path(args.out).write_text(
        json.dumps({'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'signals': results}, ensure_ascii=False, indent=2),
        encoding='utf-8')

    # 控制台摘要
    order = ['strong_buy', 'buy', 'dca', 'hold', 'sell', 'strong_sell']
    tz_map = {'bear': '空头', 'bull': '多头', 'range': '震荡', 'unknown': '未知'}

    def fmt(v, suffix='', nd=1):
        return f'{v:.{nd}f}{suffix}' if v is not None else '--'

    print(f"{'代码':6s} {'趋势':6s} {'RSI6':>6s} {'σ':>7s} {'阈值R':>7s} "
          f"{'反弹%':>7s} {'回调%':>7s} {'信号':15s} {'份额':>6s}")
    print('-' * 88)
    for k in order:
        for sym, r in results.items():
            if r['advice_key'] != k:
                continue
            print(f"{sym:6s} {tz_map[r['trend']]:6s} "
                  f"{fmt(r['rsi6']):>6s} "
                  f"{fmt(r['sigma'], '%', 2):>7s} "
                  f"{fmt(r['rebound_threshold'], '%'):>7s} "
                  f"{fmt(r['rebound_pct'], '%'):>7s} "
                  f"{fmt(r['pullback_pct'], '%'):>7s} "
                  f"{r['advice_label']:15s} {r['shares']:+.1f}")
    tot = sum(r['shares'] for r in results.values())
    print('-' * 88)
    print(f'净份额合计：{tot:+.1f} 份')


if __name__ == '__main__':
    main()
