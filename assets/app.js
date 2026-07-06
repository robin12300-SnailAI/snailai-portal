/* ============================================================
 * 蜗牛AI 学员门户 — 公共导航 & 页面工具
 * 每个门户页面在 <body> 顶部放 <div id="nav-root"></div>，
 * 在末尾引入本文件并调用 renderNav('online') 等。
 * 导航链接前缀会根据当前页面深度自动计算，
 * 所以无论页面在根目录还是子目录都能正确跳转。
 * ============================================================ */

/* 计算从当前页面回到门户根目录的相对前缀
 * 兼容两种运行位置：
 *   - 本地开发：文件夹名为「官网学生登录」
 *   - 线上部署：挂在 /student/ 子目录（如 GitHub Pages 的 /chocolate/student/）
 * 关键点：/student/ 带前导斜杠会产生空路径段，必须切片时去掉。
 */
function navPrefix() {
  const href = location.href.split("?")[0].split("#")[0];
  let marker = "官网学生登录";
  let idx = href.indexOf(marker);
  if (idx === -1) { marker = "/student/"; idx = href.indexOf(marker); }
  if (idx === -1) return "./";
  // 取 marker 之后的路径段（去掉前导斜杠），按 "/" 计算相对层级
  const rest = href.slice(idx + marker.length);
  const segs = rest.split("/").filter(s => s.length > 0);
  let depth = segs.length;
  if (depth > 0 && segs[depth - 1].indexOf(".") > -1) depth -= 1; // 末段是文件
  return depth > 0 ? "../".repeat(depth) : "./";
}

const NAV_ITEMS = [
  { key: "dashboard", label: "我的学堂", file: "dashboard.html" },
  { key: "online", label: "AI 应用线上班", file: "AI 应用线上班/" },
  { key: "offline", label: "AI 财富线下班", file: "AI 财富线下班/" },
  { key: "checklist", label: "AI 能力清单", file: "AI 能力清单/" },
  { key: "roadmap", label: "路演直播 PPT", file: "路演直播 PPT/" }
];

function renderNav(active) {
  const root = document.getElementById("nav-root");
  if (!root) return;
  const p = navPrefix();
  const user = getCurrentUser();
  let links = NAV_ITEMS.map(it =>
    `<a href="${p}${it.file}" class="${it.key === active ? "active" : ""}">${it.label}</a>`
  ).join("");

  let right;
  if (user) {
    right = `
      <div class="userbox">
        <span class="uname">${user.name}${user.role === "instructor" ? " · 总讲师" : user.role === "ta" ? " · 助教" : ""}</span>
        <button class="btn btn-ghost btn-sm" onclick="logout()">退出</button>
      </div>`;
  } else {
    right = `<a class="btn btn-primary btn-sm" href="${p}login.html">学员登录</a>`;
  }

  root.innerHTML = `
    <nav class="topnav">
      <a class="brand" href="${p}dashboard.html">
        <span class="logo">🐌</span><span>蜗牛AI · 学员学堂</span>
      </a>
      <div class="navlinks">${links}</div>
      ${right}
    </nav>`;
}

/* 公告（你后续改这里的内容即可全站生效；留空则不显示）*/
const ANNOUNCEMENT = "📢 学员学堂试运行中：课件与能力清单正在陆续上传，敬请期待。";
function renderAnnounce() {
  if (!ANNOUNCEMENT) return;
  const el = document.getElementById("announce-root");
  if (el) el.innerHTML = `<div class="announce">${ANNOUNCEMENT}</div>`;
}

/* 页面底部通用 */
function renderFoot() {
  const el = document.getElementById("foot-root");
  if (el) el.innerHTML = `<div class="foot">蜗牛AI · 澳洲华人 AI 应用培训 &nbsp;|&nbsp; © 2026 SnailAI</div>`;
}

/* 统一初始化（页面调用）*/
function initPortal(active) {
  renderNav(active);
  renderAnnounce();
  renderFoot();
}
