/* ================================================================
   YoungStockDaily · 前端 SPA v6
   - 数据源：data/daily.json 索引 + daily/daily_YYYYMMDD_HHMM.json 全量
   - 三个一级 Tab：今日最新 / 分析日报 / 自选股
   - 分析日报：列表 <-> 详情 原地切换（hash 路由 #daily/<slug>）
   - 去白框 UI：内容直接平铺
   - v6 修复：版本化 ?v= 击穿浏览器缓存；_indexPromise 失败时 console 明显提示
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
      renderDetail(box, latest.slug, { isTodayHeader: true });
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
      let html = '';
      // 页首元信息
      html += '<div class="daily-page-head">';
      if (opts.isTodayHeader) {
        html += '<span class="today-chip">🔥 今日最新</span>';
      }
      html += '<h1>' + escapeHtml(d.date) + ' · 投研日报</h1>';
      html += '<div class="daily-meta">🕒 生成于 ' + escapeHtml(d.generated_at || '') + '</div>';
      html += '</div>';

      // 预览图
      if (d.image) {
        html += '<figure class="hero-image-plain">' +
                  '<img src="' + escapeHtml(d.image) + '" alt="' + escapeHtml(d.date) + ' 异常信号总览" loading="lazy">' +
                  '<figcaption>异常信号总览 · 点击可查看大图</figcaption>' +
                '</figure>';
      }

      // 锚点导航（两部分都有才显示）
      if (d.has_stock && d.has_web3) {
        html += '<div class="daily-anchor-nav">' +
                  '<a href="#stock-section">📈 自选股</a>' +
                  '<a href="#web3-section">🪙 Web3</a>' +
                '</div>';
      }

      // 股票区
      if (d.has_stock) {
        html += '<section class="daily-block" id="stock-section">' +
                  '<h2 class="daily-block-title">📈 自选股实时行情分析</h2>' +
                  '<div class="daily-block-body">' + rewriteRelativePaths(d.stock_body_html || '') + '</div>' +
                '</section>';
      }
      // Web3 区
      if (d.has_web3) {
        html += '<section class="daily-block" id="web3-section">' +
                  '<h2 class="daily-block-title">🪙 Web3 加密日报</h2>' +
                  '<div class="daily-block-body">' + (d.web3_body_html || '') + '</div>' +
                '</section>';
      }
      if (!d.has_stock && !d.has_web3) {
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
    console.log('%c[YSD] SPA v6 booted','color:#d4a849;font-weight:700');
    initTabs();
    initToday();
    initDaily();
    initPortfolio();
    attachLightboxFor(document);
  });
})();
