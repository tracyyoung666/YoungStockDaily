/* ================================================================
   YoungStockDaily · 前端逻辑 v3
   - 首页：4 Tab（今日最新 / 股票 / Web3 / 自选股），默认"今日最新"
   - 今日最新：合并显示当日股票报告 + Web3 日报 + 顶部锚点导航
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
  function fetchText(url) {
    return fetch(url + (url.indexOf('?') === -1 ? '?' : '&') + '_=' + Date.now())
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status + ' ' + url); return r.text(); });
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
    if (h && ['today', 'stock', 'web3', 'portfolio'].indexOf(h) !== -1) {
      const btn = document.querySelector('.tab-btn[data-tab="' + h + '"]');
      if (btn) btn.click();
    }
  }

  // ---------- 今日最新（合并页） ----------
  function initToday() {
    const box = document.getElementById('today-container');
    if (!box) return;

    Promise.all([
      fetchJSON('data/reports.json').catch(function () { return { reports: [] }; }),
      fetchJSON('data/web3.json').catch(function () { return { digests: [] }; })
    ]).then(function (results) {
      const stocks = (results[0].reports || []).slice().sort(function (a, b) { return b.date.localeCompare(a.date); });
      const web3s  = (results[1].digests || []).slice().sort(function (a, b) { return b.date.localeCompare(a.date); });

      const latestStock = stocks[0] || null;
      const latestWeb3  = web3s[0]  || null;

      if (!latestStock && !latestWeb3) {
        box.innerHTML = '<div class="empty-state"><h3>暂无报告</h3><p>定时任务尚未生成任何报告，请稍后再来</p></div>';
        return;
      }

      // 选用较新的一个作为"今日"标签；实际上两份内容都展示
      const headerDate = (latestStock && latestStock.date) || (latestWeb3 && latestWeb3.date) || '';

      // 头部信息 + 锚点导航
      let html = '';
      html += '<div class="today-header">' +
                '<div class="today-title">' +
                  '<span class="today-chip">🔥 今日最新</span>' +
                  '<h1>' + escapeHtml(headerDate) + ' · 投研日报</h1>' +
                '</div>' +
                '<div class="today-anchors">' +
                  (latestStock ? '<a href="#stock-section">📈 股票行情</a>' : '') +
                  (latestWeb3  ? '<a href="#web3-section">🪙 Web3 日报</a>' : '') +
                  '<a href="#portfolio-section">⭐ 自选股</a>' +
                '</div>' +
              '</div>';

      // === 股票板块 ===
      if (latestStock) {
        html += '<section class="today-block" id="stock-section">' +
                  '<h2 class="today-block-title">📈 自选股实时行情分析</h2>' +
                  '<div class="today-block-body" id="today-stock-body">' +
                    '<div class="empty-state"><h3>⏳ 加载股票报告…</h3></div>' +
                  '</div>' +
                  '<div class="today-block-foot">' +
                    '<a class="btn-link" href="reports/' + encodeURIComponent(latestStock.date) + '.html">打开完整股票报告 →</a>' +
                  '</div>' +
                '</section>';
      }

      // === Web3 板块 ===
      if (latestWeb3) {
        html += '<section class="today-block" id="web3-section">' +
                  '<h2 class="today-block-title">🪙 Web3 加密日报</h2>' +
                  '<div class="today-block-body" id="today-web3-body">' +
                    '<div class="empty-state"><h3>⏳ 加载 Web3 日报…</h3></div>' +
                  '</div>' +
                  '<div class="today-block-foot">' +
                    '<a class="btn-link" href="web3/' + encodeURIComponent(latestWeb3.date) + '.html">打开完整 Web3 日报 →</a>' +
                  '</div>' +
                '</section>';
      }

      // === 自选股速览 ===
      html += '<section class="today-block" id="portfolio-section">' +
                '<h2 class="today-block-title">⭐ 自选股速览</h2>' +
                '<div class="today-block-body" id="today-portfolio-body">' +
                  '<div class="empty-state"><h3>⏳ 加载自选股…</h3></div>' +
                '</div>' +
                '<div class="today-block-foot">' +
                  '<a class="btn-link" href="portfolio.html">打开完整清单 →</a>' +
                '</div>' +
              '</section>';

      box.innerHTML = html;

      // 加载实际内容（并行）
      if (latestStock) loadStockBody(latestStock);
      if (latestWeb3)  loadWeb3Body(latestWeb3);
      loadPortfolioBody(document.getElementById('today-portfolio-body'));

    }).catch(function (err) {
      box.innerHTML = '<div class="empty-state"><h3>😔 加载失败</h3><p>' + escapeHtml(err.message) + '</p></div>';
    });
  }

  function loadStockBody(meta) {
    const container = document.getElementById('today-stock-body');
    if (!container) return;
    fetchText('reports/' + encodeURIComponent(meta.date) + '.html').then(function (htmlStr) {
      // 抽出 <article class="report-content">...</article>
      const mArticle = htmlStr.match(/<article[^>]*class="report-content"[^>]*>([\s\S]*?)<\/article>/i);
      const mPreview = htmlStr.match(/<div class="preview-image"[\s\S]*?<\/div>/i);
      let bodyHtml = '';
      if (mPreview) {
        // 修正图片路径：详情页里 ../images/xx.png，到首页需要 images/xx.png
        bodyHtml += mPreview[0].replace(/src="\.\.\/(images\/[^"]+)"/g, 'src="$1"');
      }
      if (mArticle) {
        // 修正内部链接：详情页里 ../web3/...、../images/... 需要改成 web3/...、images/...
        let article = mArticle[1];
        article = article.replace(/href="\.\.\/(web3\/[^"]+)"/g, 'href="$1"');
        article = article.replace(/src="\.\.\/(images\/[^"]+)"/g, 'src="$1"');
        bodyHtml += '<article class="report-content">' + article + '</article>';
      } else {
        // 退化为摘要
        bodyHtml += '<div class="report-content"><h3>' + escapeHtml(meta.title || '') + '</h3><p>' + escapeHtml(meta.summary || '') + '</p></div>';
      }
      container.innerHTML = bodyHtml;
      // 对新插入的预览图挂 lightbox
      attachLightboxFor(container);
    }).catch(function (err) {
      container.innerHTML = '<div class="empty-state"><h3>😔 加载失败</h3><p>' + escapeHtml(err.message) + '</p></div>';
    });
  }

  function loadWeb3Body(meta) {
    const container = document.getElementById('today-web3-body');
    if (!container) return;
    fetchText('web3/' + encodeURIComponent(meta.date) + '.html').then(function (htmlStr) {
      const m = htmlStr.match(/<div[^>]*id="digest-body"[^>]*>([\s\S]*?)<\/div>\s*<details/i);
      if (m) {
        container.innerHTML = '<div class="report-content">' + m[1] + '</div>';
      } else {
        container.innerHTML = '<div class="report-content"><h3>' + escapeHtml(meta.title || 'Web3 日报') + '</h3><p>' + escapeHtml(meta.summary || '') + '</p></div>';
      }
    }).catch(function (err) {
      container.innerHTML = '<div class="empty-state"><h3>😔 加载失败</h3><p>' + escapeHtml(err.message) + '</p></div>';
    });
  }

  function loadPortfolioBody(container) {
    if (!container) return;
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
      container.innerHTML = html || '<div class="empty-state"><h3>暂无自选股</h3></div>';
    }).catch(function (err) {
      container.innerHTML = '<div class="empty-state"><h3>😔 加载失败</h3><p>' + escapeHtml(err.message) + '</p></div>';
    });
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

  // ---------- 自选股速览（Tab 3） ----------
  function initPortfolioPreview() {
    const box = document.getElementById('portfolio-preview');
    if (!box) return;
    loadPortfolioBody(box);
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

  // ---------- Lightbox ----------
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
    const previews = (root || document).querySelectorAll('.preview-image');
    if (!previews.length) return;
    const lightbox = buildLightboxOnce();
    const lightImg = lightbox.querySelector('img');
    previews.forEach(function (preview) {
      if (preview.dataset.lbBound) return;
      preview.dataset.lbBound = '1';
      const img = preview.querySelector('img');
      if (!img) return;
      preview.addEventListener('click', function () {
        lightImg.src = img.src;
        lightbox.classList.add('show'); document.body.style.overflow = 'hidden';
      });
    });
  }
  function initLightbox() { attachLightboxFor(document); }

  // ---------- 启动 ----------
  document.addEventListener('DOMContentLoaded', function () {
    initTabs();
    initToday();
    initStockList();
    initWeb3List();
    initPortfolioPreview();
    initPortfolioPage();
    initLightbox();
  });
})();
