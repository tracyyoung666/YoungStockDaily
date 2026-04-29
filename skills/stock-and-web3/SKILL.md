---
name: stock-and-web3
description: 股票自选股管理与 Web3 日报一体化持久化技能。一次性完成【自选股维护 + 自选股实时行情分析（含盘前价、异常信号总览图、逐股详解）+ Web3 日报拉取 + 内容归档到 HTML 站点 + 推送 Git 仓库 + 返回结果】的完整闭环。适用场景（任一触发即调用）：(1) 用户要求"出一份自选股分析"、"跑一下今天的盘前分析"、"推送今天的股票 + Web3 日报"、"生成今日投研报告"；(2) 用户要求"把 X 加入/移除自选股"、"查看自选股清单"；(3) 用户要求"获取今日 Web3 日报"并希望沉淀到站点；(4) 用户设置了定时任务要求每日盘前/盘后推送图片 + 简报。前置依赖 Skills：westock-data（行情/新闻/财务）、web3-daily（加密日报）、investment-masters（大师视角，可选）、stock-analyzer（可选兜底）。Git 仓库地址和 Token 支持外部传入（默认仓库 tracyyoung666/YoungStockDaily，默认 Token 从 ~/.config/knot/github_token 读取）。
---

# stock_and_web3 · 股票与 Web3 一体化投研技能

## 能力总览

本技能提供"一条命令跑完整条流水线"的能力：

```
自选股清单 ─┐
            ├─→ 行情/新闻/异常信号 ─→ 异常信号总览图（PNG）─┐
westock-data┘                                                ├─→ 合并成 HTML 报告 ─→ git commit + push
web3-daily ─→ Web3 日报（MD+微信版）──────────────────────┘                      │
                                                                                  ↓
                                                                        notify 推送（先图后文）
```

## 核心数据与仓库路径

| 用途 | 本地路径 | 仓库路径 |
|---|---|---|
| 自选股清单 | `/data/workspace/portfolio/watchlist.json` | `data/portfolio.json` |
| 股票报告索引 | - | `data/reports.json` |
| Web3 归档数据 | `/data/workspace/web3-archive/digests/YYYY-MM-DD.json` | - |
| Web3 列表索引 | - | `data/web3.json` |
| 股票报告详情页 | - | `reports/YYYY-MM-DD.html` |
| Web3 详情页 | - | `web3/YYYY-MM-DD.html` |
| 异常信号总览图 | - | `images/YYYY-MM-DD.png` |
| 访问入口 | - | `https://youngstockdaily.pages.dev/` |

默认 Git 仓库：`https://github.com/tracyyoung666/YoungStockDaily.git`（可通过 `--repo` 覆盖）。
默认 Token：从 `~/.config/knot/github_token` 读取（可通过环境变量 `GITHUB_TOKEN` 覆盖）。

## 工作流（标准六步）

**重要：任一步出错必须通过 notify 工具告知用户。下列步骤可按需跳过，但顺序不能颠倒。**

### 步骤 1：维护自选股清单（如有增删请求）

读取 `/data/workspace/portfolio/watchlist.json`，按用户意图增删后原位写回。结构见 `references/data-schemas.md`。

### 步骤 2：获取每只自选股的实时行情 + 异常信号

**⚠️ 重要：数据口径与时区（v2 修正，2026-04-29）**

直接调用封装好的统一抓取工具（已固化正确时区/字段映射，防止踩坑）：
```bash
python3 /data/workspace/.agent/skills/stock-and-web3/scripts/fetch_quotes.py MU,AMD,INTC,...
```

返回的每只股包含：
- `close_price` → **昨收**（= 美东 T 日收盘 = 北京昨夜刚结束的那个盘），来自 westock-data
- `prev_close` → 前日收盘（= 美东 T-1 日收盘，仅作参考）
- `pct_1d` → T 日当日涨跌%（已跌算完）
- `volume_ratio`、`high_52w`、`dist_from_52w_high_pct` 等
- `premarket_price` → **盘前价**（只在盘前时段才有值；无有效成交时为 `None`）
- `premarket_pct_vs_close` → 真实盘前涨跌% = (盘前价 - 昨收) / 昨收
- `premarket_note` → `'ok'` / `'no_premarket_activity'` / `'fields_insufficient'`
- `abnormal_signals` → 自动打标的异常列表

**🚫 绝对禁止的错误**：
1. 不要把新浪 `gb_` 接口的 `change_pct` 当作盘前涨跌（基准是 T-1，不是昨收）
2. 没拉到盘前价时**不要用昨收兜底冒充盘前**，必须写 `暂无有效盘前`
3. 忽略 fetch_quotes 返回的 `meta.session`，在休市时段（08:00-16:00）还强拉盘前

详见 `references/premarket.md`。

**异常判定口径**：单日涨跌 > 4% | 量比 > 2 | RSI6 > 85 或 < 15 | 创 52 周新高/新低 | 盘前涨跌 > 4%。

另外补充每只股的新闻（`westock-data news --type 3 --limit 2`）。

### 步骤 3：生成异常信号总览图（PNG）

调用 `scripts/render_overview.py`，生成适合手机竖屏的亮色系表格图：
```bash
python3 scripts/render_overview.py \
  --input /tmp/overview_data.json \
  --output <仓库>/images/YYYY-MM-DD.png
```

输入 JSON schema 见 `references/data-schemas.md#overview_data`。图默认 1188×约 2100，亮色 `#f7f9fc` 背景，无底部冗余留白。

