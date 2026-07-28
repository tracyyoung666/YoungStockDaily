---
name: stock-and-web3
description: 股票自选股管理与 Web3 日报一体化持久化技能。一次性完成【自选股维护 + 自选股实时行情分析（含盘前/盘后/盘中价、异常信号总览图、逐股详解）+ Web3 日报拉取 + 内容归档到站点 + 推送 Git 仓库 + 返回结果】的完整闭环。适用场景（任一触发即调用）：(1) 用户要求"出一份自选股分析"、"跑一下今天的盘前分析"、"推送今天的股票 + Web3 日报"、"生成今日投研报告"；(2) 用户要求"把 X 加入/移除自选股"、"查看自选股清单"；(3) 用户要求"获取今日 Web3 日报"并希望沉淀到站点；(4) 用户设置了定时任务要求每日盘前/盘后推送图片 + 简报。前置依赖 Skills：westock-data（行情/新闻/财务）、web3-daily（加密日报）、investment-masters（大师视角，可选）、stock-analyzer（可选兜底）。Git 仓库地址和 Token 支持外部传入（默认仓库 tracyyoung666/YoungStockDaily，默认 Token 从 ~/.config/knot/github_token 读取）。
---

# stock_and_web3 · 股票与 Web3 一体化投研技能

## 能力总览

本技能提供"一条命令跑完整条流水线"的能力：

```
自选股清单 ─┐
            ├─→ 行情/新闻/异常信号 ─→ 异常信号总览图（PNG）─┐
westock-data┘                                                ├─→ 合并写入 daily JSON ─→ git commit + push
web3-daily ─→ Web3 日报（MD+微信版）──────────────────────┘                          │
                                                                                      ↓
                                                                            notify 推送（先图后文）
```

## 核心数据与仓库路径

| 用途 | 本地路径 | 仓库路径 |
|---|---|---|
| 自选股清单 | `/data/workspace/portfolio/watchlist.json` | `data/portfolio.json` |
| 日报数据（JSON） | - | `daily/daily_YYYYMMDD_HHMM.json` |
| 日报索引 | - | `data/daily.json`（由 `rebuild_daily_index.py` 自动生成） |
| 异常信号总览图 | - | `images/daily_YYYYMMDD_HHMM.png` |
| 7日K线数据 | - | `data/sparkline.json` |
| 财报分析页 | - | `earnings/SYMBOL-YYYYQN.html` |
| 财报索引 | - | `data/earnings.json` |
| Web3 归档数据 | `/data/workspace/web3-archive/digests/YYYY-MM-DD.json` | - |
| 访问入口 | - | `https://youngstockdaily.pages.dev/` |

默认 Git 仓库：`https://github.com/tracyyoung666/YoungStockDaily.git`（可通过 `--repo` 覆盖）。
默认 Token：从 `~/.config/knot/github_token` 读取（可通过环境变量 `GITHUB_TOKEN` 覆盖）。

## 自选股清单（当前 11 只，顺序固定）

MU / AMD / INTC / GOOG / NVDA / NBIS / CRWV / CRCL / MSTR / TSLA / XPEV

## 工作流（标准七步，含前置步骤 0）

**重要：任一步出错必须通过 notify 工具告知用户。下列步骤可按需跳过，但顺序不能颠倒。**

### 步骤 0：前置 Skill 升级检查（⭐ 最前置，每次流程开始前必做）

**目的**：保证依赖的数据底座 `westock-data` / `westock-tool` 不过期。若距离上次升级超过 **14 天（2 周）**，自动触发升级并推送通知。

**维护的两个 skill（相对较新，需保持更新）：**
| skill | skill_id | 升级详情页 |
|---|---|---|
| `westock-data` | `2984` | https://knot.woa.com/skills/detail/2984 |
| `westock-tool` | `5600` | https://knot.woa.com/skills/detail/5600 |

**执行逻辑**：

