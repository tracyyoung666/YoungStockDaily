# 数据 Schema 参考

## 1. watchlist.json（自选股源）

位置：`/data/workspace/portfolio/watchlist.json`

```json
{
  "updated_at": "YYYY-MM-DD",
  "categories": {
    "default": {
      "description": "默认分类说明",
      "stocks": [
        {
          "symbol": "MU",
          "market": "US",
          "name": "Micron 美光",
          "added_at": "YYYY-MM-DD",
          "tags": ["半导体", "HBM"]
        }
      ]
    }
  }
}
```

- `categories` 是字典，key 是分类名，value 包含 description 和 stocks 数组
- `market` 枚举：`US`（美股） / `HK`（港股） / `CN`（A股）
- 增删股票即修改对应分类 `stocks` 数组，保持 updated_at 同步

## 2. reports.json（股票报告索引）

仓库路径：`data/reports.json`

```json
{
  "updated_at": "ISO 时间戳",
  "reports": [
    {
      "date": "2026-04-28",
      "title": "自选股实时行情分析 · 盘前",
      "category": "实时行情分析",
      "summary": "一句话摘要（用于首页卡片展示）",
      "tickers": ["MU", "AMD", "..."],
      "image": "images/2026-04-28.png"
    }
  ]
}
```

- 每条报告对应 `reports/<date>.html`
- `image` 是可选的预览图相对路径
- publish_site.py 会自动插入/覆盖同日条目并按 date 倒序排序

## 3. web3.json（Web3 日报索引）

仓库路径：`data/web3.json`

```json
{
  "updated_at": "ISO 时间戳",
  "count": 10,
  "digests": [
    {
      "date": "2026-04-28",
      "title": "Web3 日报 · 2026-04-28",
      "summary": "首段摘要",
      "generated_at": "原始 API 返回时间"
    }
  ]
}
```

每条对应 `web3/<date>.html`。由 `scripts/build_web3_pages.py` 自动重建。

## 4. overview_data.json（异常信号总览图输入）

传给 `scripts/render_overview.py --input <file>`：

```json
{
  "date": "2026-04-28",
  "phase": "盘前",
  "rows": [
    {
      "symbol": "MU",
      "prev_close": 524.56,
      "prev_change_pct": 5.60,
      "premarket_price": 503.00,
      "premarket_change_pct": -4.11,
      "dist_52w_high_pct": 0.0,
      "signal_label": "🔥 超买+新高",
      "signal_level": "fire"
    }
  ],
  "portfolio_summary": [
    "主战场：MU / INTC 兑现盈利",
    "次战场：AMD 回踩建仓"
  ],
  "action_list": [
    {"action": "减仓", "target": "MU", "detail": "分批 $470-485 锁利"},
    {"action": "观望", "target": "AMD", "detail": "等待 $305-320 回踩"}
  ]
}
```

- `signal_level` 枚举：`fire`（🔥 极端） / `warn`（⚠️ 警告） / `ok`（✅ 正常）
- `rows` 顺序决定表格行顺序
- `portfolio_summary` 和 `action_list` 会渲染在图片下半部分

## 5. web3 archive digest JSON

位置：`/data/workspace/web3-archive/digests/YYYY-MM-DD.json`

```json
{
  "date": "2026-04-28",
  "digest_md": "# 📅 Web3 日报 | 2026-04-28\n...",
  "digest_wechat": "📅 Web3 日报 | 2026-04-28\n...",
  "generated_at": "2026-04-28T06:06:10",
  "source": "j4y-production.up.railway.app",
  "archived_at": "2026-04-28T19:02:00+08:00"
}
```

由 `/data/workspace/web3-archive/archive.py` 读 stdin JSON 写入。
