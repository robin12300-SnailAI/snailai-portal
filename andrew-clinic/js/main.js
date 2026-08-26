/**
 * SKIN CANCER LASER CENTRE — Main Interactions
 * Version: 2.0.0
 *
 * Features:
 * - Page loading fade-out
 * - Navbar scroll state (glass blur)
 * - Mobile drawer navigation
 * - Scroll progress bar
 * - Reveal-on-scroll animations (IntersectionObserver)
 * - Counter number animation
 * - Back-to-top button
 */

(function() {
  'use strict';

  /* ====================================================
   * V2.2 — Prototype-only click guard
   * Disable all mailto: links and form submits (no email client pop-up).
   * Snackbar feedback instead. Drop this entire block to restore live behaviour.
   * ==================================================== */
  function initPrototypeGuard() {
    // 1. Block any mailto link at capture phase so click never reaches the browser
    document.addEventListener('click', (e) => {
      const link = e.target.closest && e.target.closest('a[href^="mailto:"], a[href^="tel:"], a[href^="javascript:void(0)"], a[href="#book"], a[data-prototype-cta], button[data-prototype-cta]');
      if (link) {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        showPrototypeToast(link.textContent.trim() || 'Booking');
        return false;
      }
    }, true); // capture phase

    // 2. Block any form submission (especially mailto: forms)
    document.addEventListener('submit', (e) => {
      e.preventDefault();
      e.stopPropagation();
      e.stopImmediatePropagation();
      showPrototypeToast('Enquiry');
      return false;
    }, true);

    // 3. Strip mailto: ctas any time JS wires them up post-DOM
    document.querySelectorAll('a[href^="mailto:"]').forEach(a => {
      a.setAttribute('data-prototype-cta', '');
      a.setAttribute('aria-disabled', 'true');
      a.removeAttribute('href');
      a.style.cursor = 'not-allowed';
    });

    // 4. Disable submit buttons so they cannot trigger submit
    document.querySelectorAll('form button[type="submit"], form input[type="submit"]').forEach(b => {
      b.setAttribute('data-prototype-cta', '');
      b.setAttribute('aria-disabled', 'true');
      b.style.cursor = 'not-allowed';
    });
  }

  // Tiny toast (no DOM deps, no layout shift)
  let _toastTimer = null;
  function showPrototypeToast(actionLabel) {
    let el = document.getElementById('prototype-toast');
    if (!el) {
      el = document.createElement('div');
      el.id = 'prototype-toast';
      el.setAttribute('role', 'status');
      el.setAttribute('aria-live', 'polite');
      el.style.cssText = `
        position: fixed; bottom: 28px; left: 50%; transform: translateX(-50%) translateY(20px);
        background: rgba(20,18,14,0.96); color: #c79323; border: 1px solid #c79323;
        padding: 12px 22px; border-radius: 30px; font-family: 'Inter',sans-serif;
        font-size: 0.84rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase;
        z-index: 99999; opacity: 0; pointer-events: none;
        transition: opacity 0.25s ease, transform 0.25s ease;
        backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
        box-shadow: 0 8px 24px rgba(0,0,0,0.6);`;
      el.innerHTML = '<span style="margin-right:8px;">●</span><span id="prototype-toast-text"></span>';
      document.body.appendChild(el);
    }
    document.getElementById('prototype-toast-text').textContent = `PROTOTYPE — ${actionLabel} is not active yet`;
    clearTimeout(_toastTimer);
    requestAnimationFrame(() => {
      el.style.opacity = '1';
      el.style.transform = 'translateX(-50%) translateY(0)';
    });
    _toastTimer = setTimeout(() => {
      el.style.opacity = '0';
      el.style.transform = 'translateX(-50%) translateY(20px)';
    }, 1800);
  }

  /* --- Page Loading --- */
  function initPageLoading() {
    const loader = document.getElementById('pageLoading');
    if (!loader) return;
    window.addEventListener('load', () => {
      setTimeout(() => loader.classList.add('hidden'), 250);
    });
    // Safety: never trap user on loader
    setTimeout(() => loader.classList.add('hidden'), 3000);
  }

  /* --- Navbar Scroll State --- */
  function initNavbar() {
    const navbar = document.getElementById('navbar');
    if (!navbar) return;
    const onScroll = () => {
      navbar.classList.toggle('scrolled', window.scrollY > 40);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }

  /* --- Mobile Drawer --- */
  function initDrawer() {
    const toggle = document.getElementById('navToggle');
    const links = document.getElementById('navLinks');
    if (!toggle || !links) return;

    function close() {
      toggle.classList.remove('active');
      links.classList.remove('open');
      document.body.classList.remove('nav-open');
      toggle.setAttribute('aria-expanded', 'false');
    }

    toggle.addEventListener('click', () => {
      const isOpen = links.classList.toggle('open');
      toggle.classList.toggle('active', isOpen);
      document.body.classList.toggle('nav-open', isOpen);
      toggle.setAttribute('aria-expanded', String(isOpen));
    });

    // Close on link click
    links.querySelectorAll('a').forEach(a => a.addEventListener('click', close));

    // Close on outside click
    document.addEventListener('click', (e) => {
      if (document.body.classList.contains('nav-open') &&
          !links.contains(e.target) && !toggle.contains(e.target)) {
        close();
      }
    });

    // Close on Escape
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') close();
    });
  }

  /* --- Scroll Progress --- */
  function initScrollProgress() {
    const progress = document.getElementById('scrollProgress');
    if (!progress) return;
    const bar = progress.querySelector('span');
    if (!bar) return;
    window.addEventListener('scroll', () => {
      const docH = document.documentElement.scrollHeight - window.innerHeight;
      const pct = docH > 0 ? (window.scrollY / docH) * 100 : 0;
      bar.style.width = pct + '%';
    }, { passive: true });
  }

  /* --- Reveal on Scroll --- */
  function initReveal() {
    const items = document.querySelectorAll('.reveal');
    if (!items.length) return;

    if (!('IntersectionObserver' in window)) {
      items.forEach(el => el.classList.add('revealed'));
      return;
    }

    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('revealed');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });

    items.forEach(el => observer.observe(el));

    // Fallback: ensure everything becomes visible after 2.5s
    // (covers screenshot tools, headless browsers, print, etc.)
    setTimeout(() => {
      document.querySelectorAll('.reveal:not(.revealed)').forEach(el => {
        el.classList.add('revealed');
      });
    }, 2500);
  }

  /* --- Counter Animation --- */
  function initCounters() {
    const counters = document.querySelectorAll('[data-counter]');
    if (!counters.length) return;

    function animate(el) {
      const target = parseInt(el.getAttribute('data-counter'), 10) || 0;
      const duration = 1600;
      const start = performance.now();
      function tick(now) {
        const p = Math.min((now - start) / duration, 1);
        const eased = 1 - Math.pow(1 - p, 3);
        const val = Math.round(target * eased);
        el.textContent = val.toLocaleString('en-US') + '+';
        if (p < 1) requestAnimationFrame(tick);
      }
      requestAnimationFrame(tick);
    }

    if (!('IntersectionObserver' in window)) {
      counters.forEach(el => {
        el.textContent = (parseInt(el.getAttribute('data-counter'), 10) || 0).toLocaleString('en-US') + '+';
      });
      return;
    }

    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          animate(entry.target);
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.5 });

    counters.forEach(el => observer.observe(el));
  }

  /* --- Back to Top --- */
  function initBackToTop() {
    const btn = document.getElementById('backToTop');
    if (!btn) return;
    window.addEventListener('scroll', () => {
      btn.style.opacity = window.scrollY > 600 ? '1' : '0';
      btn.style.pointerEvents = window.scrollY > 600 ? 'auto' : 'none';
    }, { passive: true });
    btn.addEventListener('click', () => {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }

  /* --- Smooth anchor links (accounting fixed nav) --- */
  function initAnchors() {
    document.querySelectorAll('a[href^="#"]:not([href="#"])').forEach(a => {
      a.addEventListener('click', (e) => {
        const id = a.getAttribute('href').slice(1);
        const target = document.getElementById(id);
        if (target) {
          e.preventDefault();
          const y = target.getBoundingClientRect().top + window.scrollY - 84;
          window.scrollTo({ top: y, behavior: 'smooth' });
        }
      });
    });
  }

  /* --- Init all --- */
  function init() {
    initPrototypeGuard();   // V2.2 — disable mailto/form before any other handler binds
    initPageLoading();
    initNavbar();
    initDrawer();
    initScrollProgress();
    initReveal();
    initCounters();
    initBackToTop();
    initAnchors();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
