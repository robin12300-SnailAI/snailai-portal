/**
 * SKIN CANCER LASER CENTRE — Bilingual Switch Engine
 * Version: 2.0.0 — Text-replacement engine
 *
 * How it works:
 * - Every translatable element carries data-en / data-zh attributes
 * - On switch, elements WITHOUT element children get textContent replaced
 *   (elements with child nodes are skipped — their children handle themselves)
 * - body.lang-en / body.lang-zh classes toggle CSS styling hooks
 * - localStorage key "sclc-lang" persists user choice
 * - Buttons: .lang-toggle [data-lang="en|zh"]
 */

(function() {
  'use strict';

  const STORAGE_KEY = 'sclc-lang';
  const LANG_EN = 'en';
  const LANG_ZH = 'zh';

  function getCurrentLang() {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === LANG_EN || stored === LANG_ZH) return stored;
    // Default to English — this is an English-speaking clinic.
    // Chinese only activates when user explicitly clicks the toggle.
    return LANG_EN;
  }

  function applyLanguage(lang) {
    const isZh = lang === LANG_ZH;
    document.body.classList.toggle('lang-zh', isZh);
    document.body.classList.toggle('lang-en', !isZh);
    document.documentElement.lang = isZh ? 'zh' : 'en';

    // Replace text on leaf elements only
    const nodes = document.querySelectorAll('[data-en]');
    nodes.forEach(el => {
      const hasElementChild = el.children.length > 0;
      if (hasElementChild) return; // let inner elements handle themselves
      const text = isZh ? el.getAttribute('data-zh') : el.getAttribute('data-en');
      if (text !== null && text !== '') el.textContent = text;
    });

    localStorage.setItem(STORAGE_KEY, lang);
    updateToggleButtons(lang);
  }

  function updateToggleButtons(lang) {
    document.querySelectorAll('.lang-toggle button').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.lang === lang);
    });
  }

  function init() {
    // Apply saved / detected language
    applyLanguage(getCurrentLang());

    // Bind all toggle buttons (nav desktop + mobile drawer)
    document.querySelectorAll('.lang-toggle button').forEach(btn => {
      btn.addEventListener('click', function() {
        applyLanguage(this.dataset.lang);
      });
    });

    // Allow dynamically added content to be translated
    window.SCLC_i18n = { apply: applyLanguage, current: getCurrentLang };
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
