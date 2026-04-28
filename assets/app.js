/* ================================================================
   YoungStockDaily · 前端逻辑
   - 首页：从 data/reports.json 渲染列表 + 筛选
   - 详情页：图片点击全屏查看
   ================================================================ */

(function () {
  'use strict';

  // ---------- 工具函数 ----------
  function el(html) {
    const d = document.createElement('div');
    d.innerHTML = html.trim();
    return d.firstChild;
  }

  function escapeHtml(s) {
    return String(s || '').replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  // ---------- 首页：报告列表 ----------
  function initHomepage() {
    const listEl = document.getElementById('report-list');
    if (!listEl) return;

    const searchInput = document.getElementById('search');
    const categorySelect = document.getElementById('category-filter');
    const countEl = document.getElementById('result-count');

    let allReports = [];

    fetch('data/reports.json?_=' + Date.now())
      .then(function (r) {
        if (!r.ok) throw new Error('无法加载 reports.json');
        return r.json();
      })
      .then(function (data) {
        allReports = (data.reports || []).sort(function (a, b) {
          return b.date.localeCompare(a.date);
        });

        // 收集分类
        const cats = Array.from(new Set(allReports.map(function (r) { return r.category; }))).sort();
        cats.forEach(function (c) {
          const opt = document.createElement('option');
          opt.value = c;
          opt.textContent = c;
          categorySelect.appendChild(opt);
        });

        render();
      })
      .catch(function (err) {
        listEl.innerHTML =
          '<div class="empty-state"><h3>😔 加载失败</h3><p>' +
          escapeHtml(err.message) +
          '</p></div>';
      });

    function render() {
      const q = (searchInput.value || '').trim().toLowerCase();
      const cat = categorySelect.value;

      const filtered = allReports.filter(function (r) {
        if (cat && r.category !== cat) return false;
        if (!q) return true;
        const hay = [
          r.date,
          r.title,
          r.summary,
          r.category,
          (r.tickers || []).join(' ')
        ].join(' ').toLowerCase();
        return hay.indexOf(q) !== -1;
      });

      countEl.textContent = '共 ' + filtered.length + ' 篇';

      if (filtered.length === 0) {
        listEl.innerHTML =
          '<div class="empty-state"><h3>🔍 未找到匹配报告</h3><p>换个关键词或分类试试</p></div>';
        return;
      }

      listEl.innerHTML = '';
      filtered.forEach(function (r) {
        const card = el(
          '<a class="report-card" href="reports/' + encodeURIComponent(r.date) + '.html">' +
            (r.image
              ? '<img class="thumb" src="' + r.image + '" alt="' + escapeHtml(r.date) + '" loading="lazy">'
              : '') +
            '<div class="date">' + escapeHtml(r.date) + '</div>' +
            '<span class="category">' + escapeHtml(r.category) + '</span>' +
            '<div class="summary">' + escapeHtml(r.summary || '') + '</div>' +
            (r.tickers && r.tickers.length
              ? '<div class="tickers">' +
                  r.tickers.map(function (t) { return '<span>' + escapeHtml(t) + '</span>'; }).join('') +
                '</div>'
              : '') +
          '</a>'
        );
        listEl.appendChild(card);
      });
    }

    searchInput.addEventListener('input', render);
    categorySelect.addEventListener('change', render);
  }

  // ---------- 详情页：图片 Lightbox ----------
  function initLightbox() {
    const preview = document.querySelector('.preview-image');
    if (!preview) return;

    const img = preview.querySelector('img');
    const lightbox = document.createElement('div');
    lightbox.className = 'lightbox';
    lightbox.innerHTML =
      '<div class="close-tip">点击任意处关闭</div>' +
      '<img src="' + img.src + '" alt="preview full">';
    document.body.appendChild(lightbox);

    preview.addEventListener('click', function () {
      lightbox.classList.add('show');
      document.body.style.overflow = 'hidden';
    });
    lightbox.addEventListener('click', function () {
      lightbox.classList.remove('show');
      document.body.style.overflow = '';
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        lightbox.classList.remove('show');
        document.body.style.overflow = '';
      }
    });
  }

  // ---------- 启动 ----------
  document.addEventListener('DOMContentLoaded', function () {
    initHomepage();
    initLightbox();
  });
})();