```bash
# 0.1 读取上次升级时间台账（首次运行若文件不存在，视为"从未升级"，直接触发升级）
LEDGER=/data/workspace/.agent/skills/stock-and-web3/.skill_upgrade.json
NOW_TS=$(date +%s)
THRESHOLD=$((14*24*3600))   # 14 天

# 对 westock-data(2984) 和 westock-tool(5600) 分别判断：
#   last_upgrade = 台账中该 skill 的 last_upgrade（ISO 时间）
#   若 (NOW - last_upgrade) > 14 天 或 台账无记录 → 标记为需升级
```

**0.2 若需升级**，对每个待升级 skill 依次执行（通过 mcporter-internal 调用 knot-skill-finder）：
```bash
# 获取下载链接（skill_id：westock-data=2984，westock-tool=5600）
mcporter-internal call knot.get_skill_download_url --args '{"skill_id": "2984"}'
# 用返回的 url 下载并覆盖安装到 /data/workspace/.agent/skills/
wget -O /tmp/westock-data.zip "<download_url>"
unzip -o /tmp/westock-data.zip -d /data/workspace/.agent/skills/
# 验证：检查 .agent/skills/westock-data/SKILL.md 存在且 package.json version 已更新
```

**0.3 升级成功后更新台账** `.skill_upgrade.json`：
```json
{
  "westock-data": {"skill_id": "2984", "last_upgrade": "2026-06-10T17:40:00+08:00", "version": "1.0.x"},
  "westock-tool": {"skill_id": "5600", "last_upgrade": "2026-06-10T17:40:00+08:00", "version": "1.0.x"}
}
```

**0.4 若本次触发了升级，必须额外推送一条通知**（在所有日报推送之前或之后均可，但必须发）：
- title：`🔧 依赖 Skill 已自动升级 | YYYY-MM-DD`
- message（纯文本，发送到当前会话 ChatID `T21660007A`）：
  ```
  检测到投研依赖 skill 距上次升级已超过 2 周，已自动升级：
  ・westock-data：vA → vB（https://knot.woa.com/skills/detail/2984）
  ・westock-tool：vC → vD（https://knot.woa.com/skills/detail/5600）
  本次日报/周报将使用升级后的最新数据能力。
  ```
- 若未触发升级（未到 2 周），则**不发**此通知，直接进入步骤 1。
- 若升级失败：用 notify 发 title `⚠️ Skill 自动升级失败 | YYYY-MM-DD`，说明失败的 skill 和原因，但**不阻断**后续日报流程（用现有版本继续跑）。

### 步骤 1：维护自选股清单（如有增删请求）

读取 `/data/workspace/portfolio/watchlist.json`，按用户意图增删后原位写回。结构见 `references/data-schemas.md`。

### 步骤 2：获取每只自选股的实时行情 + 异常信号

**⚠️ 重要：必须使用 fetch_quotes.py v4 统一抓取工具**

```bash
python3 /data/workspace/.agent/skills/stock-and-web3/scripts/fetch_quotes.py MU,AMD,INTC,GOOG,NVDA,NBIS,CRWV,CRCL,MSTR,TSLA,XPEV
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
- `sector_analysis` → 板块关联分析（半导体/科技巨头/AI基建/Crypto/新能源车 各赛道平均涨跌）

**异常判定口径（v4 增强）**：
- 单日涨跌 > 4%
- 量比 > 2
- RSI6 > 85（超买）或 < 15（超卖）
- 创 52 周新高/新低
- 盘前/盘后/盘中涨跌 > 4%

**🚫 绝对禁止**：不要自己拼接 westock-data + 新浪 gb_ 接口，必须用 fetch_quotes.py。

### 步骤 2.5：生成股票报告 HTML（stock_body_html 内容规范）

**⚠️ 核心要求：stock_body_html 必须包含以下板块，缺一不可。**

**🚨 HTML 格式强制规范（每次都必须严格遵守，不能自行发挥）：**
- 涨跌颜色：**红涨绿跌**（涨用 `color:#dc2626`，跌用 `color:#16a34a`）
- 总览表格必须用 `class="stock-table"`，**严禁** `border="1"` 或 inline table 样式
- 异常信号详解和建议动作的 `<h3>` 标签不需要额外 class，前端 CSS 会自动通过 `:nth-of-type` 选择器高亮
- 逐股详解用 `<h4>` 标签（不是 `<h3>`）
- 整个 stock_body_html 必须包裹在 `<div class="stock-report">` 中

