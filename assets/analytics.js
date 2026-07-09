/* ============================================================
 * 蜗牛AI 访问埋点（自包含，不依赖 auth.js）
 *  - 页面停留上报：visibilitychange / pagehide 时 sendBeacon
 *  - 已登录心跳：每 60s 上报一次活跃（用于计算停留时长）
 *  - 匿名访客：localStorage 随机 visitor_id 标识（不含个人信息）
 * ============================================================ */
(function () {
  var TOKEN_KEY = "snailai_api_token";
  var VID_KEY = "snailai_vid";

  function getToken() {
    try { return sessionStorage.getItem(TOKEN_KEY); } catch (e) { return null; }
  }
  function getVid() {
    var v;
    try { v = localStorage.getItem(VID_KEY); } catch (e) { v = null; }
    if (!v) {
      v = "v-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
      try { localStorage.setItem(VID_KEY, v); } catch (e) {}
    }
    return v;
  }

  var enteredAt = Date.now();
  var path = location.pathname;

  function sendBeacon() {
    var dur = Math.max(0, Math.round((Date.now() - enteredAt) / 1000));
    if (dur < 1) return; // 忽略秒级误触
    var payload = {
      path: path,
      duration_sec: dur,
      referrer: document.referrer || "",
      visitor_id: getVid(),
      token: getToken() || ""
    };
    try {
      navigator.sendBeacon("/api/track/pageview",
        new Blob([JSON.stringify(payload)], { type: "application/json" }));
    } catch (e) {
      fetch("/api/track/pageview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        keepalive: true
      });
    }
  }

  function onHide() {
    if (document.visibilityState === "hidden") sendBeacon();
  }
  document.addEventListener("visibilitychange", onHide);
  window.addEventListener("pagehide", sendBeacon);

  // 已登录才发心跳
  if (getToken()) {
    setInterval(function () {
      try {
        fetch("/api/activity", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token: getToken() }),
          keepalive: true
        });
      } catch (e) {}
    }, 60000);
  }
})();
