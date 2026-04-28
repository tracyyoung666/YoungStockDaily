# 美股盘前价获取指南

## 时段判定（北京时间）

| 时段 | BJ 时间范围 | 可否取盘前价 |
|---|---|---|
| 盘前 Pre-Market | 16:00 - 21:30 | ✅ 是 |
| 开盘 Regular | 21:30 - 次日 04:00 | ❌ 直接用实时价 |
| 盘后 After-Hours | 次日 04:00 - 08:00 | ✅ 用盘后价，字段名不同 |
| 休市 | 08:00 - 16:00 | ❌ 只用前一交易日收盘价 |

夏令时与冬令时会有 1 小时偏移（3 月中至 11 月初为夏令时，开盘 21:30；其他时段开盘 22:30）。实际调用时以当前时间与开盘前 1 分钟对齐判断即可。

## 数据源：新浪财经 gb_ 接口

### 请求
```bash
# symbol 需要小写
curl -s "https://hq.sinajs.cn/?list=gb_${symbol_lower}" \
  -H "Referer: https://finance.sina.com.cn"
```

### 响应格式
```
var hq_str_gb_amd="AMD,315.24,-5.76,-19.39,...";
```

字段顺序（从左到右）：
1. 名称
2. 当前价
3. 涨跌百分比
4. 涨跌额
5. 昨收
6. 今开
7. 今日最高
8. 今日最低
9. 52 周最高
10. 52 周最低
11. 成交量（股）
12. 时间戳
13. 盘前价
14. 盘前涨跌百分比
15. 盘前涨跌额
16. 盘前时间戳
17. 盘后价
18. 盘后涨跌百分比
19. 盘后涨跌额

### Python 解析示例
```python
import re, urllib.request

def fetch_premarket(symbol):
    url = f"https://hq.sinajs.cn/?list=gb_{symbol.lower()}"
    req = urllib.request.Request(url, headers={'Referer': 'https://finance.sina.com.cn'})
    text = urllib.request.urlopen(req, timeout=5).read().decode('gbk', errors='ignore')
    m = re.search(r'"([^"]+)"', text)
    if not m:
        return None
    parts = m.group(1).split(',')
    if len(parts) < 16:
        return None
    try:
        return {
            'symbol': symbol.upper(),
            'last': float(parts[1]) if parts[1] else None,
            'pct': float(parts[2]) if parts[2] else None,
            'prev_close': float(parts[4]) if parts[4] else None,
            'premarket_price': float(parts[12]) if parts[12] else None,
            'premarket_pct': float(parts[13]) if parts[13] else None,
        }
    except ValueError:
        return None
```

## 批量获取（自选股清单）

```bash
# 一次查多只：gb_amd,gb_mu,gb_intc
curl -s "https://hq.sinajs.cn/?list=gb_amd,gb_mu,gb_intc" \
  -H "Referer: https://finance.sina.com.cn"
```

响应是多条 `var hq_str_gb_xxx="..."`，按顺序解析即可。建议把清单拆成每 30 只一组请求，避免超长 URL。

## 异常处理

- 返回空字符串：该股票可能暂停交易或接口异常 → 用昨收兜底
- 盘前价字段为空：当前不在盘前时段 → 跳过盘前价显示
- curl 超时：设置 5s 超时，失败则跳过盘前价，不阻塞主流程

## 距 52 周高点计算

```python
dist = (current_price - high_52w) / high_52w * 100  # 负值表示距高点的跌幅
```

创新高判定：`abs(dist) < 0.1%`（阈值可调）。