**1️⃣ 异常信号总览表（HTML 模板，直接复制修改数据即可）：**

```html
<div class="stock-report">

<h3>📊 异常信号总览表</h3>
<table class="stock-table">
<thead><tr>
  <th>代码</th><th>名称</th><th>收盘价</th><th>今日涨跌</th>
  <th>盘前/盘后价</th><th>盘前/盘后%</th><th>距52W高</th><th>信号</th>
</tr></thead>
<tbody>
<tr>
  <td><strong>MU</strong></td><td>美光科技</td><td>$518.46</td>
  <td style="color:#dc2626">+2.81%</td>
  <td>$523.16</td><td style="color:#dc2626">+0.91%</td>
  <td>-2.4%</td><td>正常</td>
</tr>
<!-- 每只股票一行，11只全部列出，涨用#dc2626红，跌用#16a34a绿 -->
</tbody>
</table>

<h3>⚡ 异常信号详解</h3>
<!-- 只列有异常的股票 -->
<ul>
  <li><strong>INTC：</strong>日涨+12.10% + 创52W新高 + RSI6=93.6超买 ...</li>
</ul>

<h3>💡 建议动作</h3>
<ul>
  <li><strong>P0 INTC：</strong>RSI超买+暴涨后建议...</li>
</ul>

<h3>📝 逐股详解</h3>
<!-- 每只用 <h4> 不是 <h3> -->
<h4>1️⃣ MU · 美光科技 — 评分 7.5</h4>
<ul>
  <li><strong>行情：</strong>...</li>
  <li><strong>技术：</strong>...</li>
  <li><strong>新闻：</strong>...</li>
  <li><strong>评级：</strong>...</li>
  <li><strong>事件：</strong>...</li>
  <li><strong>🎯 定投信号：</strong><span style="color:#dc2626">🟢 定投买（抄底）</span> — RSI6=13.2超卖 + 距52W高-24% + 单日-6.2%，回调中，建议分批定投买入</li>
  <li><strong>建议：</strong>...</li>
</ul>
<!-- 重复 15 只。🎯 定投信号 = 由"定投买卖点判定规则"（见步骤 2.55）产出，三档取值：
     🟢 定投买（抄底） / 🔴 定投卖（破顶） / ⚪ 观望持有；文案必须写明触发的量化依据 -->

<h3>🎯 定投买卖点建议（全量 15 只）</h3>
<!-- 每次必出，覆盖全部自选股；信号规则见步骤 2.55 -->
<table class="stock-table">
<thead><tr>
  <th>代码</th><th>名称</th><th>收盘价</th><th>RSI6</th><th>距52W高</th><th>定投信号</th><th>依据 / 操作建议</th>
</tr></thead>
<tbody>
<tr>
  <td><strong>MU</strong></td><td>美光科技</td><td>$518.46</td><td>13.2</td>
  <td>-24.0%</td>
  <td><span style="color:#dc2626">🟢 定投买</span></td>
  <td>RSI6超卖+深度回调，分批抄底</td>
</tr>
<!-- 15 只全部列出。定投信号三档：
     🟢 定投买（color:#dc2626） / 🔴 定投卖（color:#16a34a） / ⚪ 观望（color:#6b7280） -->
</tbody>
</table>

<h3>🏷️ 板块关联分析</h3>
<ul>
  <li><strong>半导体：</strong>+6.40%（MU +2.81%, AMD +4.30%, INTC +12.10%, NVDA -1.84%）</li>
  <!-- 其他板块 -->
</ul>

<h3>🔥 市场近期热点（全市场2日涨幅Top）</h3>
<table class="stock-table">
<thead><tr>
  <th>排名</th><th>代码</th><th>名称</th><th>收盘价</th><th>2日涨幅</th><th>热点原因</th>
</tr></thead>
<tbody>
<tr>
  <td>1</td><td><strong>DDOG</strong></td><td>Datadog</td><td>$178.52</td>
  <td style="color:#dc2626">+39.28%</td><td>Q1财报大幅超预期+AI可观测性需求爆发</td>
</tr>
<!-- 最多10只，按涨幅排序；数据来自 fetch_market_hotspots.py 输出的 hotspots.json -->
<!-- 热点原因：结合 westock-data news 逐只查询新闻标题分析上涨原因 -->
</tbody>
</table>

<h3>💡 一句话结论</h3>
<p>...</p>

</div>
```

