/* ============================================================
 * 蜗牛AI 学员门户 — 鉴权模块 (后端 API 方案)
 * 账号 / 角色 / 能力清单勾选 全部由后端 SQLite 统一管理。
 * 前端只保存登录后返回的 token（sessionStorage），不存密码、不存勾选数据。
 *
 * 角色（role）三种：
 *   "student"    学员   — 勾「自查」
 *   "ta"         助教   — 勾「初审」，可查看所有学员
 *   "instructor" 总讲师 — 勾「最终确认」，可查看所有学员
 *
 * 部署：后端 Flask 服务既托管本门户又提供 /api/*。
 * 若门户与后端不同源（例如门户在 GitHub Pages、后端独立部署），
 * 在 login.html 之前设置 window.SNAILAI_API_BASE = "https://你的后端地址"
 * 即可，无需改动本文件其它部分。
 * ============================================================ */

/* API 基地址：同源为空串；跨域部署时由页面注入 window.SNAILAI_API_BASE */
const API_BASE = (typeof window !== "undefined" && window.SNAILAI_API_BASE) || "";

const SESSION_KEY = "snailai_session"; // 存 {token, user}

/* ---------- 低级请求封装 ---------- */
async function apiFetch(path, opts = {}) {
  const url = API_BASE + path;
  const headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
  const token = getToken();
  if (token) headers["Authorization"] = "Bearer " + token;
  const resp = await fetch(url, {
    method: opts.method || "GET",
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined
  });
  let data = null;
  try { data = await resp.json(); } catch (e) { data = {}; }
  if (resp.status === 401 && !opts.suppressAuth) {
    // token 失效：清理并跳转登录（登录接口本身不触发）
    _clearSession();
    if (location.pathname.indexOf("login.html") === -1) {
      location.href = "login.html?next=" + encodeURIComponent(location.pathname.split("/").pop() || "dashboard.html");
    }
    throw new Error("未登录或登录已失效");
  }
  return { status: resp.status, data };
}

/* ---------- 登录 / 登出 ---------- */
async function login(username, password) {
  username = (username || "").trim();
  // 登录失败本身是 401，不应触发自动跳转
  const { status, data } = await apiFetch("/api/login", {
    method: "POST", body: { username, password }, suppressAuth: true
  });
  if (!data.ok) return { ok: false, msg: data.error || "登录失败" };
  _saveSession(data.token, data.user);
  return { ok: true, user: data.user };
}

async function logout() {
  try { await apiFetch("/api/logout", { method: "POST" }); } catch (e) {}
  _clearSession();
  location.href = "login.html";
}

function _saveSession(token, user) {
  sessionStorage.setItem(SESSION_KEY, JSON.stringify({ token, user }));
}
function _clearSession() {
  sessionStorage.removeItem(SESSION_KEY);
}
function getToken() {
  try { return (JSON.parse(sessionStorage.getItem(SESSION_KEY) || "{}")).token || null; }
  catch (e) { return null; }
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

/* 角色判断 */
function isStudent()    { const u = getCurrentUser(); return u && u.role === "student"; }
function isTA()         { const u = getCurrentUser(); return u && u.role === "ta"; }
function isInstructor() { const u = getCurrentUser(); return u && u.role === "instructor"; }
function isStaff()      { return isTA() || isInstructor(); } // 助教/总讲师可看所有学员

/* ============================================================
 * 能力清单数据层（全部走后端 API，来源：SQLite）
 * 能力项从 /api/capabilities 读取；勾选读写 /api/checks。
 * ============================================================ */

/* 取全部能力项 */
async function apiGetCapabilities() {
  const { data } = await apiFetch("/api/capabilities");
  return data.ok ? data.capabilities : [];
}

/* 取学员列表（仅助教/总讲师可调用）*/
async function apiGetStudents() {
  const { data } = await apiFetch("/api/students");
  return data.ok ? data.students : [];
}

/* 取某学员的全部勾选：{capId: {self,ta,final,updated_at,updated_by}} */
async function apiGetChecks(username) {
  const { data } = await apiFetch("/api/checks/" + encodeURIComponent(username));
  if (!data.ok) throw new Error(data.error || "读取失败");
  return data.checks || {};
}

/* 设置某学员某能力的某一列勾选
 * column: "self" | "ta" | "final" ; value: true/false */
async function apiSetCheck(username, capId, column, value) {
  const { data } = await apiFetch(
    "/api/checks/" + encodeURIComponent(username) + "/" + encodeURIComponent(capId),
    { method: "PUT", body: { column, value: value ? 1 : 0 } }
  );
  if (!data.ok) throw new Error(data.error || "保存失败");
  return data;
}

/* 兼容旧引用：返回学员列表 [{username,name}] */
async function listStudents() { return apiGetStudents(); }
