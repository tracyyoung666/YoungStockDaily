/* ================================================================
   YoungStockDaily · 前端 SPA v7
   - 数据源：data/daily.json 索引 + daily/daily_YYYYMMDD_HHMM.json 全量
   - 三个一级 Tab：今日最新 / 分析日报 / 自选股
   - 分析日报：列表 <-> 详情 原地切换（hash 路由 #daily/<slug>）
   - 去白框 UI：内容直接平铺
   - v6 修复：版本化 ?v= 击穿浏览器缓存；_indexPromise 失败时 console 明显提示
   - v7 修复：兼容 JSON 缺少 has_stock/has_web3/image 字段，从内容自动推断
   ================================================================ */

(function () {
  'use strict';

  // ================= 工具 =================
  function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function bust(url) { return url + (url.indexOf('?') === -1 ? '?' : '&') + '_=' + Date.now(); }
  function fetchJSON(url) {
    return fetch(bust(url)).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status + ' ' + url);
      return r.json();
    });
  }
  /* 从 daily JSON 抽出的 body HTML 里，相对路径 ../images/xxx.png 在首页根目录下访问时不生效
     需改成 images/xxx.png */
  function rewriteRelativePaths(html) {
    if (!html) return '';
    return html
      .replace(/src="\.\.\/(images\/[^"]+)"/g, 'src="$1"')
      .replace(/href="\.\.\/(images\/[^"]+)"/g, 'href="$1"');
  }

  /* Web3 报告 HTML 后处理：将混合格式（HTML标签 + 残留Markdown）转为纯净 HTML */
  function formatWeb3Html(html) {
    if (!html) return '';
    var s = html;

    // === 阶段0：精确清理多余的 <br> 标签 ===
    // 0a. 删除 HTML 闭合标签后紧跟的 <br>（如 </h3><br>, </li><br>, <hr><br>）
    s = s.replace(/(<\/(?:h[1-6]|li|ul|ol|table|tr|td|th|blockquote|div|p|figure|figcaption|section)>)\s*<br\s*\/?>/gi, '$1');
    s = s.replace(/(<hr\s*\/?>)\s*<br\s*\/?>/gi, '$1');
    // 0b. 删除 HTML 开始标签前紧跟的 <br>（如 <br>\n<h3>）
    s = s.replace(/<br\s*\/?>\s*\n?\s*(<(?:h[1-6]|hr|table|ul|ol|blockquote|div|section)\b)/gi, '\n$1');
    // 0c. 删除独占一行的纯 <br>（空行标记）
    s = s.replace(/^\s*<br\s*\/?>\s*$/gm, '');
    // 0d. Markdown 表格行末的 <br> 转为 \n（让表格正则能匹配连续行）
    s = s.replace(/\|<br\s*\/?>\s*\n?/gi, '|\n');
    // 0e. 剩余的 <br> 保留（段内有意义的换行）
    // 0f. 清理连续空行
    s = s.replace(/\n{3,}/g, '\n\n');

    // === 阶段1：Markdown 内联语法 ===
    // **bold** → <strong>bold</strong>
    s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

    // === 阶段2：Markdown blockquote（> 开头的行）===
    s = s.replace(/(?:^|\n)>\s*([^\n]+)/g, function (match, content) {
      return '\n<blockquote class="web3-quote">' + content.trim() + '</blockquote>';
    });

    // === 阶段3：Markdown 表格 → HTML table ===
    // 匹配连续的 | 开头的行（至少2行）
    s = s.replace(/((?:^|\n)\|[^\n]+\|(?:\n\|[^\n]+\|)+)/g, function (block) {
      var rows = block.trim().split('\n').filter(function (r) { return r.trim(); });
      if (rows.length < 2) return block;
      var tableHtml = '<table class="web3-table">';
      var isFirstDataRow = true;
      rows.forEach(function (row) {
        // 跳过分隔行 |---|---|
        if (/^\s*\|[\s\-:|]+\|\s*$/.test(row)) return;
        var cells = row.split('|').filter(function (c, i, arr) {
          return i > 0 && i < arr.length - 1;
        });
        if (!cells.length) return;
        var tag = isFirstDataRow ? 'th' : 'td';
        tableHtml += '<tr>';
        cells.forEach(function (c) {
          tableHtml += '<' + tag + '>' + c.trim() + '</' + tag + '>';
        });
        tableHtml += '</tr>';
        isFirstDataRow = false;
      });
      tableHtml += '</table>';
      return tableHtml;
    });

    // === 阶段4：裸 <li> 包裹进 <ul> ===
    s = s.replace(/((?:\s*<li>[\s\S]*?<\/li>\s*)+)/g, function (match, g, offset) {
      // 检查前面是否已有 <ul> 或 <ol>
      var before = s.substring(Math.max(0, offset - 5), offset);
      if (/<[uo]l/i.test(before)) return match;
      return '<ul class="web3-list">' + match.trim() + '</ul>';
    });

    // === 阶段5：有序列表（数字. 开头的行）===
    s = s.replace(/((?:^|\n)\d+\.\s+<strong>[^\n]+(?:\n|$))+/g, function (block) {
      var items = block.trim().split('\n').filter(function (l) { return l.trim(); });
      var ol = '<ol class="web3-ordered-list">';
      items.forEach(function (item) {
        var content = item.replace(/^\d+\.\s+/, '');
        ol += '<li>' + content + '</li>';
      });
      ol += '</ol>';
      return ol;
    });

    // === 阶段6：美化标签 ===
    // 给 <hr> 加 class
    s = s.replace(/<hr\s*\/?>/gi, '<hr class="web3-divider">');

    // 给已有的 <blockquote>（没有 class 的）加 class
    s = s.replace(/<blockquote>(?![\s\S]*class=)/g, '<blockquote class="web3-quote">');

    // === 阶段7：清理残留 ===
    // 清理孤立的换行变成的空白段落
    s = s.replace(/\n\n+/g, '\n');
    // 去掉 <p>\n</p> 这种空段落
    s = s.replace(/<p>\s*<\/p>/g, '');

    return s;
  }

  // ================= Tab 切换 & 路由 =================
  function initTabs() {
    document.querySelectorAll('.tab-btn').forEach(function (b) {
      b.addEventListener('click', function () {
        const name = b.dataset.tab;
        try { history.replaceState(null, '', '#' + name); } catch (e) {}
        activateTab(name);
        if (name === 'daily') showDailyList();
      });
    });
    routeFromHash();
    window.addEventListener('hashchange', routeFromHash);
  }
  function activateTab(name) {
    document.querySelectorAll('.tab-btn').forEach(function (b) {
      b.classList.toggle('active', b.dataset.tab === name);
    });
    document.querySelectorAll('.tab-panel').forEach(function (p) {
      p.classList.toggle('active', p.dataset.panel === name);
    });
  }
  function routeFromHash() {
    const h = (location.hash || '').replace('#', '');
    if (!h) { activateTab('today'); return; }
    const parts = h.split('/');
    const tab = parts[0];
    if (['today', 'daily', 'portfolio'].indexOf(tab) === -1) { activateTab('today'); return; }
    activateTab(tab);
    if (tab === 'daily') {
      if (parts[1]) showDailyDetail(decodeURIComponent(parts[1]));
      else showDailyList();
    }
  }

  // ================= 共享索引 =================
  const _indexPromise = fetchJSON('data/daily.json').catch(function (e) {
    console.error(e); return { dailies: [] };
  });

  // ================= Tab 1：今日最新 =================
  function initToday() {
    const box = document.getElementById('today-container');
    if (!box) return;
    _indexPromise.then(function (idx) {
      const list = (idx.dailies || []).slice().sort(function (a, b) {
        return (b.date + ' ' + b.generated_at).localeCompare(a.date + ' ' + a.generated_at);
      });
      const latest = list[0];
      if (!latest) {
        box.innerHTML = '<div class="empty-state"><h3>暂无报告</h3></div>';
        return;
      }
      // 先渲染 7 天走势迷你图区域，再渲染详情
      var sparkHtml = buildSparklineSection(list);
      box.innerHTML = sparkHtml;
      // 走势对比图区域
      var perfBox = document.createElement('div');
      perfBox.id = 'performance-container';
      box.appendChild(perfBox);
      loadPerformanceChart(perfBox);
      var detailBox = document.createElement('div');
      box.appendChild(detailBox);
      renderDetail(detailBox, latest.slug, { isTodayHeader: true });
    });
  }

  // ================= 7天K线迷你图 =================
  function buildSparklineSection(dailyList) {
    var html = '<div class="sparkline-section">';
    html += '<h3 class="sparkline-title">📈 最近 7 日 K 线走势</h3>';
    html += '<div class="sparkline-grid" id="sparkline-grid">';
    html += '<div class="sparkline-loading">加载K线数据中…</div>';
    html += '</div></div>';
    setTimeout(function () { loadKlineData(); }, 100);
    return html;
  }

  function loadKlineData() {
    var grid = document.getElementById('sparkline-grid');
    if (!grid) return;

    fetchJSON('data/sparkline.json').then(function (data) {
      var stocks = data.stocks || {};
      var symbols = Object.keys(stocks);
      if (symbols.length === 0) {
        grid.innerHTML = '<div class="sparkline-empty">暂无K线数据</div>';
        return;
      }

      var html = '';
      symbols.forEach(function (sym) {
        var klines = stocks[sym];
        if (!klines || klines.length < 2) return;

        var first = klines[0];
        var last = klines[klines.length - 1];
        var weekPct = ((last.close - first.open) / first.open * 100).toFixed(2);
        var isWeekUp = last.close >= first.open;
        var themeColor = isWeekUp ? '#dc2626' : '#16a34a';

        // 计算全局高低
        var allHigh = Math.max.apply(null, klines.map(function (k) { return k.high; }));
        var allLow = Math.min.apply(null, klines.map(function (k) { return k.low; }));
        var priceRange = allHigh - allLow || 1;

        // SVG K线图参数
        var W = 154, H = 52, PAD_T = 3, PAD_B = 3, PAD_X = 6;
        var barW = Math.min(14, (W - PAD_X * 2) / klines.length - 2);
        var gap = (W - PAD_X * 2 - barW * klines.length) / (klines.length - 1 || 1);

        var svgContent = '';
        klines.forEach(function (k, i) {
          var x = PAD_X + i * (barW + gap) + barW / 2;
          var isUp = k.close >= k.open;
          var bodyTop = isUp ? k.close : k.open;
          var bodyBot = isUp ? k.open : k.close;
          var color = isUp ? '#dc2626' : '#16a34a';

          // Y 坐标映射（价格 → 像素，Y 轴反转）
          var yHigh = PAD_T + (1 - (k.high - allLow) / priceRange) * (H - PAD_T - PAD_B);
          var yLow = PAD_T + (1 - (k.low - allLow) / priceRange) * (H - PAD_T - PAD_B);
          var yBodyTop = PAD_T + (1 - (bodyTop - allLow) / priceRange) * (H - PAD_T - PAD_B);
          var yBodyBot = PAD_T + (1 - (bodyBot - allLow) / priceRange) * (H - PAD_T - PAD_B);
          var bodyH = Math.max(1, yBodyBot - yBodyTop);

          // 上下影线
          svgContent += '<line x1="' + x.toFixed(1) + '" y1="' + yHigh.toFixed(1) + '" x2="' + x.toFixed(1) + '" y2="' + yLow.toFixed(1) + '" stroke="' + color + '" stroke-width="1.2"/>';
          // 实体
          svgContent += '<rect x="' + (x - barW / 2).toFixed(1) + '" y="' + yBodyTop.toFixed(1) + '" width="' + barW + '" height="' + bodyH.toFixed(1) + '" fill="' + (isUp ? color : color) + '" rx="1"/>';
        });

        html += '<div class="sparkline-card" style="border-color: ' + themeColor + '22;">';
        html += '<div class="sparkline-header">';
        html += '<span class="sparkline-sym">' + sym + '</span>';
        html += '<span class="sparkline-price" style="color:' + themeColor + '">$' + last.close.toFixed(2) + '</span>';
        html += '</div>';
        html += '<svg class="sparkline-svg" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none">';
        html += svgContent;
        html += '</svg>';
        html += '<div class="sparkline-footer">';
        html += '<span class="sparkline-range">' + first.date.slice(5) + '~' + last.date.slice(5) + '</span>';
        html += '<span class="sparkline-pct" style="color:' + themeColor + '">' + (isWeekUp ? '+' : '') + weekPct + '%</span>';
        html += '</div>';
        html += '</div>';
      });

      grid.innerHTML = html;
    }).catch(function () {
      grid.innerHTML = '<div class="sparkline-empty">K线数据加载失败</div>';
    });
  }

  // ================= 自选股走势对比图 =================
  var PERF_COLORS = [
    '#dc2626', '#2563eb', '#16a34a', '#d97706', '#7c3aed',
    '#db2777', '#0891b2', '#65a30d', '#c026d3', '#ea580c', '#4f46e5'
  ];

  function loadPerformanceChart(container) {
    fetchJSON('data/performance.json').then(function (data) {
      var stocks = data.stocks || {};
      var symbols = Object.keys(stocks);
      if (symbols.length === 0) return;

      // 归一化：以第一天收盘价为基准，计算每天的涨跌幅%
      var allDates = [];
      var normalized = {}; // { symbol: [{date, pct}] }

      symbols.forEach(function (sym) {
        var klines = stocks[sym];
        if (!klines || klines.length < 2) return;
        var base = klines[0].close;
        normalized[sym] = klines.map(function (k) {
          return { date: k.date, pct: ((k.close - base) / base) * 100 };
        });
        // 收集所有日期
        klines.forEach(function (k) {
          if (allDates.indexOf(k.date) === -1) allDates.push(k.date);
        });
      });
      allDates.sort();

      // 计算最终涨跌排名
      var finalRank = symbols.filter(function (s) { return normalized[s]; }).map(function (s) {
        var pts = normalized[s];
        return { symbol: s, finalPct: pts[pts.length - 1].pct };
      }).sort(function (a, b) { return b.finalPct - a.finalPct; });

      // 构建HTML
      var html = '<div class="perf-section">';
      html += '<h3 class="perf-title">📊 自选股走势对比 <small>近' + allDates.length + '个交易日 · 归一化涨跌幅</small></h3>';
      html += '<div class="perf-chart-wrap">';
      html += '<div class="perf-chart" id="perf-chart"></div>';
      html += '</div>';
      html += '<div class="perf-legend" id="perf-legend"></div>';
      html += '</div>';
      container.innerHTML = html;

      // 渲染SVG图表
      renderPerfSVG(allDates, normalized, finalRank);
    }).catch(function () {
      container.innerHTML = '';
    });
  }

  function renderPerfSVG(dates, normalized, rankList) {
    var chartEl = document.getElementById('perf-chart');
    var legendEl = document.getElementById('perf-legend');
    if (!chartEl || !legendEl) return;

    var W = 800, H = 360;
    var PAD = { top: 30, right: 70, bottom: 40, left: 56 };
    var plotW = W - PAD.left - PAD.right;
    var plotH = H - PAD.top - PAD.bottom;

    // 计算Y轴范围
    var allPcts = [];
    rankList.forEach(function (r) {
      (normalized[r.symbol] || []).forEach(function (p) { allPcts.push(p.pct); });
    });
    var yMin = Math.min.apply(null, allPcts);
    var yMax = Math.max.apply(null, allPcts);
    var yPad = (yMax - yMin) * 0.1 || 5;
    yMin -= yPad; yMax += yPad;

    // 颜色映射
    var colorMap = {};
    rankList.forEach(function (r, i) { colorMap[r.symbol] = PERF_COLORS[i % PERF_COLORS.length]; });

    // 隐藏状态
    var hidden = {};

    function buildSVG() {
      var svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" class="perf-svg">';

      // 背景网格
      var gridSteps = 5;
      for (var gi = 0; gi <= gridSteps; gi++) {
        var gy = PAD.top + (plotH / gridSteps) * gi;
        var gVal = yMax - ((yMax - yMin) / gridSteps) * gi;
        svg += '<line x1="' + PAD.left + '" y1="' + gy.toFixed(1) + '" x2="' + (W - PAD.right) + '" y2="' + gy.toFixed(1) + '" stroke="#e2e8f0" stroke-width="0.5"/>';
        svg += '<text x="' + (PAD.left - 8) + '" y="' + (gy + 4).toFixed(1) + '" text-anchor="end" font-size="10" fill="#94a3b8">' + gVal.toFixed(1) + '%</text>';
      }

      // 零线
      if (yMin < 0 && yMax > 0) {
        var zeroY = PAD.top + ((yMax - 0) / (yMax - yMin)) * plotH;
        svg += '<line x1="' + PAD.left + '" y1="' + zeroY.toFixed(1) + '" x2="' + (W - PAD.right) + '" y2="' + zeroY.toFixed(1) + '" stroke="#64748b" stroke-width="1" stroke-dasharray="4,3"/>';
      }

      // X轴日期标签（间隔显示）
      var xStep = Math.max(1, Math.floor(dates.length / 6));
      dates.forEach(function (dt, i) {
        if (i % xStep === 0 || i === dates.length - 1) {
          var x = PAD.left + (i / (dates.length - 1)) * plotW;
          svg += '<text x="' + x.toFixed(1) + '" y="' + (H - PAD.bottom + 18) + '" text-anchor="middle" font-size="10" fill="#94a3b8">' + dt.slice(5) + '</text>';
        }
      });

      // 绘制每只股票的折线
      rankList.forEach(function (r) {
        if (hidden[r.symbol]) return;
        var pts = normalized[r.symbol];
        if (!pts || pts.length < 2) return;
        var color = colorMap[r.symbol];
        var pathD = '';
        pts.forEach(function (p, i) {
          var di = dates.indexOf(p.date);
          if (di === -1) return;
          var x = PAD.left + (di / (dates.length - 1)) * plotW;
          var y = PAD.top + ((yMax - p.pct) / (yMax - yMin)) * plotH;
          pathD += (i === 0 ? 'M' : 'L') + x.toFixed(2) + ',' + y.toFixed(2);
        });
        // 最好/最差的线加粗
        var sw = (r === rankList[0] || r === rankList[rankList.length - 1]) ? '2.5' : '1.8';
        svg += '<path d="' + pathD + '" fill="none" stroke="' + color + '" stroke-width="' + sw + '" stroke-linecap="round" stroke-linejoin="round"/>';

        // 末端标注
        var lastPt = pts[pts.length - 1];
        var ldi = dates.indexOf(lastPt.date);
        var lx = PAD.left + (ldi / (dates.length - 1)) * plotW;
        var ly = PAD.top + ((yMax - lastPt.pct) / (yMax - yMin)) * plotH;
        svg += '<circle cx="' + lx.toFixed(1) + '" cy="' + ly.toFixed(1) + '" r="3" fill="' + color + '"/>';
        svg += '<text x="' + (lx + 6).toFixed(1) + '" y="' + (ly + 4).toFixed(1) + '" font-size="10" font-weight="600" fill="' + color + '">' + r.symbol + '</text>';
      });

      svg += '</svg>';
      return svg;
    }

    chartEl.innerHTML = buildSVG();

    // 图例
    var legendHtml = '';
    rankList.forEach(function (r, i) {
      var isTop = (i === 0);
      var isBottom = (i === rankList.length - 1);
      var badge = isTop ? ' 🏆' : (isBottom ? ' ⚠️' : '');
      var pctStr = (r.finalPct >= 0 ? '+' : '') + r.finalPct.toFixed(2) + '%';
      var pctColor = r.finalPct >= 0 ? '#dc2626' : '#16a34a';
      legendHtml += '<button class="perf-legend-item' + (hidden[r.symbol] ? ' disabled' : '') + '" data-sym="' + r.symbol + '">';
      legendHtml += '<span class="perf-legend-dot" style="background:' + colorMap[r.symbol] + '"></span>';
      legendHtml += '<span class="perf-legend-sym">' + r.symbol + badge + '</span>';
      legendHtml += '<span class="perf-legend-pct" style="color:' + pctColor + '">' + pctStr + '</span>';
      legendHtml += '</button>';
    });
    legendEl.innerHTML = legendHtml;

    // 点击图例切换显示
    legendEl.querySelectorAll('.perf-legend-item').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var sym = btn.getAttribute('data-sym');
        hidden[sym] = !hidden[sym];
        btn.classList.toggle('disabled', hidden[sym]);
        chartEl.innerHTML = buildSVG();
      });
    });
  }

  // ================= Tab 2：分析日报 =================
  function initDaily() {
    const listEl = document.getElementById('list-daily');
    if (!listEl) return;
    const searchInput = document.getElementById('search-daily');
    const countEl = document.getElementById('count-daily');
    const backBtn = document.getElementById('btn-daily-back');

    let all = [];

    _indexPromise.then(function (idx) {
      all = (idx.dailies || []).slice().sort(function (a, b) {
        return (b.date + ' ' + b.generated_at).localeCompare(a.date + ' ' + a.generated_at);
      });
      window.__DAILY_INDEX__ = all;
      render();
    });

    function render() {
      const q = (searchInput.value || '').trim().toLowerCase();
      const filtered = all.filter(function (r) {
        if (!q) return true;
        const hay = [r.date, r.generated_at, r.title, r.summary, (r.tickers || []).join(' ')].join(' ').toLowerCase();
        return hay.indexOf(q) !== -1;
      });
      countEl.textContent = '共 ' + filtered.length + ' 篇';
      if (!filtered.length) {
        listEl.innerHTML = '<div class="empty-state"><h3>🔍 未找到</h3></div>';
        return;
      }
      listEl.innerHTML = filtered.map(function (r) {
        const isWeekly = (r.slug || '').indexOf('weekly_') === 0;
        const badges =
          (r.has_stock ? '<span class="badge stock">📈 股票</span>' : '') +
          (r.has_web3  ? '<span class="badge web3">🪙 Web3</span>'  : '');
        const tickers = (r.tickers || []).length
          ? '<div class="tickers">' + r.tickers.map(function (t) {
              var label = (typeof t === 'string') ? t : (t.symbol || '');
              return '<span>' + escapeHtml(label) + '</span>';
            }).join('') + '</div>'
          : '';
        const img = r.image ? '<img class="thumb" src="' + escapeHtml(r.image) + '" alt="" loading="lazy">' : '';
        return '<a class="report-card' + (isWeekly ? ' weekly-card' : '') + '" data-date="' + escapeHtml(r.date) + '" href="#daily/' + encodeURIComponent(r.slug) + '">' +
                 img +
                 '<div class="date">' + escapeHtml(r.date) + ' <small>🕒 ' + escapeHtml(r.generated_at || '') + '</small></div>' +
                 '<div class="badges">' + badges + (isWeekly ? '<span class="badge weekly">📊 周报</span>' : '') + '</div>' +
                 '<div class="title">' + escapeHtml(r.title) + '</div>' +
                 '<div class="summary">' + escapeHtml(r.summary || '') + '</div>' +
                 tickers +
               '</a>';
      }).join('');
      // 注入财报条目到列表
      injectEarningsToList(listEl, filtered);
    }
    searchInput.addEventListener('input', render);

    if (backBtn) {
      backBtn.addEventListener('click', function () {
        try { history.pushState(null, '', '#daily'); } catch (e) {}
        showDailyList();
      });
    }
  }
  function showDailyList() {
    const lv = document.getElementById('daily-list-view');
    const dv = document.getElementById('daily-detail-view');
    if (lv) lv.style.display = '';
    if (dv) dv.style.display = 'none';
  }
  function showDailyDetail(slug) {
    const lv = document.getElementById('daily-list-view');
    const dv = document.getElementById('daily-detail-view');
    const body = document.getElementById('daily-detail-body');
    const dateEl = document.getElementById('daily-detail-date');
    if (!lv || !dv || !body) return;
    lv.style.display = 'none';
    dv.style.display = '';
    dateEl.textContent = slug;
    body.innerHTML = '<div class="empty-state"><h3>⏳ 加载中</h3></div>';
    renderDetail(body, slug, { isTodayHeader: false, updateToolbarDate: true });
  }

  // ================= 详情渲染（今日最新 / 日报详情共用） =================
  function renderDetail(container, slug, opts) {
    opts = opts || {};
    fetchJSON('daily/' + encodeURIComponent(slug) + '.json').then(function (d) {
      // 兼容：如果 JSON 缺少 has_stock/has_web3 字段，从内容自动推断
      var hasStock = d.has_stock != null ? d.has_stock : !!(d.stock_body_html && d.stock_body_html.length > 10);
      var hasWeb3  = d.has_web3  != null ? d.has_web3  : !!(d.web3_body_html && d.web3_body_html.length > 10);
      var imgPath  = d.image || d.overview_image || null;

      var html = '';
      // 页首元信息
      html += '<div class="daily-page-head">';
      if (opts.isTodayHeader) {
        html += '<span class="today-chip">🔥 今日最新</span>';
      }
      html += '<h1>' + escapeHtml(d.date) + ' · ' + (slug.indexOf('weekly_') === 0 ? '投研周报' : '投研日报') + '</h1>';
      html += '<div class="daily-meta">🕒 生成于 ' + escapeHtml(d.generated_at || '') + '</div>';
      html += '</div>';

      // 财报链接区域（显示在总览图上方）
      html += '<div class="earnings-links" id="earnings-links-' + slug + '"></div>';

      // 预览图
      if (imgPath) {
        html += '<figure class="hero-image-plain">' +
                  '<img src="' + escapeHtml(imgPath) + '" alt="' + escapeHtml(d.date) + ' 异常信号总览" loading="lazy">' +
                  '<figcaption>异常信号总览 · 点击可查看大图</figcaption>' +
                '</figure>';
      }

      // 锚点导航（两部分都有才显示）
      if (hasStock && hasWeb3) {
        html += '<div class="daily-anchor-nav">' +
                  '<a href="#stock-section">📈 自选股</a>' +
                  '<a href="#web3-section">🪙 Web3</a>' +
                '</div>';
      }

      // 股票区
      if (hasStock) {
        html += '<section class="daily-block" id="stock-section">' +
                  '<h2 class="daily-block-title">📈 自选股实时行情分析</h2>' +
                  '<div class="daily-block-body">' + rewriteRelativePaths(d.stock_body_html || '') + '</div>' +
                '</section>';
      }
      // Web3 区
      if (hasWeb3) {
        html += '<section class="daily-block" id="web3-section">' +
                  '<h2 class="daily-block-title">🪙 Web3 加密日报</h2>' +
                  '<div class="daily-block-body web3-content">' + formatWeb3Html(d.web3_body_html || '') + '</div>' +
                '</section>';
      }
      if (!hasStock && !hasWeb3) {
        html += '<div class="empty-state"><h3>该记录暂无内容</h3></div>';
      }
      container.innerHTML = html;
      // 加载财报链接
      loadEarningsLinks(slug, d.date);
      if (opts.updateToolbarDate) {
        const dateEl = document.getElementById('daily-detail-date');
        if (dateEl) dateEl.textContent = d.date + ' · 🕒 ' + (d.generated_at || '');
      }
      attachLightboxFor(container);
      // 处理锚点跳转（因为 hash 已被用于 SPA 路由，锚点需要 JS 平滑滚动）
      container.querySelectorAll('.daily-anchor-nav a').forEach(function (a) {
        a.addEventListener('click', function (e) {
          e.preventDefault();
          const tgt = container.querySelector(a.getAttribute('href'));
          if (tgt) tgt.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
      });
    }).catch(function (err) {
      container.innerHTML = '<div class="empty-state"><h3>😔 加载失败</h3><p>' + escapeHtml(err.message) + '</p></div>';
    });
  }

  // ================= Tab 3：自选股 =================
  function initPortfolio() {
    const box = document.getElementById('portfolio-full');
    if (!box) return;
    fetchJSON('data/portfolio.json').then(function (data) {
      const cats = data.categories || {};
      const html = Object.keys(cats).map(function (k) {
        const c = cats[k];
        const rows = (c.stocks || []).map(function (s) {
          const tags = (s.tags || []).map(function (t) { return '<span class="tag">' + escapeHtml(t) + '</span>'; }).join('');
          return '<tr>' +
                  '<td><b>' + escapeHtml(s.symbol) + '</b></td>' +
                  '<td>' + escapeHtml(s.name) + '</td>' +
                  '<td>' + escapeHtml(s.market) + '</td>' +
                  '<td>' + escapeHtml(s.added_at || '') + '</td>' +
                  '<td>' + tags + '</td>' +
                 '</tr>';
        }).join('');
        return '<div class="portfolio-cat">' +
                '<h3>📁 ' + escapeHtml(k) + ' <small>' + escapeHtml(c.description || '') + '</small></h3>' +
                '<div class="table-wrap"><table class="portfolio-table">' +
                  '<thead><tr><th>代码</th><th>名称</th><th>市场</th><th>加入日期</th><th>标签</th></tr></thead>' +
                  '<tbody>' + rows + '</tbody>' +
                '</table></div>' +
               '</div>';
      }).join('');
      box.innerHTML = html || '<div class="empty-state"><h3>暂无自选股</h3></div>';
      const up = document.getElementById('portfolio-updated');
      if (up) up.textContent = '更新于 ' + (data.updated_at || '未知');
    }).catch(function (err) {
      box.innerHTML = '<div class="empty-state"><h3>😔 加载失败</h3><p>' + escapeHtml(err.message) + '</p></div>';
    });
  }

  // ================= Lightbox =================
  function buildLightboxOnce() {
    if (document.querySelector('.lightbox')) return document.querySelector('.lightbox');
    const lightbox = document.createElement('div');
    lightbox.className = 'lightbox';
    lightbox.innerHTML = '<div class="close-tip">点击任意处关闭</div><img alt="preview full">';
    document.body.appendChild(lightbox);
    lightbox.addEventListener('click', function () {
      lightbox.classList.remove('show'); document.body.style.overflow = '';
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { lightbox.classList.remove('show'); document.body.style.overflow = ''; }
    });
    return lightbox;
  }
  function attachLightboxFor(root) {
    const imgs = (root || document).querySelectorAll('.hero-image-plain img, .preview-image img');
    if (!imgs.length) return;
    const lightbox = buildLightboxOnce();
    const lightImg = lightbox.querySelector('img');
    imgs.forEach(function (img) {
      if (img.dataset.lbBound) return;
      img.dataset.lbBound = '1';
      img.style.cursor = 'zoom-in';
      img.addEventListener('click', function () {
        lightImg.src = img.src;
        lightbox.classList.add('show'); document.body.style.overflow = 'hidden';
      });
    });
  }

  // ================= 财报链接加载 =================
  var _earningsPromise = null;
  function getEarningsIndex() {
    if (!_earningsPromise) {
      _earningsPromise = fetchJSON('data/earnings.json').catch(function () { return { reports: [] }; });
    }
    return _earningsPromise;
  }

  function loadEarningsLinks(slug, reportDate) {
    getEarningsIndex().then(function (idx) {
      var reports = idx.reports || [];
      if (!reports.length) return;
      var linkEl = document.getElementById('earnings-links-' + slug);
      if (!linkEl) return;

      // 只显示 report_date 在当前报告日期同一天或同一周内的财报
      var rDate = new Date(reportDate);
      var filteredReports = reports.filter(function (r) {
        var erDate = new Date(r.report_date);
        var diffDays = Math.abs(rDate - erDate) / (1000 * 60 * 60 * 24);
        return diffDays <= 7; // 同一周内（7天内）
      });

      if (!filteredReports.length) return;

      var html = '<div class="earnings-banner">';
      html += '<div class="earnings-banner-title">📊 最新财报分析</div>';
      html += '<div class="earnings-banner-links">';
      filteredReports.forEach(function (r) {
        var verdictClass = r.verdict === 'beat' ? 'beat' : (r.verdict === 'miss' ? 'miss' : 'inline');
        html += '<a href="' + r.url + '" class="earnings-link earnings-' + verdictClass + '">';
        html += '<span class="earnings-link-sym">' + r.symbol + '</span>';
        html += '<span class="earnings-link-period">' + r.period_label + ' 财报分析</span>';
        html += '<span class="earnings-link-verdict">' + r.verdict_label + '</span>';
        html += '</a>';
      });
      html += '</div></div>';
      linkEl.innerHTML = html;
    });
  }

  // 在日报列表中按日期顺序插入财报条目（不置顶）
  function injectEarningsToList(listEl, existingItems) {
    getEarningsIndex().then(function (idx) {
      var reports = idx.reports || [];
      if (!reports.length) return;

      // 获取列表中已有的日报日期范围（取最新一条日报的日期）
      var latestDailyDate = existingItems.length ? existingItems[0].date : '';

      reports.forEach(function (r) {
        // 只在财报发布当天或当周（7天内）的列表中显示
        if (!latestDailyDate) return;
        var latest = new Date(latestDailyDate);
        var erDate = new Date(r.report_date);
        var diffDays = (latest - erDate) / (1000 * 60 * 60 * 24);
        if (diffDays > 7 || diffDays < -1) return; // 超过7天不显示

        var earningHtml = '<a class="report-card earnings-card" href="' + r.url + '" data-date="' + r.report_date + '">' +
          '<div class="date">' + r.report_date + ' <small>财报</small></div>' +
          '<div class="title">📊 ' + r.symbol + ' · ' + r.period_label + ' 财报分析</div>' +
          '<div class="summary">' + r.verdict_label + ' | EPS $' + r.eps_actual + ' vs 预期 $' + r.eps_estimate + ' | 营收 $' + r.revenue_actual + r.revenue_unit + '</div>' +
          '</a>';

        // 找到合适的插入位置（按日期排序）
        var cards = listEl.querySelectorAll('.report-card');
        var inserted = false;
        for (var i = 0; i < cards.length; i++) {
          var cardDate = cards[i].getAttribute('data-date') || cards[i].querySelector('.date').textContent.trim().slice(0, 10);
          if (r.report_date >= cardDate) {
            cards[i].insertAdjacentHTML('beforebegin', earningHtml);
            inserted = true;
            break;
          }
        }
        if (!inserted) {
          listEl.insertAdjacentHTML('beforeend', earningHtml);
        }
      });
    });
  }

  // ================= 启动 =================
  document.addEventListener('DOMContentLoaded', function () {
    console.log('%c[YSD] SPA v7 booted','color:#d4a849;font-weight:700');
    initTabs();
    initToday();
    initDaily();
    initPortfolio();
    attachLightboxFor(document);
  });
})();