**🚫 严禁：**
- 严禁用 `border="1"` / `cellpadding` / `cellspacing` 等 inline table 样式
- 严禁用 `#e03e3e` 旧红色（必须用 `#dc2626`）
- 严禁涨用绿跌用红（必须**红涨绿跌**：涨 `#dc2626`，跌 `#16a34a`）
- 严禁逐股详解用 `<h3>` 标签（必须用 `<h4>`）
- 严禁省略外层 `<div class="stock-report">` 包裹

**绝对禁止**：只生成一个概览表格就结束——那是"摘要"不是"报告"。逐股详解是用户查看报告的核心价值。

### 步骤 2.55：定投买卖点判定（🎯 每只股票必做）

**目的**：在纯行情/新闻描述之外，为每只自选股给出一个**确定性的定投操作信号**，回答用户核心诉求——"现在是该定投买（下跌抄底）、定投卖（破顶卖出），还是观望持有？"。信号必须由下列量化规则机械推导，**不得凭感觉主观打分**，保证每天口径一致、可复现。

**输入字段**（全部来自步骤 2 的 `fetch_quotes.py` 输出，无需新数据源）：
- `rsi6`（6日RSI，超买超卖）
- `dist_from_52w_high_pct`（距52周高点百分比，负值=低于高点）
- `low_52w` / `high_52w` / `close_price` → 计算 `dist_from_52w_low_pct = (close - low_52w)/low_52w*100`
- `pct_1d`（当日涨跌）、`extended_pct`（盘前/盘后涨跌）
- `kdj_k`（辅助）；sparkline.json / performance.json 的近期走势（辅助佐证趋势方向）

**三档信号判定规则（按优先级从上到下，命中即定，不再往下判）：**

```
🔴 定投卖（破顶卖出）—— 命中任一即触发：
   1. RSI6 > 85（超买）
   2. dist_from_52w_high_pct > -2%（贴近/创52周新高）且 rsi6 > 70
   3. 单日或盘前盘后涨幅 > 10% 且 rsi6 > 75（冲高情绪过热）
   → 文案含"分批止盈 / 破顶减仓"，color:#16a34a（绿）

🟢 定投买（下跌抄底）—— 未触发卖出信号，且命中任一即触发：
   1. RSI6 < 20（超卖）
   2. dist_from_52w_high_pct < -20%（较高点深度回撤 ≥20%）且 rsi6 < 45
   3. 单日或盘前盘后跌幅 > 6% 且 rsi6 < 40（恐慌错杀）
   → 文案含"分批定投买入 / 逢跌加仓"，color:#dc2626（红）

⚪ 观望持有 —— 以上均未命中：
   → 文案："信号中性，维持定投节奏 / 持有观望"，color:#6b7280（灰）
```

**特殊标注（叠加在三档之上，非独立档位）：**
- 若命中财报/重大事件窗口（见步骤 2.7 财报检测 或 `upcoming_events` 3日内有财报）→ 信号后追加"⚠️事件窗口，建议财报后再动手"
- 若 `rsi6` 为 None（技术指标缺失）→ 降级为纯价格判定（只用 dist_52w + 涨跌幅两组规则），并在文案标注"（RSI缺失，仅价格判定）"

