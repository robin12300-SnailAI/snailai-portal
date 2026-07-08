/* ============================================================
 * 蜗牛AI 学员门户 — 鉴权模块（已接入后端 Flask /api/login）
 *
 * 登录流程：
 *   login.html → POST /api/login → 后端返回 { token, user }
 *   → 前端存 sessionStorage["snailai_api_token"] + ["snailai_me"]
 *   本文件只负责「读取这个 session」并做登录态守卫，
 *   不再做本地密码校验（密码校验在后端）。
 *
 * 为兼容旧页面，仍保留对旧 key "snailai_session" 的读取回退。
 *
 * 角色（role）控制界面称呼与可见内容：
 *   "student"    学员
 *   "ta"         助教
 *   "instructor" 总讲师
 * ============================================================ */

/* ---------- 新后端 session key ---------- */
const TOKEN_KEY = "snailai_api_token";
const ME_KEY = "snailai_me";
/* 旧兼容 key（纯静态方案遗留） */
const SESSION_KEY = "snailai_session";

/* ---------- 读取当前登录用户 ---------- */
function getCurrentUser() {
  // 优先读新后端 session
  try {
    const raw = sessionStorage.getItem(ME_KEY);
    if (raw) return JSON.parse(raw);
  } catch (e) {}
  // 回退：旧纯静态方案
  try {
    const s = sessionStorage.getItem(SESSION_KEY);
    if (s) return (JSON.parse(s).user) || null;
  } catch (e) {}
  return null;
}

/* 是否已登录（同时要求 token 与用户信息都在）*/
function isLoggedIn() {
  return !!getCurrentUser() && !!sessionStorage.getItem(TOKEN_KEY);
}

/* 需要登录的页面调用：未登录跳转到统一登录页 */
function requireAuth() {
  if (!isLoggedIn()) {
    location.href = navPrefix() + "login.html";
  }
}

/* 退出：清除所有 session 并回登录页 */
function logout() {
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(ME_KEY);
  sessionStorage.removeItem(SESSION_KEY);
  location.href = navPrefix() + "login.html";
}

/* ---------- 角色判断 ---------- */
function isStudent()    { const u = getCurrentUser(); return u && u.role === "student"; }
function isTA()         { const u = getCurrentUser(); return u && u.role === "ta"; }
function isInstructor() { const u = getCurrentUser(); return u && u.role === "instructor"; }
function isStaff()      { return isTA() || isInstructor(); }
