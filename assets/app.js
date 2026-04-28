/* ================================================================
   YoungStockDaily · 前端逻辑 v2
   - 首页：Tab 切换（股票 / Web3 / 自选股）+ 独立索引渲染
   - 详情页：图片 Lightbox
   ================================================================ */

(function () {
  'use strict';

  // ---------- 工具 ----------
  function el(html) {
    const d = document.createElement('div');
    d.innerHTML = html.trim();
    return d.firstChild;
  }
  function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function fetchJSON(url) {
    return fetch(url + (url.indexOf('?') === -1 ? '?' : '&') + '_=' + Date.now())
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status + ' ' + url); return r.json(); });
  }

  // ---------- Tab 切换 ----------
  function initTabs() {
    const btns = document.querySelectorAll('.tab-btn');
    const panels = document.querySelectorAll('.tab-panel');
    if (!btns.length) return;
    btns.forEach(function (b) {
      b.addEventListener('click', function () {
        const t = b.dataset.tab;
        btns.forEach(function (x) { x.classList.toggle('active', x === b); });
        panels.forEach(function (p) { p.classList.toggle('active', p.dataset.panel === t); });
        try { history.replaceState(null, '', '#' + t); } catch (e) {}
      });
    });
    // 启动时根据 hash 定位 Tab
    const h = (location.hash || '').replace('#', '');
    if (h) {
      const btn = document.querySelector('.tab-btn[data-tab="' + h + '"]');
      if (btn) btn.click();
    }
  }

  // ---------- 股票报告列表 ----------
  function initStockList() {
    const listEl = document.getElementById('list-stock');
    if (!listEl) return;
    const searchInput = document.getElementById('search-stock');
    const categorySelect = document.getElementById('category-stock');
    const countEl = document.getElementById('count-stock');

    let all = [];

    fetchJSON('data/reports.json').then(function (data) {
      all = (data.reports || []).sort(function (a, b) { return b.date.localeCompare(a.date); });
      const cats = Array.from(new Set(all.map(function (r) { return r.category; }))).sort();
      cats.forEach(function (c) {
        const opt = document.createElement('option');
        opt.value = c; opt.textContent = c;
        categorySelect.appendChild(opt);
      });
      render();
    }).catch(function (err) {
      listEl.innerHTML = '<div class="empty-state"><h3>😔 加载失败</h3><p>' + escapeHtml(err.message) + '</p></div>';
    });

    function render() {
      const q = (searchInput.value || '').trim().toLowerCase();
      const cat = categorySelect.value;
      const filtered = all.filter(function (r) {
        if (cat && r.category !== cat) return false;
        if (!q) return true;
        const hay = [r.date, r.title, r.summary, r.category, (r.tickers || []).join(' ')].join(' ').toLowerCase();
        return hay.indexOf(q) !== -1;
      });
      countEl.textContent = '共 ' + filtered.length + ' 篇';
      if (!filtered.length) {
        listEl.innerHTML = '<div class="empty-state"><h3>🔍 未找到</h3><p>换个关键词试试</p></div>';
        return;
      }
      listEl.innerHTML = '';
      filtered.forEach(function (r) {
        const card = el(
          '<a class="report-card" href="reports/' + encodeURIComponent(r.date) + '.html">' +
            (r.image ? '<img class="thumb" src="' + escapeHtml(r.image) + '" alt="' + escapeHtml(r.date) + '" loading="lazy">' : '') +
            '<div class="date">' + escapeHtml(r.date) + '</div>' +
            '<span class="category">' + escapeHtml(r.category) + '</span>' +
            '<div class="title">' + escapeHtml(r.title || '') + '</div>' +
            '<div class="summary">' + escapeHtml(r.summary || '') + '</div>' +
            (r.tickers && r.tickers.length
              ? '<div class="tickers">' + r.tickers.map(function (t) { return '<span>' + escapeHtml(t) + '</span>'; }).join('') + '</div>'
              : '') +
          '</a>'
        );
        listEl.appendChild(card);
      });
    }
    searchInput.addEventListener('input', render);
    categorySelect.addEventListener('change', render);
  }

  // ---------- Web3 日报列表 ----------
  function initWeb3List() {
    const listEl = document.getElementById('list-web3');
    if (!listEl) return;
    const searchInput = document.getElementById('search-web3');
    const countEl = document.getElementById('count-web3');
    let all = [];

    fetchJSON('data/web3.json').then(function (data) {
      all = (data.digests || []).sort(function (a, b) { return b.date.localeCompare(a.date); });
      render();
    }).catch(function (err) {
      listEl.innerHTML = '<div class="empty-state"><h3>😔 加载失败</h3><p>' + escapeHtml(err.message) + '</p></div>';
    });

    function render() {
      const q = (searchInput.value || '').trim().toLowerCase();
      const filtered = all.filter(function (r) {
        if (!q) return true;
        return [r.date, r.title, r.summary].join(' ').toLowerCase().indexOf(q) !== -1;
      });
      countEl.textContent = '共 ' + filtered.length + ' 篇';
      if (!filtered.length) {
        listEl.innerHTML = '<div class="empty-state"><h3>🔍 未找到</h3><p>换个关键词试试</p></div>';
        return;
      }
      listEl.innerHTML = '';
      filtered.forEach(function (r) {
        const card = el(
          '<a class="report-card web3" href="web3/' + encodeURIComponent(r.date) + '.html">' +
            '<div class="web3-badge">🪙 Web3</div>' +
            '<div class="date">' + escapeHtml(r.date) + '</div>' +
            '<div class="title">' + escapeHtml(r.title || 'Web3 日报') + '</div>' +
            '<div class="summary">' + escapeHtml(r.summary || '') + '</div>' +
          '</a>'
        );
        listEl.appendChild(card);
      });
    }
    searchInput.addEventListener('input', render);
  }

  // ---------- 自选股预览（首页） ----------
  function initPortfolioPreview() {
    const box = document.getElementById('portfolio-preview');
    if (!box) return;
    fetchJSON('data/portfolio.json').then(function (data) {
      const cats = data.categories || {};
      const html = Object.keys(cats).map(function (k) {
        const c = cats[k];
        const chips = (c.stocks || []).map(function (s) {
          return '<span class="stock-chip"><b>' + escapeHtml(s.symbol) + '</b> · ' + escapeHtml(s.name) + '</span>';
        }).join('');
        return '<div class="portfolio-cat">' +
                '<h3>📁 ' + escapeHtml(k) + ' <small>' + escapeHtml(c.description || '') + '</small></h3>' +
                '<div class="stock-chips">' + chips + '</div>' +
               '</div>';
      }).join('');
      box.innerHTML = html || '<div class="empty-state"><h3>暂无自选股</h3></div>';
    }).catch(function (err) {
      box.innerHTML = '<div class="empty-state"><h3>😔 加载失败</h3><p>' + escapeHtml(err.message) + '</p></div>';
    });
  }

  // ---------- 独立 portfolio.html 页的详细渲染 ----------
  function initPortfolioPage() {
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

  // ---------- 详情页 Lightbox ----------
  function initLightbox() {
    const preview = document.querySelector('.preview-image');
    if (!preview) return;
    const img = preview.querySelector('img');
    if (!img) return;
    const lightbox = document.createElement('div');
    lightbox.className = 'lightbox';
    lightbox.innerHTML = '<div class="close-tip">点击任意处关闭</div><img src="' + img.src + '" alt="preview full">';
    document.body.appendChild(lightbox);
    preview.addEventListener('click', function () {
      lightbox.classList.add('show'); document.body.style.overflow = 'hidden';
    });
    lightbox.addEventListener('click', function () {
      lightbox.classList.remove('show'); document.body.style.overflow = '';
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { lightbox.classList.remove('show'); document.body.style.overflow = ''; }
    });
  }

  // ---------- 启动 ----------
  document.addEventListener('DOMContentLoaded', function () {
    initTabs();
    initStockList();
    initWeb3List();
    initPortfolioPreview();
    initPortfolioPage();
    initLightbox();
  });
})();
