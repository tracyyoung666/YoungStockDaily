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
      var detailBox = document.createElement('div');
      box.appendChild(detailBox);
      renderDetail(detailBox, latest.slug, { isTodayHeader: true });
    });
  }

  // ================= 7天走势迷你图 =================
  function buildSparklineSection(dailyList) {
    // 取最近 7 天的日报（按日期去重，每天取最新一份）
    var dateMap = {};
    dailyList.forEach(function (d) {
      if (!dateMap[d.date] && d.has_stock) dateMap[d.date] = d;
    });
    var dates = Object.keys(dateMap).sort().slice(-7);
    if (dates.length < 2) return '';

    // 从每份日报的 tickers 和 summary 中无法直接拿到收盘价
    // 所以用 slug 异步加载 JSON 拿价格——但这里做同步布局，实际数据延迟填充
    var html = '<div class="sparkline-section">';
    html += '<h3 class="sparkline-title">📈 最近 ' + dates.length + ' 天走势</h3>';
    html += '<div class="sparkline-grid" id="sparkline-grid">';
    html += '<div class="sparkline-loading">加载走势数据中…</div>';
    html += '</div></div>';

    // 异步加载数据并渲染
    setTimeout(function () { loadSparklineData(dates, dateMap); }, 100);
    return html;
  }

  function loadSparklineData(dates, dateMap) {
    var grid = document.getElementById('sparkline-grid');
    if (!grid) return;

    // 对每个日期加载 JSON 获取收盘价
    var promises = dates.map(function (date) {
      var d = dateMap[date];
      return fetchJSON('daily/' + encodeURIComponent(d.slug) + '.json')
        .then(function (json) { return { date: date, data: json }; })
        .catch(function () { return { date: date, data: null }; });
    });

    Promise.all(promises).then(function (results) {
      // 从 stock_body_html 提取价格（找 <td>$XXX.XX</td> 模式）
      // 或从 meta 中直接取——更好的方式是解析 tickers
      var stockPrices = {}; // { symbol: [{date, close}] }

      results.forEach(function (r) {
        if (!r.data) return;
        var tickers = r.data.tickers || [];
        // 尝试从 meta.stocks 取价格
        var meta = r.data.meta || {};
        var stocks = meta.stocks || {};
        // 如果 meta 里没有 stocks，从 stock_body_html 中正则提取
        if (Object.keys(stocks).length === 0 && r.data.stock_body_html) {
          // 从表格提取：<td><strong>MU</strong></td><td>...<td>$518.46</td>
          var tableMatch = r.data.stock_body_html.match(/<tbody>([\s\S]*?)<\/tbody>/);
          if (tableMatch) {
            var rows = tableMatch[1].match(/<tr>[\s\S]*?<\/tr>/g) || [];
            rows.forEach(function (row) {
              var cells = row.match(/<td[^>]*>([\s\S]*?)<\/td>/g) || [];
              if (cells.length >= 3) {
                var symMatch = cells[0].match(/<strong>(\w+)<\/strong>/);
                var priceMatch = cells[2].match(/\$([\d.]+)/);
                if (symMatch && priceMatch) {
                  var sym = symMatch[1];
                  var price = parseFloat(priceMatch[1]);
                  if (!stockPrices[sym]) stockPrices[sym] = [];
                  stockPrices[sym].push({ date: r.date, close: price });
                }
              }
            });
          }
        } else {
          // 从 meta.stocks 取
          Object.keys(stocks).forEach(function (sym) {
            var cp = stocks[sym].close_price;
            if (cp) {
              if (!stockPrices[sym]) stockPrices[sym] = [];
              stockPrices[sym].push({ date: r.date, close: cp });
            }
          });
        }
      });

      // 渲染迷你图
      var html = '';
      var symbols = Object.keys(stockPrices);
      if (symbols.length === 0) {
        grid.innerHTML = '<div class="sparkline-empty">暂无足够数据绘制走势图</div>';
        return;
      }

      symbols.forEach(function (sym) {
        var points = stockPrices[sym].sort(function (a, b) { return a.date.localeCompare(b.date); });
        if (points.length < 2) return;
        var prices = points.map(function (p) { return p.close; });
        var minP = Math.min.apply(null, prices);
        var maxP = Math.max.apply(null, prices);
        var range = maxP - minP || 1;
        var first = prices[0];
        var last = prices[prices.length - 1];
        var totalPct = ((last - first) / first * 100).toFixed(2);
        var isUp = last >= first;
        var color = isUp ? '#16a34a' : '#dc2626';
        var bgColor = isUp ? 'rgba(22,163,74,0.06)' : 'rgba(220,38,38,0.06)';

        // SVG sparkline
        var W = 140, H = 40, PAD = 2;
        var step = (W - PAD * 2) / (prices.length - 1);
        var pathD = prices.map(function (p, i) {
          var x = PAD + i * step;
          var y = PAD + (1 - (p - minP) / range) * (H - PAD * 2);
          return (i === 0 ? 'M' : 'L') + x.toFixed(1) + ',' + y.toFixed(1);
        }).join(' ');

        // 渐变填充
        var fillD = pathD + ' L' + (PAD + (prices.length - 1) * step).toFixed(1) + ',' + H + ' L' + PAD + ',' + H + ' Z';

        html += '<div class="sparkline-card" style="border-color: ' + color + '22;">';
        html += '<div class="sparkline-header">';
        html += '<span class="sparkline-sym">' + sym + '</span>';
        html += '<span class="sparkline-price" style="color:' + color + '">$' + last.toFixed(2) + '</span>';
        html += '</div>';
        html += '<svg class="sparkline-svg" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none">';
        html += '<defs><linearGradient id="sg-' + sym + '" x1="0" y1="0" x2="0" y2="1">';
        html += '<stop offset="0%" stop-color="' + color + '" stop-opacity="0.25"/>';
        html += '<stop offset="100%" stop-color="' + color + '" stop-opacity="0.02"/>';
        html += '</linearGradient></defs>';
        html += '<path d="' + fillD + '" fill="url(#sg-' + sym + ')"/>';
        html += '<path d="' + pathD + '" fill="none" stroke="' + color + '" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>';
        // 终点圆点
        var lastX = PAD + (prices.length - 1) * step;
        var lastY = PAD + (1 - (last - minP) / range) * (H - PAD * 2);
        html += '<circle cx="' + lastX.toFixed(1) + '" cy="' + lastY.toFixed(1) + '" r="3" fill="' + color + '"/>';
        html += '</svg>';
        html += '<div class="sparkline-footer">';
        html += '<span class="sparkline-range">' + points[0].date.slice(5) + '~' + points[points.length - 1].date.slice(5) + '</span>';
        html += '<span class="sparkline-pct" style="color:' + color + '">' + (isUp ? '+' : '') + totalPct + '%</span>';
        html += '</div>';
        html += '</div>';
      });

      grid.innerHTML = html;
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
        const badges =
          (r.has_stock ? '<span class="badge stock">📈 股票</span>' : '') +
          (r.has_web3  ? '<span class="badge web3">🪙 Web3</span>'  : '');
        const tickers = (r.tickers || []).length
          ? '<div class="tickers">' + r.tickers.map(function (t) { return '<span>' + escapeHtml(t) + '</span>'; }).join('') + '</div>'
          : '';
        const img = r.image ? '<img class="thumb" src="' + escapeHtml(r.image) + '" alt="" loading="lazy">' : '';
        return '<a class="report-card" href="#daily/' + encodeURIComponent(r.slug) + '">' +
                 img +
                 '<div class="date">' + escapeHtml(r.date) + ' <small>🕒 ' + escapeHtml(r.generated_at || '') + '</small></div>' +
                 '<div class="badges">' + badges + '</div>' +
                 '<div class="title">' + escapeHtml(r.title) + '</div>' +
                 '<div class="summary">' + escapeHtml(r.summary || '') + '</div>' +
                 tickers +
               '</a>';
      }).join('');
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
      html += '<h1>' + escapeHtml(d.date) + ' · 投研日报</h1>';
      html += '<div class="daily-meta">🕒 生成于 ' + escapeHtml(d.generated_at || '') + '</div>';
      html += '</div>';

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
                  '<div class="daily-block-body">' + (d.web3_body_html || '') + '</div>' +
                '</section>';
      }
      if (!hasStock && !hasWeb3) {
        html += '<div class="empty-state"><h3>该记录暂无内容</h3></div>';
      }
      container.innerHTML = html;
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
