/**
 * SKIN CANCER LASER CENTRE — Main JS
 * Version: 1.0.0
 */

(function() {
  'use strict';

  // --- Navbar scroll effect ---
  function initNavbar() {
    const navbar = document.querySelector('.navbar');
    if (!navbar) return;

    window.addEventListener('scroll', function() {
      navbar.classList.toggle('scrolled', window.scrollY > 10);
    });
  }

  // --- Mobile nav toggle ---
  function initMobileNav() {
    const toggle = document.querySelector('.nav-toggle');
    const navLinks = document.querySelector('.nav-links');
    if (!toggle || !navLinks) return;

    toggle.addEventListener('click', function() {
      navLinks.classList.toggle('open');
      const expanded = toggle.getAttribute('aria-expanded') === 'true';
      toggle.setAttribute('aria-expanded', !expanded);
    });

    // Close nav when clicking a link
    navLinks.querySelectorAll('a').forEach(link => {
      link.addEventListener('click', () => {
        navLinks.classList.remove('open');
        toggle.setAttribute('aria-expanded', 'false');
      });
    });
  }

  // --- Page loading animation ---
  function initPageLoad() {
    const loader = document.querySelector('.page-loading');
    if (!loader) return;
    window.addEventListener('load', function() {
      setTimeout(() => loader.classList.add('hidden'), 300);
    });
  }

  // --- Smooth scroll for anchor links ---
  function initSmoothScroll() {
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
      anchor.addEventListener('click', function(e) {
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
          e.preventDefault();
          target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      });
    });
  }

  // --- Active nav link ---
  function initActiveNav() {
    const currentPath = window.location.pathname;
    document.querySelectorAll('.nav-links a').forEach(link => {
      const href = link.getAttribute('href');
      if (href && (currentPath.endsWith(href) || (href === 'index.html' && (currentPath.endsWith('/') || currentPath.endsWith('/andrew-clinic/'))))) {
        link.style.color = 'var(--color-gold)';
      }
    });
  }

  // Init all
  function init() {
    initNavbar();
    initMobileNav();
    initPageLoad();
    initSmoothScroll();
    initActiveNav();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
