/**
 * SKIN CANCER LASER CENTRE — V3.0 Light Edition
 * Main Interactions
 * Version: 3.0.0
 *
 * Features:
 * - Page loading fade-out
 * - Navbar scroll state
 * - Mobile drawer (legacy)
 * - Scroll progress bar
 * - Reveal-on-scroll animations
 * - Prototype click guard (mailto intercept, light toast)
 * - FAQ accordion
 * - Testimonials carousel (auto + dots)
 * - Instagram horizontal carousel (prev/next)
 * - Back-to-top
 */

(function() {
  'use strict';

  /* ====================================================
   * V3.0 — Prototype click guard (light theme)
   * Disable all mailto: links and form submits.
   * Snackbar feedback. Drop the init call to restore live behaviour.
   * ==================================================== */
  function initPrototypeGuard() {
    document.addEventListener('click', (e) => {
      const link = e.target.closest && e.target.closest(
        'a[href^="mailto:"], a[href^="tel:"], a[href^="javascript:void(0)"], a[href="#book"], a[data-prototype-cta], button[data-prototype-cta]'
      );
      if (link) {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        showPrototypeToast(link.textContent.trim() || 'Booking');
        return false;
      }
    }, true);

    document.addEventListener('submit', (e) => {
      e.preventDefault();
      e.stopPropagation();
      e.stopImmediatePropagation();
      showPrototypeToast('Enquiry');
      return false;
    }, true);

    document.querySelectorAll('a[href^="mailto:"]').forEach(a => {
      a.setAttribute('data-prototype-cta', '');
      a.setAttribute('aria-disabled', 'true');
      a.removeAttribute('href');
      a.style.cursor = 'not-allowed';
    });

    document.querySelectorAll('form button[type="submit"], form input[type="submit"]').forEach(b => {
      b.setAttribute('data-prototype-cta', '');
      b.setAttribute('aria-disabled', 'true');
      b.style.cursor = 'not-allowed';
    });
  }

  let _toastTimer = null;
  function showPrototypeToast(actionLabel) {
    let el = document.getElementById('prototype-toast');
    if (!el) {
      el = document.createElement('div');
      el.id = 'prototype-toast';
      el.className = 'prototype-toast';
      el.setAttribute('role', 'status');
      el.setAttribute('aria-live', 'polite');
      el.innerHTML = '<span class="dot">●</span><span id="prototype-toast-text"></span>';
      document.body.appendChild(el);
    }
    document.getElementById('prototype-toast-text').textContent = `PROTOTYPE — ${actionLabel} is not active yet`;
    clearTimeout(_toastTimer);
    requestAnimationFrame(() => el.classList.add('is-visible'));
    _toastTimer = setTimeout(() => el.classList.remove('is-visible'), 1800);
  }

  /* --- Page Loading --- */
  function initPageLoading() {
    const loader = document.getElementById('pageLoading');
    if (!loader) return;
    window.addEventListener('load', () => {
      setTimeout(() => loader.classList.add('hidden'), 250);
    });
  }

  /* --- Navbar scroll state --- */
  function initNavbar() {
    const nav = document.getElementById('navbar');
    if (!nav) return;
    const onScroll = () => {
      if (window.scrollY > 12) nav.classList.add('is-scrolled');
      else nav.classList.remove('is-scrolled');
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }

  /* --- Mobile drawer (legacy) --- */
  function initDrawer() {
    const burger = document.getElementById('navBurger');
    const links = document.getElementById('navLinks');
    if (!burger || !links) return;
    burger.addEventListener('click', () => {
      burger.classList.toggle('active');
      links.classList.toggle('is-open');
    });
    links.querySelectorAll('a').forEach(a => {
      a.addEventListener('click', () => {
        burger.classList.remove('active');
        links.classList.remove('is-open');
      });
    });
  }

  /* --- Scroll progress bar --- */
  function initScrollProgress() {
    const bar = document.querySelector('.scroll-progress span');
    if (!bar) return;
    window.addEventListener('scroll', () => {
      const scrolled = window.scrollY;
      const height = document.documentElement.scrollHeight - window.innerHeight;
      const pct = height > 0 ? (scrolled / height) * 100 : 0;
      bar.style.width = pct + '%';
    }, { passive: true });
  }

  /* --- Reveal on scroll --- */
  function initReveal() {
    const items = document.querySelectorAll('.reveal');
    if (!items.length) return;

    // Force-reveal fallback: 5s after load everything visible even if observer never fires
    // (covers full-page screenshot tools / Puppeteer / older browsers)
    const forceRevealAll = () => {
      items.forEach(el => el.classList.add('is-revealed'));
    };
    setTimeout(forceRevealAll, 5000);
    window.addEventListener('load', () => setTimeout(forceRevealAll, 3500));

    if (!('IntersectionObserver' in window)) {
      items.forEach(el => el.classList.add('is-revealed'));
      return;
    }

    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-revealed');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.05, rootMargin: '0px 0px 0px 0px' });

    items.forEach(el => observer.observe(el));
  }

  /* --- Back to top --- */
  function initBackToTop() {
    const btn = document.getElementById('backToTop');
    if (!btn) return;
    window.addEventListener('scroll', () => {
      if (window.scrollY > 600) btn.classList.add('is-visible');
      else btn.classList.remove('is-visible');
    }, { passive: true });
    btn.addEventListener('click', () => {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }

  /* ====================================================
   * V3.0 — FAQ accordion
   * ==================================================== */
  function initFAQ() {
    const items = document.querySelectorAll('.faq-item');
    if (!items.length) return;
    items.forEach(item => {
      const btn = item.querySelector('.faq-question');
      if (!btn) return;
      // Ensure initial aria-expanded matches DOM state
      btn.setAttribute('aria-expanded', item.classList.contains('is-open') ? 'true' : 'false');
      btn.addEventListener('click', () => {
        const isOpen = item.classList.contains('is-open');
        // Close all others (single-open mode)
        items.forEach(other => {
          if (other !== item) {
            other.classList.remove('is-open');
            const otherBtn = other.querySelector('.faq-question');
            if (otherBtn) otherBtn.setAttribute('aria-expanded', 'false');
          }
        });
        if (isOpen) {
          item.classList.remove('is-open');
          btn.setAttribute('aria-expanded', 'false');
        } else {
          item.classList.add('is-open');
          btn.setAttribute('aria-expanded', 'true');
        }
      });
    });
  }

  /* ====================================================
   * V3.0 — Testimonials carousel
   * Auto-advance every 5s, dots click, click on slide pauses
   * ==================================================== */
  function initTestimonials() {
    const slides = document.querySelectorAll('.testimonial-slide');
    const dots = document.querySelectorAll('.testimonial-dots button');
    if (slides.length < 2) return;

    let idx = 0;
    let timer = null;
    const delay = 5500;

    function goTo(n) {
      slides[idx].classList.remove('is-active');
      if (dots[idx]) dots[idx].classList.remove('is-active');
      idx = (n + slides.length) % slides.length;
      slides[idx].classList.add('is-active');
      if (dots[idx]) dots[idx].classList.add('is-active');
    }
    function start() {
      stop();
      timer = setInterval(() => goTo(idx + 1), delay);
    }
    function stop() {
      if (timer) { clearInterval(timer); timer = null; }
    }

    dots.forEach((d, i) => {
      d.addEventListener('click', () => {
        goTo(i);
        start();
      });
    });

    // Pause on hover
    const viewport = document.querySelector('.testimonial-viewport');
    if (viewport) {
      viewport.addEventListener('mouseenter', stop);
      viewport.addEventListener('mouseleave', start);
    }

    start();
  }

  /* ====================================================
   * V3.0 — Instagram horizontal carousel
   * 4 cards visible (desktop), 2 (tablet), 1 (mobile)
   * ==================================================== */
  function initInstagram() {
    const track = document.getElementById('instaTrack');
    const prev = document.getElementById('instaPrev');
    const next = document.getElementById('instaNext');
    if (!track || !prev || !next) return;

    const cards = track.querySelectorAll('.insta-card');
    if (cards.length < 2) return;

    let pos = 0;
    const gap = 16;

    function getVisibleCount() {
      const w = window.innerWidth;
      if (w < 640) return 1;
      if (w < 1024) return 2;
      return 4;
    }

    function getCardWidth() {
      const visible = getVisibleCount();
      const containerWidth = track.parentElement.clientWidth;
      return (containerWidth - (visible - 1) * gap) / visible;
    }

    function maxPos() {
      return Math.max(0, cards.length - getVisibleCount());
    }

    function update() {
      const w = getCardWidth();
      cards.forEach(c => c.style.flex = `0 0 ${w}px`);
      const offset = pos * (w + gap);
      track.style.transform = `translateX(-${offset}px)`;
      prev.disabled = pos <= 0;
      next.disabled = pos >= maxPos();
    }

    prev.addEventListener('click', () => {
      if (pos > 0) { pos--; update(); }
    });
    next.addEventListener('click', () => {
      if (pos < maxPos()) { pos++; update(); }
    });
    window.addEventListener('resize', () => { update(); });

    update();
  }

  /* ====================================================
   * V3.1 — Services horizontal carousel
   * One instance per .services-carousel (4 categories).
   * 4 cards visible (desktop), 2 (tablet), 1.2 (mobile).
   * Prev/next black square buttons + dot indicators.
   * ==================================================== */
  function initServicesCarousel() {
    const carousels = document.querySelectorAll('.services-carousel[data-carousel]');
    if (!carousels.length) return;

    carousels.forEach((root) => {
      const track   = root.querySelector('.services-track');
      const prev    = root.querySelector('.carousel-prev');
      const next    = root.querySelector('.carousel-next');
      const dots    = root.querySelectorAll('.carousel-dots button');
      const cards   = root.querySelectorAll('.service-card-img');
      if (!track || !prev || !next || !cards.length) return;

      let pos = 0;

      function getVisibleCount() {
        const w = window.innerWidth;
        if (w < 768) return 1;     // 1.2 cards visible (78% width set in CSS)
        if (w < 1024) return 2;
        return 4;
      }

      function getGap() {
        // gap = 18px on desktop, 18px on tablet (matches CSS), 0 on mobile (CSS uses 0)
        return window.innerWidth < 768 ? 0 : 18;
      }

      function getCardWidth() {
        const vw = root.querySelector('.services-viewport').clientWidth;
        const visible = getVisibleCount();
        const gapTotal = (visible - 1) * getGap();
        return (vw - gapTotal) / visible;
      }

      function maxPos() {
        return Math.max(0, cards.length - getVisibleCount());
      }

      function update() {
        const w = getCardWidth();
        const gap = getGap();
        // Card flex-basis is already set by CSS; just set width for precision
        cards.forEach(c => { c.style.flex = `0 0 ${w}px`; });
        const offset = pos * (w + gap);
        track.style.transform = `translateX(-${offset}px)`;
        prev.disabled = pos <= 0;
        next.disabled = pos >= maxPos();
        if (dots.length) {
          dots.forEach((d, i) => d.classList.toggle('is-active', i === pos));
        }
      }

      prev.addEventListener('click', () => {
        if (pos > 0) { pos--; update(); }
      });
      next.addEventListener('click', () => {
        if (pos < maxPos()) { pos++; update(); }
      });
      dots.forEach((d, i) => {
        d.addEventListener('click', () => {
          if (i <= maxPos()) { pos = i; update(); }
        });
      });

      // Touch swipe support
      let touchStartX = 0, touchDeltaX = 0, swiping = false;
      const viewport = root.querySelector('.services-viewport');
      if (viewport) {
        viewport.addEventListener('touchstart', (e) => {
          touchStartX = e.touches[0].clientX;
          swiping = true;
        }, { passive: true });
        viewport.addEventListener('touchmove', (e) => {
          if (!swiping) return;
          touchDeltaX = e.touches[0].clientX - touchStartX;
        }, { passive: true });
        viewport.addEventListener('touchend', () => {
          if (!swiping) return;
          swiping = false;
          if (Math.abs(touchDeltaX) > 50) {
            if (touchDeltaX < 0 && pos < maxPos()) pos++;
            else if (touchDeltaX > 0 && pos > 0) pos--;
            update();
          }
          touchDeltaX = 0;
        });
      }

      window.addEventListener('resize', update);
      // Initial update after a tick (so flex-basis in CSS has applied)
      setTimeout(update, 50);
    });
  }

  /* ====================================================
   * V3.2 — Version badge
   * Fetch version.json and populate #navVersion + footer pill
   * ==================================================== */
  function initVersionBadge() {
    fetch('version.json')
      .then(r => r.json())
      .then(data => {
        const v = 'V' + data.version;
        const navPill = document.getElementById('navVersion');
        if (navPill) navPill.textContent = v;
        document.querySelectorAll('.footer-version-pill').forEach(el => {
          el.textContent = v;
        });
      })
      .catch(() => {
        const navPill = document.getElementById('navVersion');
        if (navPill) navPill.textContent = '';
      });
  }

  /* ====================================================
   * Init
   * ==================================================== */
  function init() {
    initPrototypeGuard();
    initPageLoading();
    initNavbar();
    initDrawer();
    initScrollProgress();
    initReveal();
    initBackToTop();
    initFAQ();
    initTestimonials();
    initInstagram();
    initServicesCarousel();
    initVersionBadge();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
