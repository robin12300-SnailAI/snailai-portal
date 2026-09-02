/* ============================================================
   Snail AI — Main Site Shared JS (V4.5.0)
   Nav burger · FAQ accordion · contact form · footer version
   V4.5.0: Lucide icon set (emoji->SVG) · scroll-reveal motion · footer ribbon
   ============================================================ */
(function () {
  'use strict';

  var SNAIL_ICONS = {"🌐":"<circle cx=\"12\" cy=\"12\" r=\"10\" /> <path d=\"M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20\" /> <path d=\"M2 12h20\" />","⚙":"<path d=\"M9.671 4.136a2.34 2.34 0 0 1 4.659 0 2.34 2.34 0 0 0 3.319 1.915 2.34 2.34 0 0 1 2.33 4.033 2.34 2.34 0 0 0 0 3.831 2.34 2.34 0 0 1-2.33 4.033 2.34 2.34 0 0 0-3.319 1.915 2.34 2.34 0 0 1-4.659 0 2.34 2.34 0 0 0-3.32-1.915 2.34 2.34 0 0 1-2.33-4.033 2.34 2.34 0 0 0 0-3.831A2.34 2.34 0 0 1 6.35 6.051a2.34 2.34 0 0 0 3.319-1.915\" /> <circle cx=\"12\" cy=\"12\" r=\"3\" />","🚀":"<path d=\"M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5\" /> <path d=\"M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09\" /> <path d=\"M9 12a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.4 22.4 0 0 1-4 2z\" /> <path d=\"M9 12H4s.55-3.03 2-4c1.62-1.08 5 .05 5 .05\" />","🩺":"<path d=\"M11 2v2\" /> <path d=\"M5 2v2\" /> <path d=\"M5 3H4a2 2 0 0 0-2 2v4a6 6 0 0 0 12 0V5a2 2 0 0 0-2-2h-1\" /> <path d=\"M8 15a6 6 0 0 0 12 0v-3\" /> <circle cx=\"20\" cy=\"10\" r=\"2\" />","🏗":"<path d=\"M10 10V5a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v5\" /> <path d=\"M14 6a6 6 0 0 1 6 6v3\" /> <path d=\"M4 15v-3a6 6 0 0 1 6-6\" /> <rect x=\"2\" y=\"15\" width=\"20\" height=\"4\" rx=\"1\" />","💼":"<path d=\"M16 20V4a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16\" /> <rect width=\"20\" height=\"14\" x=\"2\" y=\"6\" rx=\"2\" />","🏢":"<path d=\"M10 12h4\" /> <path d=\"M10 8h4\" /> <path d=\"M14 21v-3a2 2 0 0 0-4 0v3\" /> <path d=\"M6 10H4a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-2\" /> <path d=\"M6 21V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v16\" />","📞":"<path d=\"M13.832 16.568a1 1 0 0 0 1.213-.303l.355-.465A2 2 0 0 1 17 15h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2A18 18 0 0 1 2 4a2 2 0 0 1 2-2h3a2 2 0 0 1 2 2v3a2 2 0 0 1-.8 1.6l-.468.351a1 1 0 0 0-.292 1.233 14 14 0 0 0 6.392 6.384\" />","📋":"<rect width=\"8\" height=\"4\" x=\"8\" y=\"2\" rx=\"1\" ry=\"1\" /> <path d=\"M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2\" /> <path d=\"M12 11h4\" /> <path d=\"M12 16h4\" /> <path d=\"M8 11h.01\" /> <path d=\"M8 16h.01\" />","📝":"<path d=\"M16 4h2a2 2 0 0 1 2 2v2\" /> <path d=\"M21.34 15.664a1 1 0 1 0-3.004-3.004l-5.01 5.012a2 2 0 0 0-.506.854l-.837 2.87a.5.5 0 0 0 .62.62l2.87-.837a2 2 0 0 0 .854-.506z\" /> <path d=\"M8 22H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2\" /> <rect x=\"8\" y=\"2\" width=\"8\" height=\"4\" rx=\"1\" />","✅":"<circle cx=\"12\" cy=\"12\" r=\"10\" /> <path d=\"m16 9-5.5 5.5L8 12\" />","📊":"<path d=\"M3 3v16a2 2 0 0 0 2 2h16\" /> <path d=\"M18 17V9\" /> <path d=\"M13 17V5\" /> <path d=\"M8 17v-3\" />","⚖":"<path d=\"M12 3v18\" /> <path d=\"m19 8 3 8a5 5 0 0 1-6 0zV7\" /> <path d=\"M3 7h1a17 17 0 0 0 8-2 17 17 0 0 0 8 2h1\" /> <path d=\"m5 8 3 8a5 5 0 0 1-6 0zV7\" /> <path d=\"M7 21h10\" />","🛡":"<path d=\"M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z\" /> <path d=\"m9 12 2 2 4-4\" />","🎯":"<circle cx=\"12\" cy=\"12\" r=\"10\" /> <circle cx=\"12\" cy=\"12\" r=\"6\" /> <circle cx=\"12\" cy=\"12\" r=\"2\" />","🏥":"<path d=\"M12 7v4\" /> <path d=\"M14 21v-3a2 2 0 0 0-4 0v3\" /> <path d=\"M14 9h-4\" /> <path d=\"M18 11h2a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-9a2 2 0 0 1 2-2h2\" /> <path d=\"M18 21V5a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16\" />","📅":"<path d=\"M8 2v3\" /> <path d=\"M16 2v3\" /> <rect x=\"3\" y=\"3\" width=\"18\" height=\"18\" rx=\"2\" /> <path d=\"M3 9h18\" /> <path d=\"M8 13h.01\" /> <path d=\"M12 13h.01\" /> <path d=\"M16 13h.01\" /> <path d=\"M8 17h.01\" /> <path d=\"M12 17h.01\" /> <path d=\"M16 17h.01\" />","📨":"<path d=\"m22 7-8.991 5.727a2 2 0 0 1-2.009 0L2 7\" /> <rect x=\"2\" y=\"4\" width=\"20\" height=\"16\" rx=\"2\" />","📍":"<path d=\"M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0\" /> <circle cx=\"12\" cy=\"10\" r=\"3\" />","🔌":"<path d=\"M12 22v-5\" /> <path d=\"M15 8V2\" /> <path d=\"M17 8a1 1 0 0 1 1 1v4a4 4 0 0 1-4 4h-4a4 4 0 0 1-4-4V9a1 1 0 0 1 1-1z\" /> <path d=\"M9 8V2\" />","🧾":"<path d=\"M12 17V7\" /> <path d=\"M16 8h-6a2 2 0 0 0 0 4h4a2 2 0 0 1 0 4H8\" /> <path d=\"M4 3a1 1 0 0 1 1-1 1.3 1.3 0 0 1 .7.2l.933.6a1.3 1.3 0 0 0 1.4 0l.934-.6a1.3 1.3 0 0 1 1.4 0l.933.6a1.3 1.3 0 0 0 1.4 0l.933-.6a1.3 1.3 0 0 1 1.4 0l.934.6a1.3 1.3 0 0 0 1.4 0l.933-.6A1.3 1.3 0 0 1 19 2a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1 1.3 1.3 0 0 1-.7-.2l-.933-.6a1.3 1.3 0 0 0-1.4 0l-.934.6a1.3 1.3 0 0 1-1.4 0l-.933-.6a1.3 1.3 0 0 0-1.4 0l-.933.6a1.3 1.3 0 0 1-1.4 0l-.934-.6a1.3 1.3 0 0 0-1.4 0l-.933.6a1.3 1.3 0 0 1-.7.2 1 1 0 0 1-1-1z\" />","🏘":"<path d=\"M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8\" /> <path d=\"M3 10a2 2 0 0 1 .709-1.528l7-6a2 2 0 0 1 2.582 0l7 6A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z\" />","📥":"<polyline points=\"22 12 16 12 14 15 10 15 8 12 2 12\" /> <path d=\"M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z\" />","💬":"<path d=\"M2.992 16.342a2 2 0 0 1 .094 1.167l-1.065 3.29a1 1 0 0 0 1.236 1.168l3.413-.998a2 2 0 0 1 1.099.092 10 10 0 1 0-4.777-4.719\" />","📷":"<path d=\"M13.997 4a2 2 0 0 1 1.76 1.05l.486.9A2 2 0 0 0 18.003 7H20a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2h1.997a2 2 0 0 0 1.759-1.048l.489-.904A2 2 0 0 1 10.004 4z\" /> <circle cx=\"12\" cy=\"13\" r=\"3\" />","🔍":"<path d=\"m21 21-4.34-4.34\" /> <circle cx=\"11\" cy=\"11\" r=\"8\" />","🔧":"<path d=\"M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.106-3.105c.32-.322.863-.22.983.218a6 6 0 0 1-8.259 7.057l-7.91 7.91a1 1 0 0 1-2.999-3l7.91-7.91a6 6 0 0 1 7.057-8.259c.438.12.54.662.219.984z\" />","✉":"<path d=\"m22 7-8.991 5.727a2 2 0 0 1-2.009 0L2 7\" /> <rect x=\"2\" y=\"4\" width=\"20\" height=\"16\" rx=\"2\" />","🤝":"<path d=\"m11 17 2 2a1 1 0 1 0 3-3\" /> <path d=\"m14 14 2.5 2.5a1 1 0 1 0 3-3l-3.88-3.88a3 3 0 0 0-4.24 0l-.88.88a1 1 0 1 1-3-3l2.81-2.81a5.79 5.79 0 0 1 7.06-.87l.47.28a2 2 0 0 0 1.42.25L21 4\" /> <path d=\"m21 3 1 11h-2\" /> <path d=\"M3 3 2 14l6.5 6.5a1 1 0 1 0 3-3\" /> <path d=\"M3 4h8\" />","📄":"<path d=\"M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2z\" /> <path d=\"M14 2v5a1 1 0 0 0 1 1h5\" /> <path d=\"M10 9H8\" /> <path d=\"M16 13H8\" /> <path d=\"M16 17H8\" />","✍":"<path d=\"M13 21h8\" /> <path d=\"M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z\" />","🔁":"<path d=\"m17 2 4 4-4 4\" /> <path d=\"M3 11v-1a4 4 0 0 1 4-4h14\" /> <path d=\"m7 22-4-4 4-4\" /> <path d=\"M21 13v1a4 4 0 0 1-4 4H3\" />","🧠":"<path d=\"M12 18V5\" /> <path d=\"M15 13a4.17 4.17 0 0 1-3-4 4.17 4.17 0 0 1-3 4\" /> <path d=\"M17.598 6.5A3 3 0 1 0 12 5a3 3 0 1 0-5.598 1.5\" /> <path d=\"M17.997 5.125a4 4 0 0 1 2.526 5.77\" /> <path d=\"M18 18a4 4 0 0 0 2-7.464\" /> <path d=\"M19.967 17.483A4 4 0 1 1 12 18a4 4 0 1 1-7.967-.517\" /> <path d=\"M6 18a4 4 0 0 1-2-7.464\" /> <path d=\"M6.003 5.125a4 4 0 0 0-2.526 5.77\" />","📣":"<path d=\"M11 6a13 13 0 0 0 8.4-2.8A1 1 0 0 1 21 4v12a1 1 0 0 1-1.6.8A13 13 0 0 0 11 14H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2z\" /> <path d=\"M6 14a12 12 0 0 0 2.4 7.2 2 2 0 0 0 3.2-2.4A8 8 0 0 1 10 14\" /> <path d=\"M8 6v8\" />","🗄":"<ellipse cx=\"12\" cy=\"5\" rx=\"9\" ry=\"3\" /> <path d=\"M3 5V19A9 3 0 0 0 21 19V5\" /> <path d=\"M3 12A9 3 0 0 0 21 12\" />","⚗":"<path d=\"M14 2v6a2 2 0 0 0 .245.96l5.51 10.08A2 2 0 0 1 18 22H6a2 2 0 0 1-1.755-2.96l5.51-10.08A2 2 0 0 0 10 8V2\" /> <path d=\"M6.453 15h11.094\" /> <path d=\"M8.5 2h7\" />"};

  /* ----- Mobile nav burger ----- */
  function initNav() {
    var burger = document.querySelector('.nav-burger');
    var links = document.querySelector('.nav-links');
    if (!burger || !links) return;
    burger.addEventListener('click', function () {
      links.classList.toggle('open');
      burger.setAttribute('aria-expanded', links.classList.contains('open') ? 'true' : 'false');
    });
    // close menu when a link is tapped（并复位 aria-expanded）
    links.addEventListener('click', function (e) {
      if (e.target.tagName === 'A') {
        links.classList.remove('open');
        burger.setAttribute('aria-expanded', 'false');
      }
    });
    // 当前页导航高亮（Gate A 无障碍：aria-current="page"）
    var path = location.pathname.replace(/\/$/, '') || '/';
    links.querySelectorAll('a').forEach(function (a) {
      var href = (a.getAttribute('href') || '').replace(/\/$/, '') || '/';
      if (href === path) a.setAttribute('aria-current', 'page');
    });
  }

  /* ----- FAQ accordion（Gate A：同步 aria-expanded）----- */
  function initFaq() {
    document.querySelectorAll('.faq-q').forEach(function (q) {
      q.addEventListener('click', function () {
        var item = q.parentElement;
        var ans = item.querySelector('.faq-a');
        var wasOpen = item.classList.contains('open');
        // close siblings (single-open pattern)
        item.parentElement.querySelectorAll('.faq-item.open').forEach(function (o) {
          o.classList.remove('open');
          var oa = o.querySelector('.faq-a');
          if (oa) oa.style.maxHeight = null;
          var oq = o.querySelector('.faq-q');
          if (oq) oq.setAttribute('aria-expanded', 'false');
        });
        if (!wasOpen) {
          item.classList.add('open');
          ans.style.maxHeight = ans.scrollHeight + 'px';
          q.setAttribute('aria-expanded', 'true');
        }
      });
    });
  }

  /* ----- Contact form ----- */
  function initContactForm() {
    var form = document.getElementById('contact-form');
    if (!form) return;
    var status = document.getElementById('form-status');
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      status.className = 'form-status';
      status.textContent = 'Sending…';
      var payload = {
        name: form.name.value.trim(),
        email: form.email.value.trim(),
        company: form.company.value.trim(),
        phone: form.phone.value.trim(),
        message: form.message.value.trim(),
      };
      if (!payload.name || !payload.email || !payload.message) {
        status.className = 'form-status err';
        status.textContent = 'Please fill in your name, work email and message.';
        return;
      }
      // Turnstile token (widget renders if site key present)
      var tw = document.getElementById('cf-turnstile');
      if (tw && window.turnstile) {
        payload.turnstile_token = (window.turnstile.getResponse && window.turnstile.getResponse()) || '';
      }
      fetch('/api/contact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
        .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
        .then(function (res) {
          if (res.ok) {
            status.className = 'form-status ok';
            status.textContent = 'Thank you — your message has been received. We will reply within two business days.';
            form.reset();
            if (window.turnstile) window.turnstile.reset();
            trackEvent('contact_form_submitted', '');
          } else {
            status.className = 'form-status err';
            status.textContent = res.j.error || 'Something went wrong. Please try again or email us directly.';
          }
        })
        .catch(function () {
          status.className = 'form-status err';
          status.textContent = 'Network error. Please try again or email robin@snailai.ai.';
        });
    });
  }

  /* ----- Footer version stamp ----- */
  function initVersion() {
    fetch('/version.json').then(function (r) { return r.json(); }).then(function (v) {
      document.querySelectorAll('[data-site-version]').forEach(function (el) {
        el.textContent = 'V' + v.version + ' · ' + (v.last_updated || v.release_date || '');
      });
    }).catch(function () {});
  }

  /* ----- Conversion event tracking (brief §18) ----- */
  function trackEvent(event, detail) {
    try {
      var vid = null;
      try { vid = localStorage.getItem('snailai_vid'); } catch (e) {}
      fetch('/api/track/event', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          event: event,
          path: location.pathname,
          visitor_id: vid,
          detail: detail || '',
        }),
        keepalive: true,
      });
    } catch (e) { /* tracking must never break the page */ }
  }

  function initTracking() {
    // 页面级事件：进入具体案例页时记录一次（原来挂在点击分支里，语义是错的）
    if (/^\/case-studies\/.+/.test(location.pathname)) {
      trackEvent('case_study_viewed', location.pathname);
    }

    // phone / email / academy / consultation clicks（委托）
    document.addEventListener('click', function (e) {
      var a = e.target.closest && e.target.closest('a[href]');
      if (!a) return;
      var href = a.getAttribute('href') || '';
      var path = a.pathname || '';
      if (href.indexOf('tel:') === 0) trackEvent('phone_click', href.slice(4));
      else if (href.indexOf('mailto:') === 0) trackEvent('email_click', href.slice(7));
      else if (a.hostname === 'academy.snailai.ai') trackEvent('academy_link_clicked', href);
      // 「Book a Consultation」等指向 /contact/ 的 CTA
      else if (a.hostname === location.hostname && /^\/contact\/?$/.test(path)) {
        trackEvent('consultation_requested', location.pathname);
      }
    });
  }


  /* ----- V4.5.0: Lucide icon replacement（emoji -> 统一线性 SVG，全站生效） ----- */
  function initIcons() {
    document.querySelectorAll('.card-icon').forEach(function (el) {
      if (el.classList.contains('has-svg')) return;
      var key = (el.textContent || '').replace(/\uFE0F/g, '').trim();
      var inner = SNAIL_ICONS[key];
      if (!inner) return;
      el.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
        inner + '</svg>';
      el.classList.add('has-svg');
    });
  }

  /* ----- V4.5.0: scroll-reveal（Cloudflare 式入场；自动挂载全站常见区块） ----- */
  function initReveal() {
    var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduced || !('IntersectionObserver' in window)) return;
    // 自动为常见区块挂 data-reveal（已有则跳过）
    var groups = [
      '.section-head', '.problem-list li', '.card-grid > .card', '.card-grid + .card',
      '.step', '.why-item', '.faq-item', '.cta-band .container > *', '.assessment-box'
    ];
    groups.forEach(function (sel) {
      document.querySelectorAll(sel).forEach(function (el) {
        if (!el.hasAttribute('data-reveal')) el.setAttribute('data-reveal', '');
      });
    });
    // 组内错峰：同一容器里的兄弟元素依次入场
    document.querySelectorAll('[data-reveal]').forEach(function (el) {
      var parent = el.parentElement;
      if (!parent) return;
      var sibs = Array.prototype.filter.call(parent.children, function (c) {
        return c.hasAttribute && c.hasAttribute('data-reveal');
      });
      var idx = sibs.indexOf(el);
      if (idx > 0) el.style.transitionDelay = Math.min(idx * 80, 480) + 'ms';
    });
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('revealed');
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -6% 0px' });
    document.querySelectorAll('[data-reveal]').forEach(function (el) { io.observe(el); });
  }

  /* ----- V4.5.0: footer ribbon（全站页脚顶部冷色彩带，JS 注入 markup） ----- */
  function initFooterRibbon() {
    var footer = document.querySelector('.footer');
    if (!footer || footer.querySelector('.footer-ribbon')) return;
    var band = document.createElement('div');
    band.className = 'footer-ribbon';
    band.setAttribute('aria-hidden', 'true');
    band.innerHTML = '<div class="ribbon-layer"></div><div class="ribbon-layer"></div>';
    footer.insertBefore(band, footer.firstChild);
  }

  /* ----- V4.6.0: 太阳日珥喷射（从英雄区彩带周期性喷出绚烂光弧） ----- */
  var PROM_COLORS = [
    ['#FDB022', '#FF8C00'], // 金→深橙
    ['#FFD700', '#FF7A3D'], // 亮金→橙
    ['#FFC107', '#FF6B1A'], // 琥珀金→橘红
    ['#FFE066', '#FDB022'], // 浅金→金
    ['#FFB347', '#FF6347'], // 暖金→珊瑚橙
    ['#FFD700', '#FFA500'], // 纯金→橙
    ['#FDB022', '#FFE066']  // 金→浅金
  ];
  var PROM_SHAPES = ['prominence-flame', 'prominence-arc', 'prominence-jet', 'prominence-spray'];

  function spawnProminence() {
    var container = document.querySelector('.prominence-container');
    if (!container) return;
    var el = document.createElement('div');
    var shape = PROM_SHAPES[Math.floor(Math.random() * PROM_SHAPES.length)];
    var colors = PROM_COLORS[Math.floor(Math.random() * PROM_COLORS.length)];
    el.className = 'prominence ' + shape;
    /* 随机参数 — V4.6.1: 高度 ×4（原来 120~300 → 480~1200） */
    var px = 6 + Math.random() * 88;          /* 水平位置 6%~94% */
    var pw = 80 + Math.random() * 200;         /* 宽度 80~280px */
    var ph = 480 + Math.random() * 720;        /* 高度 480~1200px */
    var pr = (Math.random() - 0.5) * 32;      /* 旋转 -16°~+16° */
    var sway = (Math.random() - 0.5) * 12;    /* 摆动 ±6° */
    var pb = 12 + Math.random() * 16;         /* blur 12~28px */
    var pd = 2.4 + Math.random() * 1.4;        /* 持续 2.4~3.8s */
    el.style.setProperty('--px', px + '%');
    el.style.setProperty('--pw', pw + 'px');
    el.style.setProperty('--ph', ph + 'px');
    el.style.setProperty('--pr', pr + 'deg');
    el.style.setProperty('--sway', sway + 'deg');
    el.style.setProperty('--pb', pb + 'px');
    el.style.setProperty('--pd', pd + 's');
    el.style.setProperty('--pc', colors[0]);
    el.style.setProperty('--pc2', colors[1]);
    container.appendChild(el);
    /* 动画结束后移除 */
    el.addEventListener('animationend', function () { el.remove(); });
  }

  function initProminence() {
    var container = document.querySelector('.hero .prominence-container');
    if (!container) return;
    var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduced) return;
    /* 首次喷射延迟 800ms，之后每 ~2.5s 喷射一次（错峰让重叠感更强） */
    setTimeout(spawnProminence, 800);
    setTimeout(spawnProminence, 2200);
    setInterval(spawnProminence, 2500);
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.documentElement.classList.add('js');
    initNav();
    initFaq();
    initContactForm();
    initVersion();
    initTracking();
    initIcons();
    initFooterRibbon();
    initProminence();
    initReveal();
  });
})();
