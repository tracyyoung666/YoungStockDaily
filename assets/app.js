/* ================================================================
   YoungStockDaily · 前端 SPA v4
   - 三个一级 Tab：今日最新 / 分析日报 / 自选股
   - 分析日报：列表 <-> 详情 原地切换，不跳页
   - 详情合并当日股票 + Web3 内容
   ================================================================ */

(function () {
  'use strict';

  // ================= 工具 =================
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
  function rewriteRelativePaths(html) {
    // 详情页里的相对路径（../images/x.png / ../web3/x.html）→ 在首页根目录访问时改为 images/x.png / web3/x.html
    return html
      .replace(/src="\.\.\/(images\/[^"]+)"/g, 'src="$1"')
      .replace(/href="\.\.\/(images\/[^"]+)"/g, 'href="$1"')
      .replace(/href="\.\.\/(web3\/[^"]+)"/g, 'href="$1"')
      .replace(/href="\.\.\/(reports\/[^"]+)"/g, 'href="$1"')
      .replace(/href="\.\.\/portfolio\.html"/g, 'href="#portfolio"')
      .replace(/href="\.\.\/index\.html"/g, 'href="#today"');
  }

  // 从股票详情页 HTML 抽出预览图块 + 正文 <article class="report-content">
  function extractStockParts(htmlStr) {
    const mPreview = htmlStr.match(/<div class="preview-image"[\s\S]*?<\/div>\s*(?=<article|<section|<div class="toc"|$)/i);
    const mArticle = htmlStr.match(/<article[^>]*class="report-content"[^>]*>([\s\S]*?)<\/article>/i);
    let out = '';
    if (mPreview) out += rewriteRelativePaths(mPreview[0]);
    if (mArticle) out += '<article class="report-content">' + rewriteRelativePaths(mArticle[1]) + '</article>';
    return out;
  }
  // 从 Web3 详情页 HTML 抽出 #digest-body
  function extractWeb3Body(htmlStr) {
    const m = htmlStr.match(/<div[^>]*id="digest-body"[^>]*>([\s\S]*?)<\/div>\s*<details/i);
    if (m) return '<div class="report-content">' + m[1] + '</div>';
    // 退化：抓 main 里所有内容
    const m2 = htmlStr.match(/<main[^>]*>([\s\S]*?)<\/main>/i);
    if (m2) return '<div class="report-content">' + m2[1] + '</div>';
    return '';
  }

  // ================= Tab 切换 =================
  function initTabs() {
    const btns = document.querySelectorAll('.tab-btn');
    const panels = document.querySelectorAll('.tab-panel');
    btns.forEach(function (b) {
      b.addEventListener('click', function () {
        activateTab(b.dataset.tab);
        // 清掉详情 hash，回到 Tab 根
        try { history.replaceState(null, '', '#' + b.dataset.tab); } catch (e) {}
        // 切到 daily 时，默认回列表视图
        if (b.dataset.tab === 'daily') showDailyList();
      });
    });
    // 启动路由
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
    // 支持 #daily/2026-04-29
    const parts = h.split('/');
    const tab = parts[0];
    if (['today', 'daily', 'portfolio'].indexOf(tab) === -1) { activateTab('today'); return; }
    activateTab(tab);
    if (tab === 'daily') {
      if (parts[1]) showDailyDetail(parts[1]);
      else showDailyList();
    }
  }

  // ================= Tab 1：今日最新 =================
  function initToday() {
    const box = document.getElementById('today-container');
    if (!box) return;
    Promise.all([
      fetchJSON('data/reports.json').catch(function () { return { reports: [] }; }),
      fetchJSON('data/web3.json').catch(function () { return { digests: [] }; })
    ]).then(function (res) {
      const stocks = (res[0].reports || []).slice().sort(function (a, b) { return b.date.localeCompare(a.date); });
      const web3s  = (res[1].digests || []).slice().sort(function (a, b) { return b.date.localeCompare(a.date); });
      const stock = stocks[0], web3 = web3s[0];
      if (!stock && !web3) {
        box.innerHTML = '<div class="empty-state"><h3>暂无报告</h3></div>';
        return;
      }
      const date = (stock && stock.date) || (web3 && web3.date);
      renderCombinedDetail(box, date, stock, web3, { isTodayHeader: true });
    }).catch(function (err) {
      box.innerHTML = '<div class="empty-state"><h3>😔 加载失败</h3><p>' + escapeHtml(err.message) + '</p></div>';
    });
  }

  // ================= Tab 2：分析日报 =================
  function initDaily() {
    const listEl = document.getElementById('list-daily');
    if (!listEl) return;
    const searchInput = document.getElementById('search-daily');
    const countEl = document.getElementById('count-daily');
    const backBtn = document.getElementById('btn-daily-back');

    let merged = []; // [{date, stock, web3, title, summary, tickers, image}]

    Promise.all([
      fetchJSON('data/reports.json').catch(function () { return { reports: [] }; }),
      fetchJSON('data/web3.json').catch(function () { return { digests: [] }; })
    ]).then(function (res) {
      const byDate = {};
      (res[0].reports || []).forEach(function (r) { byDate[r.date] = byDate[r.date] || {}; byDate[r.date].stock = r; });
      (res[1].digests || []).forEach(function (w) { byDate[w.date] = byDate[w.date] || {}; byDate[w.date].web3 = w; });
      merged = Object.keys(byDate).sort(function (a, b) { return b.localeCompare(a); }).map(function (d) {
        const s = byDate[d].stock, w = byDate[d].web3;
        return {
          date: d,
          stock: s || null,
          web3: w || null,
          title: (s && s.title) || (w && w.title) || d + ' 分析日报',
          summary: [s && s.summary, w && w.summary].filter(Boolean).join(' · '),
          tickers: (s && s.tickers) || [],
          image: (s && s.image) || null,
          hasStock: !!s,
          hasWeb3:  !!w
        };
      });
      window.__DAILY_INDEX__ = merged; // 供详情视图按日期查找
      render();
    }).catch(function (err) {
      listEl.innerHTML = '<div class="empty-state"><h3>😔 加载失败</h3><p>' + escapeHtml(err.message) + '</p></div>';
    });

    function render() {
      const q = (searchInput.value || '').trim().toLowerCase();
      const filtered = merged.filter(function (r) {
        if (!q) return true;
        return [r.date, r.title, r.summary, r.tickers.join(' ')].join(' ').toLowerCase().indexOf(q) !== -1;
      });
      countEl.textContent = '共 ' + filtered.length + ' 篇';
      if (!filtered.length) {
        listEl.innerHTML = '<div class="empty-state"><h3>🔍 未找到</h3></div>';
        return;
      }
      const html = filtered.map(function (r) {
        const badges = (r.hasStock ? '<span class="badge stock">📈 股票</span>' : '') +
                       (r.hasWeb3  ? '<span class="badge web3">🪙 Web3</span>'  : '');
        const tickers = r.tickers.length
          ? '<div class="tickers">' + r.tickers.map(function (t) { return '<span>' + escapeHtml(t) + '</span>'; }).join('') + '</div>'
          : '';
        return '<a class="report-card" href="#daily/' + encodeURIComponent(r.date) + '" data-date="' + escapeHtml(r.date) + '">' +
                 (r.image ? '<img class="thumb" src="' + escapeHtml(r.image) + '" alt="' + escapeHtml(r.date) + '" loading="lazy">' : '') +
                 '<div class="date">' + escapeHtml(r.date) + '</div>' +
                 '<div class="badges">' + badges + '</div>' +
                 '<div class="title">' + escapeHtml(r.title) + '</div>' +
                 '<div class="summary">' + escapeHtml(r.summary || '') + '</div>' +
                 tickers +
               '</a>';
      }).join('');
      listEl.innerHTML = html;
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
  function showDailyDetail(date) {
    const lv = document.getElementById('daily-list-view');
    const dv = document.getElementById('daily-detail-view');
    const body = document.getElementById('daily-detail-body');
    const dateEl = document.getElementById('daily-detail-date');
    if (!lv || !dv || !body) return;
    lv.style.display = 'none';
    dv.style.display = '';
    dateEl.textContent = date;
    body.innerHTML = '<div class="empty-state"><h3>⏳ 加载中</h3></div>';

    // 在索引里找对应的 stock/web3 元数据
    const idx = (window.__DAILY_INDEX__ || []).filter(function (r) { return r.date === date; })[0];
    const tryRender = function () {
      const item = (window.__DAILY_INDEX__ || []).filter(function (r) { return r.date === date; })[0];
      renderCombinedDetail(body, date, item ? item.stock : null, item ? item.web3 : null, { isTodayHeader: false });
    };
    if (idx) { tryRender(); return; }
    // 索引未加载时，等待一下
    let waits = 0;
    const t = setInterval(function () {
      waits += 1;
      if (window.__DAILY_INDEX__ || waits > 20) {
        clearInterval(t);
        tryRender();
      }
    }, 200);
  }

  // ================= 合并详情渲染（今日最新 + 日报详情共用） =================
  function renderCombinedDetail(container, date, stockMeta, web3Meta, opts) {
    opts = opts || {};
    let html = '';
    if (opts.isTodayHeader) {
      html += '<div class="today-header">' +
                '<div class="today-title">' +
                  '<span class="today-chip">🔥 今日最新</span>' +
                  '<h1>' + escapeHtml(date) + ' · 投研日报</h1>' +
                '</div>' +
              '</div>';
    }
    // 📈 股票区
    if (stockMeta) {
      html += '<section class="today-block" id="stock-section">' +
                '<h2 class="today-block-title">📈 自选股实时行情分析</h2>' +
                '<div class="today-block-body" id="slot-stock-' + date + '">' +
                  '<div class="empty-state"><h3>⏳ 加载股票报告…</h3></div>' +
                '</div>' +
              '</section>';
    }
    // 🪙 Web3 区
    if (web3Meta) {
      html += '<section class="today-block" id="web3-section">' +
                '<h2 class="today-block-title">🪙 Web3 加密日报</h2>' +
                '<div class="today-block-body" id="slot-web3-' + date + '">' +
                  '<div class="empty-state"><h3>⏳ 加载 Web3 日报…</h3></div>' +
                '</div>' +
              '</section>';
    }
    if (!stockMeta && !web3Meta) {
      html += '<div class="empty-state"><h3>该日期暂无内容</h3></div>';
    }
    container.innerHTML = html;

    // 异步填充
    if (stockMeta) {
      fetchText('reports/' + encodeURIComponent(date) + '.html').then(function (s) {
        const slot = document.getElementById('slot-stock-' + date);
        if (!slot) return;
        const parts = extractStockParts(s);
        slot.innerHTML = parts || ('<div class="report-content"><h3>' + escapeHtml(stockMeta.title || '') + '</h3><p>' + escapeHtml(stockMeta.summary || '') + '</p></div>');
        attachLightboxFor(slot);
      }).catch(function (err) {
        const slot = document.getElementById('slot-stock-' + date);
        if (slot) slot.innerHTML = '<div class="empty-state"><h3>😔 股票报告加载失败</h3><p>' + escapeHtml(err.message) + '</p></div>';
      });
    }
    if (web3Meta) {
      fetchText('web3/' + encodeURIComponent(date) + '.html').then(function (s) {
        const slot = document.getElementById('slot-web3-' + date);
        if (!slot) return;
        const body = extractWeb3Body(s);
        slot.innerHTML = body || ('<div class="report-content"><h3>Web3 日报</h3><p>' + escapeHtml(web3Meta.summary || '') + '</p></div>');
      }).catch(function (err) {
        const slot = document.getElementById('slot-web3-' + date);
        if (slot) slot.innerHTML = '<div class="empty-state"><h3>😔 Web3 加载失败</h3><p>' + escapeHtml(err.message) + '</p></div>';
      });
    }
  }

  // ================= Tab 3：自选股（完整清单原地展示） =================
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

  // ================= 启动 =================
  document.addEventListener('DOMContentLoaded', function () {
    initTabs();
    initToday();
    initDaily();
    initPortfolio();
    attachLightboxFor(document);
  });
})();
