/* ============================================================
 * 蜗牛AI 学员门户 — 鉴权模块 (纯静态 / 硬编码方案)
 * 账号密码直接写在本文件里（USERS）。学员登录后即可查看
 * 课件、PPT、YouTube 链接。**不涉及后端、不连任何服务器。**
 *
 * 能力清单的「打勾确认」（学员自查 / 助教初审 / 讲师终审）
 * 存于浏览器 localStorage（键 snailai_checklist_v1），
 * 靠导出 / 导入 JSON 在设备 / 人员之间合并。
 *
 * 角色（role）控制可勾选的列：
 *   "student"    学员  → 勾「自查」
 *   "ta"         助教  → 勾「初审」
 *   "instructor" 总讲师 → 勾「最终确认」
 *
 * 上线前请把 USERS 换成真实学员/助教名单（不要公开真密码）。
 * ============================================================ */

/* ---------- 硬编码账号表（上线前替换）---------- */
const USERS = [
  { username: "serena",     name: "Serena 谢昕言", password: "12345", role: "student" },
  { username: "mandy",      name: "Mandy 曼蒂",    password: "12345", role: "student" },
  { username: "jenny",      name: "Jenny",         password: "12345", role: "student" },
  { username: "jackie",     name: "Jackie",        password: "12345", role: "student" },
  { username: "xianlu",     name: "仙路",          password: "12345", role: "student" },
  { username: "coco",       name: "雅雅CoCo",      password: "12345", role: "student" },
  { username: "xieyouchen", name: "谢侑辰",        password: "12345", role: "student" },
  { username: "wuqing",     name: "吴清",          password: "12345", role: "student" },
  { username: "jiangpei",   name: "蒋培",          password: "12345", role: "student" },
  { username: "laoliu",     name: "laoliu",        password: "12345", role: "student" },
  { username: "suping",     name: "suping",        password: "12345", role: "student" },
  { username: "lucy",       name: "Lucy",          password: "12345", role: "student" },
  { username: "step",       name: "step",          password: "12345", role: "student" },
  { username: "zilin",      name: "子霖",          password: "12345", role: "student" },
  { username: "ta01",       name: "助教一号",      password: "snailai@ta",  role: "ta" },
  { username: "teacher01",  name: "罗宾 Robin",    password: "snail@teacher", role: "instructor" }
];

const SESSION_KEY = "snailai_session"; // 存 {user}

/* ---------- 登录 / 登出（纯本地校验）---------- */
async function login(username, password) {
  username = (username || "").trim();
  const u = USERS.find(x => x.username === username && x.password === password);
  if (!u) return { ok: false, msg: "用户名或密码错误" };
  _saveSession({ username: u.username, name: u.name, role: u.role });
  return { ok: true, user: { username: u.username, name: u.name, role: u.role } };
}

function logout() {
  _clearSession();
  location.href = navPrefix() + "login.html";
}

function _saveSession(user) {
  sessionStorage.setItem(SESSION_KEY, JSON.stringify({ user }));
}
function _clearSession() {
  sessionStorage.removeItem(SESSION_KEY);
}
function getCurrentUser() {
  try { return (JSON.parse(sessionStorage.getItem(SESSION_KEY) || "{}")).user || null; }
  catch (e) { return null; }
}
function isLoggedIn() { return !!getCurrentUser(); }

/* 需要登录的页面调用：未登录跳转到登录页（自动算门户根目录相对路径）*/
function requireAuth() {
  if (!isLoggedIn()) {
    // 计算相对于门户根目录的当前路径，作为登录后回跳地址
    const here = location.href.split("?")[0].split("#")[0];
    let marker = "官网学生登录";
    let idx = here.indexOf(marker);
    if (idx === -1) { marker = "/student/"; idx = here.indexOf(marker); }
    let next = "dashboard.html";
    if (idx > -1) {
      const rel = here.slice(idx + marker.length).replace(/^\//, "");
      if (rel && rel !== "login.html") next = rel;
    }
    location.href = navPrefix() + "login.html?next=" + encodeURIComponent(next);
  }
}

/* 角色判断（仅界面称呼用，不影响可见内容）*/
function isStudent()    { const u = getCurrentUser(); return u && u.role === "student"; }
function isTA()         { const u = getCurrentUser(); return u && u.role === "ta"; }
function isInstructor() { const u = getCurrentUser(); return u && u.role === "instructor"; }
function isStaff()      { return isTA() || isInstructor(); }
