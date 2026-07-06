/* ============================================================
 * 蜗牛AI 学员门户 — 鉴权模块 (纯静态 / 硬编码方案)
 * 账号密码直接写在本文件里（USERS）。学员登录后即可查看
 * 课件、PPT、YouTube 链接。**不涉及后端、不连任何服务器。**
 *
 * 能力清单的「打勾确认」已在企业微信智能表格完成，
 * 本门户只做能力项只读展示，不存储勾选状态。
 *
 * 角色（role）仅用于界面称呼，不影响可见内容：
 *   "student"    学员
 *   "ta"         助教
 *   "instructor" 总讲师
 *
 * 上线前请把 USERS 换成真实学员/助教名单（不要公开真密码）。
 * ============================================================ */

/* ---------- 硬编码账号表（上线前替换）---------- */
const USERS = [
  { username: "student01", name: "学员一号", password: "snail123", role: "student" },
  { username: "student02", name: "学员二号", password: "snail123", role: "student" },
  { username: "ta01",      name: "助教一号", password: "snailai@ta",  role: "ta" },
  { username: "teacher01", name: "罗宾 Robin", password: "snail@teacher", role: "instructor" }
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
  location.href = "login.html";
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

/* 需要登录的页面调用：未登录跳转到登录页 */
function requireAuth() {
  if (!isLoggedIn()) {
    location.href = "login.html?next=" + encodeURIComponent(location.pathname.split("/").pop() || "dashboard.html");
  }
}

/* 角色判断（仅界面称呼用，不影响可见内容）*/
function isStudent()    { const u = getCurrentUser(); return u && u.role === "student"; }
function isTA()         { const u = getCurrentUser(); return u && u.role === "ta"; }
function isInstructor() { const u = getCurrentUser(); return u && u.role === "instructor"; }
function isStaff()      { return isTA() || isInstructor(); }
