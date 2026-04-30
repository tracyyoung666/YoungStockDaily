# 美股实时行情 + 盘前价获取指南（v2，2026-04-29 大修）

> ⚠️ **历史血泪教训**：上游多次把"新浪 gb_ 接口的 change_pct 当成盘前涨跌"，把"接口 [1] 字段当成盘前价"，结果所有日期都错位。必须严格按本文口径。

## 📅 时区对齐（核心认知）

| 术语 | 含义（用户是北京时间视角）| 对应数据源字段 |
|---|---|---|
| **昨收** | 北京昨晚-今晨刚刚结束的那个美股常规交易日的收盘价 | `westock-data quote` 的 `price`（= `close`），`time` 字段显示美东交易日 |
| **前日收盘** | 再往前一个交易日的收盘 | `westock-data quote` 的 `prev_close`（= 美东 T-1 日收盘） |
| **盘前价** | 未开盘的这个交易日，盘前时段的实时成交 | 新浪 `hq_str_gb_xxx` 的**最后一个数字字段**（倒数第一）|

**举例**：
- 现在北京 2026-04-29 19:30（周三晚）= 美东 4/29 07:30（周三早，盘前中段）
- 用户说的"MU 昨收 $504.29" = 美东 4/28（周二）收盘 = 北京 4/29 凌晨 04:00 刚收盘那个盘
- westock-data quote 返回 `price=504.29, time=2026-04-28` ✅ 完全对得上
- 新浪 gb_ 接口 `prev_close=524.56` 其实是**美东 4/27 周一**的收盘（相对 T=4/28 是 T-1）

## 🕒 交易时段判定（夏令时，3 月中 → 11 月初）

```
北京 16:00 - 21:30  = 美东 04:00-09:30  → 盘前 Pre-Market  ✅可拉盘前价
北京 21:30 - 次 04:00 = 美东 09:30-16:00 → 常规盘中 Regular  ❌直接拉实时
北京 04:00 - 08:00  = 美东 16:00-20:00  → 盘后 After-Hours  ✅可拉盘后价
北京 08:00 - 16:00  = 美东 20:00-04:00  → 完全休市，只有昨收
```

冬令时（11月初-3月中）整体右移 1 小时。

## 🛠 数据源 1：westock-data（权威昨收）

```bash
# 美股代码必须带 us 前缀 + 后缀（.OQ=纳斯达克 / .N=纽交所）
node /data/workspace/.agent/skills/westock-data/scripts/index.js quote "usMU.OQ,usAMD.OQ"
```

返回表格里取：
- `price` → 昨收（= 美东 T日收盘 = 北京昨夜刚收的盘）
- `prev_close` → 前日收盘（= 美东 T-1 日收盘）
- `change_percent` → T 日当日涨跌 %（T vs T-1）
- `high_52week` / `low_52week` → 52 周极值
- `volume_ratio` → 量比
- `time` → 美东交易日（YYYY-MM-DD）

## 🛠 数据源 2：新浪 gb_ 接口（盘前/盘后价）

```bash
curl -s "https://hq.sinajs.cn/list=gb_mu,gb_amd,gb_intc" \
     -H "Referer: https://finance.sina.com.cn"
```

**真实字段顺序**（36 字段，编码 GBK）：
```
[0]  名称
[1]  当前报价（盘前/盘中/盘后实时价）
[2]  累计涨跌%  （⚠️注意：这是"[1] vs [26]"，不是"盘前 vs 昨收"！不能直接用！）
[3]  时间戳（北京时间）
[4]  涨跌额
[5]  今开
[6]  最高
[7]  最低
[8]  52w 高
[9]  52w 低
[10] 成交量
[11] 平均量
[12] 总市值
...
[25] 美东时间戳（例 "Apr 28 03:59PM EDT"）
[26] 前一个已结束交易日的前收（= 美东 T-1 日收盘）
[27] 前一笔成交量
...
[-4] 盘前倒数第二笔价
[-3] 盘前累计成交额
[-2] 盘前最高价
[-1] 盘前最新成交价  ⭐ 真正的盘前价在这里
```

**必须做的二次校验**：
```python
if abs(premarket_price - yesterday_close) < 0.01:
    # 盘前价与昨收完全相同 → 说明盘前尚无有效成交，返回 None
    premarket_price = None
```

## ✅ 正确的调用姿势（直接用封装好的工具）

```python
from scripts.fetch_quotes import fetch_all

data = fetch_all(["MU","AMD","INTC","NBIS","CRWV","CRCL","MSTR","TSLA","XPEV"])
# data["meta"]["session"]           → 'pre_market' / 'regular' / ...
# data["stocks"]["MU"]["close_price"]  → 504.29 （昨收，权威）
# data["stocks"]["MU"]["premarket_price"]  → 盘前价 or None
# data["stocks"]["MU"]["premarket_pct_vs_close"]  → 盘前涨跌% vs 昨收
# data["stocks"]["MU"]["premarket_note"]  → 'ok' / 'no_premarket_activity'
```

或命令行：
```bash
python3 /data/workspace/.agent/skills/stock-and-web3/scripts/fetch_quotes.py MU,AMD,INTC
```

## 🚫 绝对禁止的错误做法

1. ❌ 把 `hq_str_gb_` 的 `[1] 当前报价` 当成"盘前价" —— 它可能就是昨收快照
2. ❌ 把 `hq_str_gb_` 的 `[2] 涨跌%` 当成"盘前涨跌" —— 它的基准是 `[26]`，不是昨收
3. ❌ 没拉到盘前价时用昨收兜底冒充盘前 —— 必须明写 `premarket_price=None` + 标注 `no_premarket_activity`
4. ❌ 休市时段（北京 08:00-16:00）还去问盘前价 —— `fetch_all` 会自动返回 `can_fetch_premarket=false`

## 📌 52 周高点距离

```python
dist = (close_price - high_52w) / high_52w * 100  # 负值 = 距高点的跌幅
# dist > -0.5% 视为"接近创新高"
```
