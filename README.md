# 📈 Young's Stock Daily

> 自托管的每日自选股分析日志 · 纯静态站点 · Deploy on Cloudflare Pages

## 🌐 访问

每次向本仓库 push 后，Cloudflare Pages 会自动触发部署，数秒内即可在线访问最新报告。

## 📂 目录结构

```
YoungStockDaily/
├── index.html                  # 列表首页（读取 data/reports.json）
├── assets/
│   ├── style.css               # 亮色主题，响应式
│   └── app.js                  # 列表筛选 + 详情图片灯箱
├── data/
│   └── reports.json            # 报告索引（元数据）
├── reports/
│   └── YYYY-MM-DD.html         # 每日报告详情页（含顶部预览图 + 全文）
├── images/
│   └── YYYY-MM-DD.png          # 每日异常信号总览图（微信推送用）
├── _headers                    # Cloudflare Pages 缓存策略
└── README.md
```

## 🎨 特性

- ✅ **响应式设计**，PC 与手机自适应
- ✅ **首页卡片列表** + 关键词搜索 + 分类筛选
- ✅ **详情页顶部预览图**（点击或任意键关闭，全屏查看）
- ✅ **完整文字报告**：异常信号表、组合总结、行动清单、逐股详解
- ✅ **亮色主题**（#f7f9fc 底 + 纯白卡片 + 品牌蓝强调）

## 📝 添加新报告流程

1. 生成图片 → `images/YYYY-MM-DD.png`
2. 生成详情页 HTML → `reports/YYYY-MM-DD.html`
3. 在 `data/reports.json` 顶部追加一条元数据
4. `git add . && git commit -m "report: YYYY-MM-DD" && git push`
5. Cloudflare Pages 自动部署，秒级生效

## 📊 报告分类

| 标签 | 用途 |
|---|---|
| 实时行情分析 | 盘前/盘后速览，重点在异常信号 + 操作建议 |
| 周度复盘 | 周末复盘，持仓逻辑复检 |
| 事件驱动 | 财报/重大新闻/异动触发 |
| 深度研究 | 单标的深度专题 |

## ⚠️ 免责声明

本站内容为个人投资笔记，仅供研究与记录，不构成任何投资建议。
