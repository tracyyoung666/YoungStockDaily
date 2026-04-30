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

**⚠️ 重要：必须使用 fetch_quotes.py v4 统一抓取工具**

```bash
python3 /data/workspace/.agent/skills/stock-and-web3/scripts/fetch_quotes.py MU,AMD,INTC,...
```

**v4 自动根据北京时间选择数据策略**：
- 北京 07:00-15:00 工作日 → 获取**盘后价**
- 北京 15:00-21:30 → 获取**盘前价**
- 北京 21:30-04:00 → 获取**盘中实时价**（新增！）
- 北京 04:00-07:00 → 获取**盘后价**
- 周六/周日 → 获取**周五收盘+盘后价**

**v4 返回的每只股额外包含**：
- `rsi6` / `kdj_k` → 技术指标（自动抓取）
- `news` → 过滤后的新闻标题（已去除纯成交额播报等低质量内容）
- `latest_rating` → 最新机构评级（机构名/评级/目标价）
- `upcoming_events` → 关键事件日历（财报披露日/分红除权日）
- `abnormal_signals` → 异常信号（新增 RSI6>85 超买 / RSI6<15 超卖）
- `sector_analysis` → 板块关联分析（半导体/AI基建/Crypto/新能源车 各赛道平均涨跌）

**异常判定口径（v4 增强）**：
- 单日涨跌 > 4%
- 量比 > 2
- RSI6 > 85（超买）或 < 15（超卖）← 新增
- 创 52 周新高/新低
- 盘前/盘后/盘中涨跌 > 4%

**🚫 绝对禁止**：不要自己拼接 westock-data + 新浪 gb_ 接口，必须用 fetch_quotes.py。

### 步骤 2.5：生成股票报告 HTML（stock_body_html 内容规范）

**⚠️ 核心要求：stock_body_html 必须包含以下 4 大板块，缺一不可：**

```
1️⃣ 异常信号总览表
   - HTML table，列：代码 | 名称 | 昨收 | 昨日涨跌 | 盘前价 | 盘前涨跌 | 距52周高 | 信号
   - 每只股票一行，无遗漏

2️⃣ 组合层面总结 + 行动清单
   - <h3>⚡ 异常信号详解</h3>：只列有异常的股票，简述原因
   - <h3>💡 建议动作</h3>：P0/P1/P2 优先级 + 具体触发条件

3️⃣ 📝 逐股详解（最重要！不能省略！）
   - 对自选股清单中的【每一只】股票，生成独立段落，格式：
     <h3>N️⃣ 代码 · 名称 — 评分 X.X</h3>
     <ul>
       <li><strong>行情：</strong>昨收$XXX(±X.XX%) · 盘前/盘后/盘中 $XXX(±X.XX%)</li>
       <li><strong>技术：</strong>RSI6/KDJ/MA/量比/距52W高等技术面关键指标（RSI6>85 或 <15 需醒目标注⚠️）</li>
       <li><strong>新闻：</strong>最近1-2条相关新闻（已过滤低质量内容，无则写"—"）</li>
       <li><strong>评级：</strong>最新机构评级（机构名+评级+目标价，无则写"—"）← v4新增</li>
       <li><strong>事件：</strong>近期关键事件（财报日/除权日，无则写"—"）← v4新增</li>
       <li><strong>建议：</strong>具体操作建议+价位+触发条件（这是用户最看重的！）</li>
       <li><strong>大师视角：</strong>1-2位投资大师的简短点评（可选，有则更好）</li>
     </ul>
   - 9只全部要有，不能只做异常的几只

4️⃣ 板块关联分析 ← v4新增
   - <h3>🏷️ 板块关联分析</h3>
   - 按赛道（半导体/AI基建/Crypto/新能源车）聚合当日平均涨跌
   - 一句话总结板块格局（如"半导体板块+6.2%领涨，INTC 驱动"）

5️⃣ 一句话结论
   - <h3>💡 一句话结论</h3>：整体总结今日策略方向
```

**绝对禁止**：只生成一个概览表格就结束——那是"摘要"不是"报告"。逐股详解是用户查看报告的核心价值。

### 步骤 2.6：数据验证护栏 ← v4新增

**在推送前必须执行验证**，调用 `fetch_quotes.validate_report(json_path, png_path, num_stocks=9)`：
```python
from scripts.fetch_quotes import validate_report
errors = validate_report("daily/daily_YYYYMMDD_HHMM.json", "images/daily_YYYYMMDD_HHMM.png")
if errors:
    # 终止推送！通过 notify 报告错误
    ...
```

验证项：
1. JSON 文件存在且可解析
2. 必填字段完整（slug/date/generated_at/title/has_stock/has_web3/image/stock_body_html/web3_body_html/tickers）
3. has_stock / has_web3 为 True
4. 逐股详解 `<h4>` 数量 = 自选股数量（9）
5. stock_body_html 长度 >= 3000 字符
6. 图片文件存在且 >= 20KB

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

## 周报流程（每周六 20:00 自动触发）← v4新增

周报是对本周 5 个交易日日报的聚合复盘，推送给用户用于周末复盘。周六/周日不再推送日报。

**周报内容板块**：
1. 📊 本周涨跌排名（按本周累计涨跌排序，含收盘价 + 周涨跌%）
2. 🚨 本周异常事件回顾（摘取本周 10 份日报中的所有异常信号去重汇总）
3. 📰 本周重要新闻 TOP 5（从本周所有新闻中筛选最有影响力的 5 条）
4. 📅 下周关键事件预告（财报日/除权日/期权到期日）
5. 💡 下周操作策略建议（基于本周走势 + 技术面 + 事件面的综合判断）
6. 🪙 本周 Web3 摘要（BTC/ETH 周涨跌 + 恐贪指数变化趋势）

**数据来源**：读取 `data/daily.json` 索引中本周一~周五的 5 份日报 JSON，聚合分析。

**推送标题格式**：`📊 自选股周报 | YYYY-MM-DD ~ YYYY-MM-DD`

## 定时任务调度规则

| 时间 | 任务 | 说明 |
|---|---|---|
| **周一~周五 09:00** | 日报推送 | 盘后/休市数据 |
| **周一~周五 19:00** | 日报推送 | 盘前数据 |
| **周六 20:00** | **周报推送** | 本周聚合复盘 |
| 周六/周日 09:00 & 19:00 | **不推送** | 日报定时任务需跳过周末 |

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
