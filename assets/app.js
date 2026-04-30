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
