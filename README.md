# Young's Stock Daily

> 个人自选股每日分析日志 · 自托管静态站点 · Cloudflare Pages 自动部署

## 📖 简介
本仓库保存每日自选股分析报告。每次提交后 Cloudflare Pages 会自动触发部署，可随时访问在线查看。

- **首页** `/index.html`：报告列表 + 分类筛选 + 关键词搜索
- **详情页** `/reports/YYYY-MM-DD.html`：单日完整分析，顶部含可全屏查看的预览图
- **图片** `/images/YYYY-MM-DD.png`：微信推送用的可视化总览图，同时在网页顶部展示
- **索引** `/data/reports.json`：报告列表（供首页渲染）

## 🗂 目录结构
```
.
├── index.html              # 首页
├── reports/
│   └── YYYY-MM-DD.html     # 每日详情页
├── data/
│   └── reports.json        # 报告索引（前端读取）
├── images/
│   └── YYYY-MM-DD.png      # 每日可视化图（推送用）
└── assets/
    ├── style.css           # 亮色主题样式（响应式）
    └── app.js              # 首页筛选 + 详情页图片 Lightbox
```

## ✨ 特性
- 🌤 纯静态站点，零依赖，适配 Cloudflare Pages / GitHub Pages
- 📱 响应式布局，手机 / 平板 / 桌面均友好
- 🔍 首页支持按日期、股票代码、分类搜索
- 🖼 详情页顶部预览图点击全屏查看
- 🎨 亮色主题（#f7f9fc 背景 + 蓝色强调）

## 📝 更新方式
由 AI 助手（Knot）自动生成：每次分析完毕，自动追加到 `reports/`、`images/`、`data/reports.json`，然后 commit + push。

## ⚠️ 免责声明
内容仅为个人投资备忘，不构成任何投资建议。
