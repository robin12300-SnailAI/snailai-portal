/* ============================================================
 * 蜗牛AI 学员门户 — 公共导航 & 页面工具（中英双语版）
 * 每个门户页面在 <body> 顶部放 <div id="nav-root"></div>，
 * 在末尾引入本文件并调用 renderNav('online') 等。
 * 导航链接前缀会根据当前页面深度自动计算，
 * 所以无论页面在根目录还是子目录都能正确跳转。
 * 双语：本文件提供 setLang(lang)，切换时自动重渲染导航/公告/底部，
 * 并派发 'langchange' 事件，页面可据此重渲染动态内容。
 * ============================================================ */

/* 语言状态 */
const LANG_KEY = "snailai-lang";
let curLang = localStorage.getItem(LANG_KEY) || "zh";

/* 门户版本号（与仓库根目录 version.json 保持一致，每次发布同步 bump）*/
const PORTAL_VERSION = "1.0.1";

/* 计算从当前页面回到门户根目录的相对前缀 */
const _APP_SRC = (document.currentScript && document.currentScript.src) || "";
function navPrefix() {
  try {
    if (_APP_SRC) {
      const u = new URL(_APP_SRC);
      const parts = u.pathname.split("/").filter(Boolean);
      const ai = parts.lastIndexOf("assets");
      if (ai > 0) {
        const rootSegs = parts.slice(0, ai);
        const curSegs = location.pathname.split("/").filter(Boolean);
        let depth = curSegs.length - rootSegs.length;
        if (depth > 0 && curSegs[curSegs.length - 1].indexOf(".") > -1) depth -= 1;
        return depth > 0 ? "../".repeat(depth) : "./";
      }
    }
  } catch (e) {}
  return "./";
}

const NAV_ITEMS = [
  { key: "dashboard", label: "我的学堂",    labelEn: "My Portal",       file: "welcome.html" },
  { key: "online",    label: "AI 应用线上班", labelEn: "AI Online",     file: "AI 应用线上班/" },
  { key: "offline",   label: "AI 财富线下班", labelEn: "AI Wealth",     file: "AI 财富线下班/" },
  { key: "checklist", label: "AI 能力清单",  labelEn: "Capability List", file: "AI 能力清单/" },
  { key: "roadmap",   label: "路演直播 PPT", labelEn: "Pitch & PPT",    file: "路演直播 PPT/" }
];

function navLabel(it) { return curLang === "en" ? (it.labelEn || it.label) : it.label; }

let _activeNav = null;

function renderNav(active) {
  _activeNav = active || _activeNav;
  const root = document.getElementById("nav-root");
  if (!root) return;
  const p = navPrefix();
  const user = getCurrentUser();
  let links = NAV_ITEMS.map(it =>
    `<a href="${p}${it.file}" class="${it.key === _activeNav ? "active" : ""}">${navLabel(it)}</a>`
  ).join("");

  let right;
  if (user) {
    const suffix = user.role === "instructor" ? (curLang === "en" ? " · Lead Instructor" : " · 总讲师")
                  : user.role === "ta" ? (curLang === "en" ? " · TA" : " · 助教") : "";
    right = `
      <div class="userbox">
        <span class="uname">${user.name}${suffix}</span>
        <button class="btn btn-ghost btn-sm" onclick="logout()">${curLang === "en" ? "Log out" : "退出"}</button>
      </div>`;
  } else {
    right = `<a class="btn btn-primary btn-sm" href="${p}login.html">${curLang === "en" ? "Student Login" : "学员登录"}</a>`;
  }

  root.innerHTML = `
    <nav class="topnav">
      <a class="brand" href="${p}welcome.html">
        <span class="logo">🐌</span><span>${curLang === "en" ? "SnailAI · Student Portal" : "蜗牛AI · 学员学堂"}</span>
      </a>
      <div class="navlinks">${links}</div>
      ${right}
    </nav>`;
}

/* 公告（你后续改这里的内容即可全站生效；留空则不显示）*/
const ANNOUNCEMENT = {
  zh: "📢 学员学堂试运行中：课件与能力清单正在陆续上传，敬请期待。",
  en: "📢 Student Portal trial run: courseware and capability checklist are being uploaded. Stay tuned."
};
function renderAnnounce() {
  if (!ANNOUNCEMENT) return;
  const el = document.getElementById("announce-root");
  if (el) el.innerHTML = `<div class="announce">${curLang === "en" ? ANNOUNCEMENT.en : ANNOUNCEMENT.zh}</div>`;
}

/* 页面底部通用 */
function renderFoot() {
  const el = document.getElementById("foot-root");
  if (el) el.innerHTML = `<div class="foot">${curLang === "en" ? "SnailAI · Australian Chinese AI Training &nbsp;|&nbsp; © 2026 SnailAI &nbsp;|&nbsp; v" + PORTAL_VERSION : "蜗牛AI · 澳洲华人 AI 应用培训 &nbsp;|&nbsp; © 2026 SnailAI &nbsp;|&nbsp; v" + PORTAL_VERSION}</div>`;
}

/* 统一初始化（页面调用）*/
function initPortal(active) {
  renderNav(active);
  renderAnnounce();
  renderFoot();
}

/* 语言切换（全站规范）：切换 [data-zh] 文本、placeholder、标题、按钮态，
   并重渲染依赖语言的公共组件，最后派发 langchange 事件。 */
function setLang(lang) {
  curLang = lang;
  document.documentElement.setAttribute("lang", lang === "en" ? "en" : "zh-CN");
  document.querySelectorAll("[data-zh]").forEach(el => {
    const tx = el.getAttribute("data-" + lang);
    if (tx !== null) el.textContent = tx;
  });
  document.querySelectorAll("[data-ph-zh]").forEach(el => {
    el.setAttribute("placeholder", el.getAttribute("data-ph-" + lang));
  });
  const ti = document.querySelector("[data-title-zh]");
  if (ti) document.title = ti.getAttribute("data-title-" + lang);
  document.querySelectorAll(".lang-btn").forEach(b => b.classList.toggle("active", b.dataset.lang === lang));
  localStorage.setItem(LANG_KEY, lang);
  // 重渲染公共组件
  if (_activeNav) renderNav(_activeNav);
  renderAnnounce();
  renderFoot();
  // 通知页面重渲染动态内容
  window.dispatchEvent(new Event("langchange"));
}

/* 绑定语言切换按钮（幂等） */
function bindLangButtons() {
  document.querySelectorAll(".lang-btn").forEach(b => {
    if (b._bound) return;
    b._bound = true;
    b.addEventListener("click", () => setLang(b.dataset.lang));
  });
}
document.addEventListener("DOMContentLoaded", bindLangButtons);
