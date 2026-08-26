/**
 * SKIN CANCER LASER CENTRE — Bilingual Switch Engine
 * Version: 1.0.0
 *
 * Implementation:
 * - body.lang-en → English visible, Chinese hidden
 * - body.lang-zh → Chinese visible, English hidden
 * - Default: English (no body class)
 * - localStorage key: "sclc-lang" persists user choice
 * - Toggle button: .lang-toggle with EN/ZH buttons
 */

(function() {
  'use strict';

  const STORAGE_KEY = 'sclc-lang';
  const LANG_EN = 'en';
  const LANG_ZH = 'zh';

  function getCurrentLang() {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === LANG_EN || stored === LANG_ZH) return stored;
    return LANG_EN; // default
  }

  function setLang(lang) {
    const body = document.body;
    body.classList.remove('lang-en', 'lang-zh');

    if (lang === LANG_ZH) {
      body.classList.add('lang-zh');
    }
    // English is default — no class needed, but add for explicitness
    // body.classList.add('lang-en'); // optional, CSS handles both

    localStorage.setItem(STORAGE_KEY, lang);
    updateToggleButtons(lang);
    document.documentElement.lang = lang === LANG_ZH ? 'zh' : 'en';
  }

  function updateToggleButtons(lang) {
    const buttons = document.querySelectorAll('.lang-toggle button');
    buttons.forEach(btn => {
      const btnLang = btn.dataset.lang;
      btn.classList.toggle('active', btnLang === lang);
    });
  }

  function init() {
    const lang = getCurrentLang();
    setLang(lang);

    // Bind toggle buttons
    document.querySelectorAll('.lang-toggle button').forEach(btn => {
      btn.addEventListener('click', function() {
        const newLang = this.dataset.lang;
        setLang(newLang);
      });
    });
  }

  // Initialize on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
