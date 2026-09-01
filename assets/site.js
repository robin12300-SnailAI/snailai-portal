/* ============================================================
   Snail AI — Main Site Shared JS (V3.0.0)
   Nav burger · FAQ accordion · contact form · footer version
   ============================================================ */
(function () {
  'use strict';

  /* ----- Mobile nav burger ----- */
  function initNav() {
    var burger = document.querySelector('.nav-burger');
    var links = document.querySelector('.nav-links');
    if (!burger || !links) return;
    burger.addEventListener('click', function () {
      links.classList.toggle('open');
      burger.setAttribute('aria-expanded', links.classList.contains('open') ? 'true' : 'false');
    });
    // close menu when a link is tapped
    links.addEventListener('click', function (e) {
      if (e.target.tagName === 'A') links.classList.remove('open');
    });
  }

  /* ----- FAQ accordion ----- */
  function initFaq() {
    document.querySelectorAll('.faq-q').forEach(function (q) {
      q.addEventListener('click', function () {
        var item = q.parentElement;
        var ans = item.querySelector('.faq-a');
        var wasOpen = item.classList.contains('open');
        // close siblings (single-open pattern)
        item.parentElement.querySelectorAll('.faq-item.open').forEach(function (o) {
          o.classList.remove('open');
          o.querySelector('.faq-a').style.maxHeight = null;
        });
        if (!wasOpen) {
          item.classList.add('open');
          ans.style.maxHeight = ans.scrollHeight + 'px';
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

  document.addEventListener('DOMContentLoaded', function () {
    initNav();
    initFaq();
    initContactForm();
    initVersion();
    initTracking();
  });
})();