**落地位置（三处，必须同时写）：**
1. 逐股详解每只股 `<ul>` 中新增 `🎯 定投信号` 条目（见步骤 2.5 模板）
2. 新增独立汇总表 `🎯 定投买卖点建议（全量 15 只）`，插在"逐股详解"与"板块关联分析"之间（见步骤 2.5 模板）
3. **总览图（render_overview.py 生成的 PNG）新增"定投"列**：脚本内置 `compute_advice()`，优先读股票 `advice_label` 字段，无则按上述规则现算。因 matplotlib 字体不支持 emoji 圆圈，图内用「定投买▲(红#dc2626) / 定投卖▼(绿#16a34a) / 观望—(灰#6b7280)」文字符号。构造 overview_data 时若能带上 `advice_label`/`rsi6` 字段可保证图与 HTML 口径一致

**微信简报补充**：第二条 notify 的"📈 自选股行情"区块新增一行 `・定投信号：` 汇总当日出现的买/卖信号（如 `🟢买 3 只(MU/XPEV/CRCL) 🔴卖 1 只(INTC) ⚪其余观望`），无买卖信号时写"全部观望"。

**颜色纪律**：定投买=红 `#dc2626`（与红涨绿跌一致，买入抄底=看多=红），定投卖=绿 `#16a34a`，观望=灰 `#6b7280`。

### 步骤 2.6：数据验证护栏

**在推送前必须执行验证**，调用 `fetch_quotes.validate_report(json_path, png_path, num_stocks=11)`：
```python
from scripts.fetch_quotes import validate_report
errors = validate_report("daily/daily_YYYYMMDD_HHMM.json", "images/daily_YYYYMMDD_HHMM.png", num_stocks=11)
if errors:
    # 终止推送！通过 notify 报告错误
    ...
```

验证项：
1. JSON 文件存在且可解析
2. 必填字段完整（slug/date/generated_at/title/has_stock/has_web3/image/stock_body_html/web3_body_html/tickers）
3. has_stock / has_web3 为 True
4. 逐股详解 `<h4>` 数量 = 自选股数量（当前 11）
5. stock_body_html 长度 >= 3000 字符
6. 图片文件存在且 >= 20KB

### 步骤 3：生成异常信号总览图（PNG）

调用 `scripts/render_overview.py`，生成适合手机竖屏的亮色系表格图：
```bash
python3 /data/workspace/.agent/skills/stock-and-web3/scripts/render_overview.py \
  --input /tmp/overview_data.json \
  --output /data/workspace/YoungStockDaily/images/daily_YYYYMMDD_HHMM.png
```

**⚠️ /tmp/overview_data.json 每只股必须包含以下字段（缺一不可！）：**
```json
{
  "generated_at": "2026-05-01 19:02",
  "session_label": "盘前",
  "stocks": [
    {
      "symbol": "MU",
      "name": "美光科技",
      "close_price": 517.16,
      "pct_1d": -0.25,
      "extended_price": 507.75,
      "extended_pct": -1.82,
      "dist_from_52w_high_pct": -3.42,
      "signals": ["日跌>4%"]
    }
  ]
}
```
**🚫 严禁遗漏 `close_price` / `extended_price` / `extended_pct` / `dist_from_52w_high_pct` 中的任何一个字段！否则图片中这些列会显示为 `--`！**

图片标题固定为"自选股行情总览"，宽 1080px，高度随行数动态。亮色 `#f7f9fc` 背景。**红涨绿跌**。

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

**⚠️ web3_body_html 格式强制规范（写入 daily JSON 前必须遵守）：**

Web3 日报原始数据是混合格式（HTML标签 + Markdown残留），前端虽有 `formatWeb3Html` 后处理，但**生成端也必须确保数据质量**：

1. **严禁**在 HTML 闭合标签后多加 `<br>`（如 `</h3><br>`、`</li><br>`、`<hr><br>` 都是错误的）
2. **严禁**用独占一行的 `<br>` 作为空行分隔（应直接用 `\n\n`）
3. **段内换行可以用 `<br>`**（如"影响等级: High<br>\n核心事件:"），但不要在 HTML 结构标签后面加
4. **表格必须用 HTML `<table>` 标签**，严禁保留 Markdown 管道语法（`| 列1 | 列2 |`）
5. **引用必须用 `<blockquote>` 标签**，严禁保留 Markdown `>` 语法
6. **加粗必须用 `<strong>` 标签**，严禁保留 Markdown `**` 语法
7. **有序列表必须用 `<ol><li>` 标签**，严禁保留 `1. 2. 3.` 纯文本格式
8. **无序列表的 `<li>` 必须被 `<ul>` 包裹**
9. 整个 web3_body_html 建议包裹在 `<div class="web3-report">` 中

**简而言之：web3_body_html 应该是纯净的 HTML，不含任何 Markdown 残留语法。**

### 步骤 5：更新索引并 git push

**⚠️ 严格按以下步骤执行，不要自己手写 daily.json 追加逻辑！**

```bash
# 5.1 运行 rebuild_daily_index.py 重建 data/daily.json 索引
#     它会自动扫描 daily/*.json，写入 "dailies" 数组（不是 "reports"！）
python3 /data/workspace/YoungStockDaily/scripts/rebuild_daily_index.py

# 5.2 更新 7 日 K 线数据
python3 /data/workspace/.agent/skills/stock-and-web3/scripts/fetch_sparkline.py \
  /data/workspace/YoungStockDaily/data/sparkline.json

# 5.3 同步 watchlist → portfolio
cp /data/workspace/portfolio/watchlist.json /data/workspace/YoungStockDaily/data/portfolio.json

# 5.4 git add + commit + push（必须包含 daily.json + sparkline.json + portfolio.json）
cd /data/workspace/YoungStockDaily
git add -A
git commit -m "📈 日报 YYYY-MM-DD HH:MM | <一句话摘要>"
TOKEN=$(cat ~/.config/knot/github_token)
git push "https://x-access-token:${TOKEN}@github.com/tracyyoung666/YoungStockDaily.git" main
```

**🚫 绝对禁止**：
1. 不要自己 `json.dump` 直接写 `data/daily.json`——必须用 `rebuild_daily_index.py`
2. 不要把新条目追加到 `reports` 或其他字段——前端只读 `dailies` 数组
3. 不要忘记 `git add -A`（确保 daily.json + sparkline.json + 图片全部提交）

### 步骤 6：通过 notify 推送（两条，先图后文）

**🎯 推送目标（方案 B）**：所有 notify 推送均发送到**当前会话 / 群聊 ChatID `T21660007A`**。
> 背景：定时任务默认运行在隔离会话（isolated），其 notify 路由曾出现投递丢失。为确保你能收到，jobMessage 已强制指定推送到当前会话 ChatID。若某条 notify 返回超时/失败，必须**重试至多 3 次**；3 次仍失败则记录并在下次任务补发。

**第一条（总览图，✅ 用 Markdown 图片语法直接显示）**：
- title: `📈 自选股行情分析 | YYYY-MM-DD HH:MM`
- message（✅ 用 `![]()` 让图片在 IM 内直接渲染显示，已于 2026-06-10 验证 GitHub raw 链接在企微端可正常显示）：
  ```
  实时价格总览图：

  ![自选股总览图](https://raw.githubusercontent.com/tracyyoung666/YoungStockDaily/main/images/daily_YYYYMMDD_HHMM.png)
  ```
  > 注：图片直链必须是 push 成功后的 GitHub raw 地址（文件名用本次实际生成的 `daily_YYYYMMDD_HHMM.png`）。务必先 git push 成功、再推送此条，否则链接 404 裂图。

**第二条（文字简报，仅精简摘要）**：
- title: `📝 今日投研简报 | YYYY-MM-DD HH:MM`
- message 格式（严格按模版，**首行仅保留站点根地址**）：
  ```
  🔗 https://youngstockdaily.pages.dev/

  ━━━ 📈 自选股行情 ━━━
  ・异常信号：<列 1-3 条关键异常>
  ・定投信号：<🟢买 X 只(代码) 🔴卖 Y 只(代码) ⚪其余观望；无买卖则写"全部观望">
  ・建议动作：<列 1-2 条>

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

## 周报流程（每周六 20:00 自动触发）

周报是对本周 5 个交易日日报的聚合复盘。周六/周日不再推送日报。

**周报内容板块**：
1. 📊 本周涨跌排名（按累计涨跌排序）
2. 🚨 本周异常事件回顾
3. 📰 本周重要新闻 TOP 5
4. 📅 下周关键事件预告（财报日/除权日）
5. 💡 下周操作策略建议
6. 🪙 本周 Web3 摘要

## 财报分析流程（步骤 2.7，在标准六步流程的步骤 2.6 之后执行）

### 触发条件（必须同时满足"初筛 + 确认"两阶段）

在每日投研推送流程中（步骤 2 获取行情后），按以下两阶段检查：

#### 阶段一：初筛（满足任意一项即进入确认阶段）

1. **事件日历匹配**：`westock-data reserve` 返回某只股票的 `disclosureDate` 在**过去3个自然日内**（含今天），这样能覆盖周末发布的情况（如周日发布的财报到周一仍能检测）
2. **新闻关键词检测**：该股票新闻标题中包含以下关键词之一：`财报`、`earnings`、`Q1`/`Q2`/`Q3`/`Q4`、`季度业绩`、`beat`、`miss`、`超预期`、`不及预期`、`每股收益`、`EPS`、`营收`、`revenue`
3. **盘后/盘前异常波动**：`extended_pct_vs_close` 绝对值 > 10%（大幅财报反应的特征）
4. **🆕 日涨幅异常 + 量比**：当日涨跌幅绝对值 > 10% 且量比 > 2，应主动检查是否为财报驱动

#### 阶段二：确认财报已实际发布（🚨关键！防止误判）

初筛命中后，**必须验证财报确实已发布**，而非仅到了预定披露日：

1. **时间窗口判断**：
   - 美股财报既可能在**盘后（16:00 ET后）**发布，也可能在**盘前（开盘前）**发布
   - 盘后发布 → 对应北京时间次日凌晨 04:00+
   - 盘前发布 → 对应北京时间当天晚间 18:00-21:30
   - **规则（简化为：不依赖发布时段猜测，而是用新闻验证来确认）**：
     - `disclosureDate` 在过去3天内（含今天）→ 进入初筛
     - 然后在阶段二通过搜索新闻来确认是否已实际发布（搜到具体财务数据 = 已发布）
     - **不再区分"仅早9点"或"仅晚19点"触发**——任何一次定时任务只要发现 disclosureDate 匹配 + 新闻中有具体财务数据，就确认并生成

2. **新闻验证**：必须通过 `westock-data news` 能搜索到**包含具体财务数据**的新闻（如"营收XX亿"、"EPS $X.XX"、"同比增长XX%"），而不仅仅是"即将发布"或"预告"类新闻

3. **如果无法确认已发布**：标记为"待确认"，跳过本次，等下一次定时任务再检查

### 排除条件

- 如果 `data/earnings.json` 中已存在该 `SYMBOL-YYYYQN` 条目，跳过（避免重复生成）
- 如果只有"即将发布财报"类预告新闻，没有实际业绩数据，跳过

### 生成步骤

确认财报已发布后，执行以下步骤：

1. **确认财报期间**：根据 `westock-data reserve` 的 `reportEndDate` 字段（如 `FY2026Q1`）确定期间
2. **收集财报数据**：
   - 通过 `westock-data news` 获取最新财报相关新闻（含具体数据）
   - 通过 `web_search` 搜索 "{SYMBOL} Q{N} {YEAR} earnings results" 获取详细数据（EPS/营收/分部表现/指引等）
   - 通过 `westock-data finance` 获取历史季度数据做同比对比
   - 通过 `westock-data rating` + `westock-data consensus` 获取市场预期作为对比基准
3. **🆕 获取 SEC Filing 原文**：
   - 运行 `python3 scripts/fetch_sec_filing.py {SYMBOL} {YYYYQN} --download --output-dir {REPO}/earnings-filings --json`
   - 脚本自动从 SEC EDGAR 查找匹配的 10-Q/10-K（美国公司）或 6-K/20-F（外国公司）
   - 下载原始 HTM 文件到 `earnings-filings/SYMBOL-YYYYQN-sec-filing.htm`
   - 将 sec_filing 信息（form/filing_date/sec_url/sec_index_url/local_file）写入 earnings.json 对应条目
4. **生成 `earnings/SYMBOL-YYYYQN.html`**：参照已有模板（如 `earnings/NBIS-2026Q1.html`），必须包含：
   - **SEC 原文下载栏**（在 header 后面）：3个按钮（查看SEC原文/Filing目录/下载本地归档）+ 提交日期
   - KPI 速览（营收/EPS/净利润/核心业务指标）
   - 业务分部表（各业务线营收+YoY+亮点）
   - 核心亮点分析（3-5 条）
   - 风险与关注点（3-4 条）
   - 投资建议（短期/中期/风险控制/关键价位）
   - 与市场预期对比表
   - **🆕 📖 财报完整分析板块**（在页面底部）：基于 SEC Filing 原文的深度解读，结构包括：
     ① SEC Filing 概要（filing类型/日期/内容结构）
     ② 分部收入深度解析（逐业务线拆解+表格）
     ③ 利润率与费用结构分析
     ④ 资产负债表与现金流要点
     ⑤ 管理层讨论与分析（MD&A）摘要
     ⑥ 10-Q/10-K 风险因素更新
     ⑦ 前瞻展望与催化剂
5. **更新 `data/earnings.json`**：追加新条目（symbol/name/period/period_label/fiscal_end/report_date/verdict/verdict_label/eps_actual/eps_estimate/revenue_actual/revenue_estimate/revenue_unit/url/generated_at/sec_filing）
6. **git add + commit**（随日报一起推送即可）

### 推送补充

如果生成了新的财报分析，在第二条 notify（投研简报）的异常信号中额外加一行：
```
📊 新增财报分析：AMD 2026Q1 超预期 → https://youngstockdaily.pages.dev/earnings/AMD-2026Q1.html
```

## 定时任务调度规则

| 时间 | 任务 | 说明 |
|---|---|---|
| **周一~周五 09:00** | 日报推送 | 盘后数据 |
| **周一~周五 19:00** | 日报推送 | 盘前数据 |
| **周六 20:00** | **周报推送** | 本周聚合复盘 |
| 周六/周日 09:00 & 19:00 | **不推送** | |

## 常见场景速查

- **"帮我跑一下今天的分析"** → 跳过步骤 1，执行 2-6
- **"把 NVDA 加入自选，然后推一版"** → 执行 1-6
- **"只推 Web3 日报"** → 只执行 4-6（步骤 5 不生成股票报告）
- **"看一下我的自选股"** → 只执行步骤 1 的读取部分，返回 JSON

## 参考文件

- `references/data-schemas.md` - watchlist.json / daily.json / overview_data JSON schema
- `references/wechat-format.md` - Markdown → 微信纯文本转换规则
- `references/premarket.md` - 盘前价获取和时段判定
- `scripts/render_overview.py` - 异常信号总览图渲染（matplotlib，红涨绿跌）
- `scripts/fetch_quotes.py` - v4 统一行情抓取（盘前/盘后/盘中 + RSI6 + 新闻 + 评级 + 事件 + 板块）
- `scripts/fetch_sparkline.py` - 7日K线数据获取
- `scripts/build_web3_pages.py` - 扫描 web3-archive 生成 HTML 详情页

## 异常与回退

- git push 401：检查 token 是否过期
- 盘前/盘后接口超时：跳过扩展时段价，只用收盘价
- matplotlib 字体找不到：用 `DejaVu Sans` 兜底
- Web3 API 超时：用最近一次 `/data/workspace/web3-archive/digests/` 最新文件

任一步失败，用 notify 发 title `❌ 投研推送失败 | YYYY-MM-DD`，message 说明失败步骤和原因。