### 步骤 4：拉取 Web3 日报

调用 web3-daily 公开 API：
```bash
curl -s -X POST "https://j4y-production.up.railway.app/api/v1/digest/public" \
  -H "Content-Type: application/json" -d '{"language":"zh"}' > /tmp/web3_digest.json
```

把 `digest` 字段转换为【微信友好纯文本版】并写入 `/tmp/web3_wechat.txt`。规则详见 `references/wechat-format.md`。

然后运行 web3 归档脚本（位于工作区）：
```bash
python3 -c "import json,re,datetime
raw=json.load(open('/tmp/web3_digest.json'))
md=raw['digest']
wc=open('/tmp/web3_wechat.txt',encoding='utf-8').read()
m=re.search(r'(\d{4}-\d{2}-\d{2})',md[:200])
date=m.group(1) if m else datetime.date.today().isoformat()
import sys,json
sys.stdout.write(json.dumps({'date':date,'digest_md':md,'digest_wechat':wc,
  'generated_at':raw.get('generated_at',''),'source':'j4y-production.up.railway.app'},ensure_ascii=False))" \
  | python3 /data/workspace/web3-archive/archive.py
```

### 步骤 5：构建 HTML 站点并 git push

调用 `scripts/publish_site.py`，它会一次性完成：
1. 重新生成 Web3 日报详情页（扫描 `/data/workspace/web3-archive/digests/*.json`）
2. 更新 `data/portfolio.json`（从 watchlist.json 同步）
3. 将本次股票报告详情页写入 `reports/YYYY-MM-DD.html`
4. 更新 `data/reports.json` 索引
5. 复制异常信号总览图到 `images/YYYY-MM-DD.png`
6. `git add / commit / push`

```bash
python3 scripts/publish_site.py \
  --repo-url https://github.com/tracyyoung666/YoungStockDaily.git \
  --repo-dir /data/workspace/YoungStockDaily \
  --token-file ~/.config/knot/github_token \
  --date YYYY-MM-DD \
  --stock-report /tmp/stock_report.html \
  --stock-summary "一句话摘要" \
  --tickers "MU,AMD,INTC,..." \
  --overview-png /tmp/overview.png \
  --category "实时行情分析"
```

所有参数都可以通过环境变量覆盖（`GITHUB_TOKEN`、`REPO_URL`、`REPO_DIR`）。详见脚本 `--help`。

### 步骤 6：通过 notify 推送（两条，先图后文）

**第一条（图片）**：
- title: `📈 自选股行情分析 | YYYY-MM-DD`
- message: 仅 Markdown 图片语法，指向 raw.githubusercontent URL
  ```
  ![异常信号总览](https://raw.githubusercontent.com/tracyyoung666/YoungStockDaily/main/images/YYYY-MM-DD.png)
  ```

**第二条（文字简报，仅精简摘要）**：
- title: `📝 今日投研简报 | YYYY-MM-DD`
- message 格式（严格按下方模版，不加前言总结，**首行仅保留站点根地址，不贴子页面链接**）：
  ```
  🔗 https://youngstockdaily.pages.dev/

  ━━━ 📈 自选股行情 ━━━
  ・异常信号：<列 1-3 条关键异常，如 "MU 创新高 RSI 超买">
  ・建议动作：<列 1-2 条，如 "MU 减仓 1/3 / AMD 观望">

  ━━━ 🪙 Web3 日报 ━━━
  ・BTC / ETH：<价格和涨跌>
  ・恐贪指数：<数值 + 文字>
  ・一句话：<一句话总结>
  ```

## 参数约定（外部可覆盖）

| 参数 | 默认值 | 环境变量 |
|---|---|---|
| 仓库地址 | `https://github.com/tracyyoung666/YoungStockDaily.git` | `REPO_URL` |
| 本地克隆目录 | `/data/workspace/YoungStockDaily` | `REPO_DIR` |
| GitHub PAT | `~/.config/knot/github_token` | `GITHUB_TOKEN` |
| 访问入口 | `https://youngstockdaily.pages.dev/` | - |

## 常见场景速查

- **"帮我跑一下今天的分析"** → 跳过步骤 1，执行 2-6
- **"把 NVDA 加入自选，然后推一版"** → 执行 1-6
- **"只推 Web3 日报"** → 只执行 4-6（步骤 5 不生成股票报告）
- **"看一下我的自选股"** → 只执行步骤 1 的读取部分，返回 JSON

## 参考文件

- `references/data-schemas.md` - watchlist.json / reports.json / web3.json / overview_data JSON 的完整 schema
- `references/wechat-format.md` - Markdown → 微信纯文本转换规则
- `references/premarket.md` - 盘前价获取和时段判定
- `scripts/render_overview.py` - 异常信号总览图渲染（matplotlib）
- `scripts/publish_site.py` - 站点构建与 git push 一体化脚本
- `scripts/build_web3_pages.py` - 扫描 web3-archive 生成 HTML 详情页和列表索引

## 异常与回退

- git push 401：检查 token 是否过期
- 盘前接口超时：跳过盘前价，只用昨收
- matplotlib 字体找不到：用 `DejaVu Sans` 兜底，emoji 用文字符号代替
- Web3 API 超时：用最近一次 `/data/workspace/web3-archive/digests/` 最新文件

任一步失败，用 notify 发 title `❌ 投研推送失败 | YYYY-MM-DD`，message 说明失败步骤和原因。
