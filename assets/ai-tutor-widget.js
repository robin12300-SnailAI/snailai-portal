/**
 * Snail AI Tutor — Floating Chat Widget
 * Include on any page: <script src="/assets/ai-tutor-widget.js"></script>
 * Auto-injects: floating bot button + draggable chat popup
 */
(function() {
  // Prevent double-load
  if (document.getElementById('snailai-tutor-fab')) return;

  var BOT_IMG = '/assets/ai-tutor-bot.jpg';
  var API_URL = '/api/chat/ask';

  // ── Inject CSS ──
  var css = document.createElement('style');
  css.textContent = '\
    .sai-fab{position:fixed;bottom:28px;right:28px;z-index:10000;width:60px;height:60px;border-radius:50%;border:3px solid #fff;background:linear-gradient(135deg,#FF5B1F 0%,#FF8C42 100%);cursor:pointer;overflow:hidden;box-shadow:0 4px 20px rgba(255,91,31,0.35);display:flex;align-items:center;justify-content:center;transition:transform .3s cubic-bezier(.34,1.56,.64,1),box-shadow .3s;}.sai-fab:hover{transform:scale(1.1);box-shadow:0 6px 28px rgba(255,91,31,0.45);}.sai-fab img{width:100%;height:100%;object-fit:cover;border-radius:50%;}.sai-fab .sai-pulse{position:absolute;width:100%;height:100%;border-radius:50%;background:#FF5B1F;opacity:0;animation:sai-pulse 2.5s ease-out infinite;}.sai-fab .sai-tip{position:absolute;right:70px;top:50%;transform:translateY(-50%);background:#1A1A2E;color:#fff;font-size:13px;font-weight:600;padding:8px 14px;border-radius:8px;white-space:nowrap;opacity:0;pointer-events:none;transition:opacity .2s;box-shadow:0 4px 16px rgba(26,26,46,0.08);}.sai-fab .sai-tip::after{content:"";position:absolute;right:-6px;top:50%;transform:translateY(-50%);border:6px solid transparent;border-left-color:#1A1A2E;border-right:none;}.sai-fab:hover .sai-tip{opacity:1;}.sai-fab.sai-open .sai-tip{display:none;}@keyframes sai-pulse{0%{transform:scale(1);opacity:.4;}100%{transform:scale(1.8);opacity:0;}}\
    .sai-popup{position:fixed;z-index:9999;width:390px;height:540px;border-radius:16px;background:#fff;border:1px solid rgba(26,26,46,0.08);box-shadow:0 8px 32px rgba(26,26,46,0.12);display:none;flex-direction:column;overflow:hidden;}.sai-popup.sai-visible{display:flex;animation:sai-pop-in .25s ease-out;}.sai-popup.sai-closing{animation:sai-pop-out .2s ease-in forwards;}@keyframes sai-pop-in{from{opacity:0;transform:scale(.9) translateY(20px);}to{opacity:1;transform:scale(1) translateY(0);}}@keyframes sai-pop-out{from{opacity:1;transform:scale(1) translateY(0);}to{opacity:0;transform:scale(.9) translateY(20px);}}\
    .sai-titlebar{display:flex;align-items:center;gap:10px;padding:12px 16px;background:linear-gradient(135deg,#FF5B1F 0%,#FF8C42 100%);color:#fff;cursor:grab;user-select:none;flex-shrink:0;}.sai-titlebar:active{cursor:grabbing;}.sai-titlebar img{width:30px;height:30px;border-radius:50%;object-fit:cover;border:2px solid rgba(255,255,255,0.4);}.sai-titlebar .sai-ttext{flex:1;font-weight:700;font-size:14px;}.sai-titlebar .sai-tsub{font-size:11px;opacity:.8;}.sai-titlebar button{background:rgba(255,255,255,0.2);border:none;color:#fff;cursor:pointer;width:28px;height:28px;border-radius:50%;font-size:15px;line-height:1;display:flex;align-items:center;justify-content:center;transition:background .15s;}.sai-titlebar button:hover{background:rgba(255,255,255,0.35);}\
    .sai-msgs{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:12px;background:#FCFCFA;}.sai-msgs::-webkit-scrollbar{width:4px;}.sai-msgs::-webkit-scrollbar-thumb{background:#E8E7E0;border-radius:4px;}\
    .sai-msg{max-width:88%;}.sai-msg.sai-user{align-self:flex-end;}.sai-msg.sai-bot{align-self:flex-start;}.sai-msg .sai-bub{padding:11px 15px;border-radius:14px;font-size:13.5px;line-height:1.65;white-space:pre-wrap;word-break:break-word;}.sai-msg.sai-user .sai-bub{background:#1A1A2E;color:#fff;border-bottom-right-radius:4px;}.sai-msg.sai-bot .sai-bub{background:#fff;color:#1A1A2E;border-bottom-left-radius:4px;border:1px solid rgba(26,26,46,0.08);}.sai-msg .sai-meta{font-size:10px;color:#6A6A85;margin-top:3px;}.sai-msg.sai-user .sai-meta{text-align:right;}.sai-msg .sai-refs{font-size:11.5px;color:#FF5B1F;margin-top:5px;padding-top:5px;border-top:1px solid rgba(26,26,46,0.08);}\
    .sai-typing{display:flex;gap:4px;padding:11px 15px;}.sai-typing span{width:6px;height:6px;background:#6A6A85;border-radius:50%;animation:sai-blink 1.2s infinite;}.sai-typing span:nth-child(2){animation-delay:.2s;}.sai-typing span:nth-child(3){animation-delay:.4s;}@keyframes sai-blink{0%,80%,100%{opacity:.3;transform:scale(.8);}40%{opacity:1;transform:scale(1);}}\
    .sai-input{display:flex;align-items:flex-end;gap:8px;padding:12px 14px;border-top:1px solid rgba(26,26,46,0.08);background:#fff;flex-shrink:0;}.sai-input textarea{flex:1;resize:none;border:1px solid #E8E7E0;border-radius:12px;padding:9px 13px;font-size:13.5px;font-family:inherit;line-height:1.5;max-height:100px;outline:none;transition:border-color .2s;}.sai-input textarea:focus{border-color:#FF5B1F;}.sai-input button{width:40px;height:40px;border-radius:12px;border:none;background:#FF5B1F;color:#fff;cursor:pointer;font-size:17px;display:flex;align-items:center;justify-content:center;transition:background .2s,transform .1s;}.sai-input button:hover{background:#E84A0F;}.sai-input button:active{transform:scale(.95);}.sai-input button:disabled{background:#E8E7E0;cursor:not-allowed;}\
    .sai-disc{padding:6px 14px;font-size:10px;color:#6A6A85;text-align:center;background:#F5F4EE;border-top:1px solid rgba(26,26,46,0.08);flex-shrink:0;}\
  ';
  document.head.appendChild(css);

  // ── Inject HTML ──
  var lang = localStorage.getItem('snailai-lang') || 'zh';
  var tipText = lang === 'zh' ? '有问题？问我呀 👋' : 'Questions? Ask me 👋';
  var titleText = lang === 'zh' ? '蜗牛AI助教' : 'Snail AI Tutor';
  var titleSub = lang === 'zh' ? '随时为你解答' : 'Always here to help';
  var welcomeText = lang === 'zh'
    ? '你好！我是蜗牛AI助教，可以回答课程、学费、报名、登录等问题。有什么想问的？'
    : 'Hello! I\'m the Snail AI tutor. I can answer questions about courses, fees, enrollment, and login. What would you like to know?';
  var placeholder = lang === 'zh' ? '输入你的问题…' : 'Type your question…';

  var html = '\
    <button class="sai-fab" id="snailai-tutor-fab">\
      <span class="sai-pulse"></span>\
      <img src="' + BOT_IMG + '" alt="AI Tutor" />\
      <span class="sai-tip">' + tipText + '</span>\
    </button>\
    <div class="sai-popup" id="snailai-tutor-popup">\
      <div class="sai-titlebar" id="snailai-tutor-titlebar">\
        <img src="' + BOT_IMG + '" alt="" />\
        <div><div class="sai-ttext">' + titleText + '</div><div class="sai-tsub">' + titleSub + '</div></div>\
        <button id="sai-btn-min" title="Minimize">—</button>\
        <button id="sai-btn-close" title="Close">✕</button>\
      </div>\
      <div class="sai-msgs" id="snailai-tutor-msgs">\
        <div class="sai-msg sai-bot"><div class="sai-bub">' + welcomeText + '</div></div>\
      </div>\
      <div class="sai-input">\
        <textarea id="snailai-tutor-input" rows="1" placeholder="' + placeholder + '"></textarea>\
        <button id="snailai-tutor-send" aria-label="Send">\
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2L11 13"/><path d="M22 2L15 22L11 13L2 9L22 2Z"/></svg>\
        </button>\
      </div>\
      <div class="sai-disc">' + (lang === 'zh' ? 'AI 助教仅基于蜗牛AI课程知识库回答，可能不完整，请以官方信息为准。' : 'AI Tutor answers based on course knowledge base. Verify with official sources.') + '</div>\
    </div>';

  var container = document.createElement('div');
  container.innerHTML = html;
  document.body.appendChild(container);

  // ── Elements ──
  var fab = document.getElementById('snailai-tutor-fab');
  var popup = document.getElementById('snailai-tutor-popup');
  var titlebar = document.getElementById('snailai-tutor-titlebar');
  var msgArea = document.getElementById('snailai-tutor-msgs');
  var qInput = document.getElementById('snailai-tutor-input');
  var sendBtn = document.getElementById('snailai-tutor-send');
  var sending = false;

  // ── Open / Close ──
  fab.addEventListener('click', function() { toggleChat(); });
  document.getElementById('sai-btn-min').addEventListener('click', function(e) { e.stopPropagation(); closeChat(); });
  document.getElementById('sai-btn-close').addEventListener('click', function(e) { e.stopPropagation(); closeChat(); });

  function toggleChat() {
    if (popup.classList.contains('sai-visible')) closeChat();
    else openChat();
  }

  function openChat() {
    var pos = localStorage.getItem('snailai-chat-pos');
    if (pos) {
      try { var p = JSON.parse(pos); popup.style.left = p.x + 'px'; popup.style.top = p.y + 'px'; }
      catch(e) { defaultPos(); }
    } else { defaultPos(); }
    popup.classList.remove('sai-closing');
    popup.classList.add('sai-visible');
    fab.classList.add('sai-open');
    qInput.focus();
  }

  function defaultPos() {
    var w = window.innerWidth, h = window.innerHeight;
    popup.style.left = Math.max(10, w - 410) + 'px';
    popup.style.top = Math.max(10, h - 580) + 'px';
  }

  function closeChat() {
    popup.classList.add('sai-closing');
    fab.classList.remove('sai-open');
    setTimeout(function() { popup.classList.remove('sai-visible', 'sai-closing'); }, 200);
  }

  // ── Drag ──
  var dragging = false, dragX = 0, dragY = 0;

  titlebar.addEventListener('mousedown', function(e) {
    if (e.target.tagName === 'BUTTON') return;
    dragging = true;
    var rect = popup.getBoundingClientRect();
    dragX = e.clientX - rect.left;
    dragY = e.clientY - rect.top;
    e.preventDefault();
  });
  document.addEventListener('mousemove', function(e) {
    if (!dragging) return;
    var x = Math.max(0, Math.min(e.clientX - dragX, window.innerWidth - popup.offsetWidth));
    var y = Math.max(0, Math.min(e.clientY - dragY, window.innerHeight - popup.offsetHeight));
    popup.style.left = x + 'px';
    popup.style.top = y + 'px';
  });
  document.addEventListener('mouseup', function() {
    if (dragging) {
      dragging = false;
      localStorage.setItem('snailai-chat-pos', JSON.stringify({ x: parseInt(popup.style.left), y: parseInt(popup.style.top) }));
    }
  });

  // Touch drag
  titlebar.addEventListener('touchstart', function(e) {
    if (e.target.tagName === 'BUTTON') return;
    dragging = true;
    var t = e.touches[0], rect = popup.getBoundingClientRect();
    dragX = t.clientX - rect.left;
    dragY = t.clientY - rect.top;
  }, { passive: true });
  document.addEventListener('touchmove', function(e) {
    if (!dragging) return;
    var t = e.touches[0];
    var x = Math.max(0, Math.min(t.clientX - dragX, window.innerWidth - popup.offsetWidth));
    var y = Math.max(0, Math.min(t.clientY - dragY, window.innerHeight - popup.offsetHeight));
    popup.style.left = x + 'px';
    popup.style.top = y + 'px';
  }, { passive: true });
  document.addEventListener('touchend', function() {
    if (dragging) {
      dragging = false;
      localStorage.setItem('snailai-chat-pos', JSON.stringify({ x: parseInt(popup.style.left), y: parseInt(popup.style.top) }));
    }
  });

  // ── Chat ──
  function esc(s) { var d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

  function addMsg(role, text, refs, source) {
    var div = document.createElement('div');
    div.className = 'sai-msg sai-' + role;
    var bubble = '<div class="sai-bub">' + esc(text) + '</div>';
    if (refs) bubble += '<div class="sai-refs">' + esc(refs) + '</div>';
    if (source && source !== 'facts') {
      var l = localStorage.getItem('snailai-lang') || 'zh';
      bubble += '<div class="sai-meta">' + esc(l === 'zh' ? '来源: ' + source : 'Source: ' + source) + '</div>';
    }
    div.innerHTML = bubble;
    msgArea.appendChild(div);
    msgArea.scrollTop = msgArea.scrollHeight;
  }

  function addTyping() {
    var div = document.createElement('div');
    div.className = 'sai-msg sai-bot';
    div.id = 'sai-typing-msg';
    div.innerHTML = '<div class="sai-typing"><span></span><span></span><span></span></div>';
    msgArea.appendChild(div);
    msgArea.scrollTop = msgArea.scrollHeight;
  }

  function removeTyping() {
    var t = document.getElementById('sai-typing-msg');
    if (t) t.remove();
  }

  qInput.addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 100) + 'px';
  });

  sendBtn.addEventListener('click', doSend);
  qInput.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); doSend(); }
  });

  function doSend() {
    if (sending) return;
    var q = qInput.value.trim();
    if (!q || q.length < 2) return;
    var lang2 = localStorage.getItem('snailai-lang') || 'zh';
    addMsg('user', q);
    qInput.value = '';
    qInput.style.height = 'auto';
    sending = true;
    sendBtn.disabled = true;
    addTyping();
    var controller = new AbortController();
    var timeout = setTimeout(function() { controller.abort(); }, 30000);
    fetch(API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q, lang: lang2 }),
      signal: controller.signal
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      clearTimeout(timeout); removeTyping();
      if (data.ok) addMsg('bot', data.answer, data.refs || '', data.source || '');
      else addMsg('bot', data.error || 'Unknown error', '', 'error');
    })
    .catch(function() {
      clearTimeout(timeout); removeTyping();
      var l = localStorage.getItem('snailai-lang') || 'zh';
      addMsg('bot', l === 'zh' ? '网络错误或超时，请稍后再试。' : 'Network error or timeout. Please try again later.', '', 'error');
    })
    .finally(function() { sending = false; sendBtn.disabled = false; });
  }
})();
