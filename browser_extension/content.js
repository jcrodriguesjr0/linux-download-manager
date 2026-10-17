// Painel "Baixar este vídeo" sobre qualquer <video> (equivale ao painel do IDM sobre players web).
(() => {
  if (window.__ldmPanel) return;
  window.__ldmPanel = true;
  const B = globalThis.browser ?? globalThis.chrome;
  const MIN_W = 160, MIN_H = 90;
  let enabled = true;
  B.storage.local.get({ overlay: true }).then((c) => (enabled = c.overlay));
  B.storage.onChanged.addListener((ch) => {
    if (ch.overlay) { enabled = ch.overlay.newValue; if (!enabled) hide(); }
  });

  let host, label, current, hideTimer, raf, lastMove = 0;

  // ---- ponte com page_hook.js (contexto da página): vídeos achados no conteúdo das respostas
  const TAG = "__ldm_page_hook__";
  window.addEventListener("message", (e) => {
    const d = e.data;
    if (e.source !== window || !d || d[TAG] !== "found" || !Array.isArray(d.items)) return;
    const items = d.items.slice(0, 40).filter((i) => i && (typeof i.url === "string" || typeof i.manifest_text === "string"));
    if (items.length) B.runtime.sendMessage({ op: "found", items, page: d.page }).catch(() => {});
  });

  // ---- teclas para impedir/forçar a captura (como o IDM): padrão Alt = navegador, Ctrl+Alt = LDM
  let keys = { prevent: "alt", force: "ctrl+alt" };
  B.runtime.sendMessage({ op: "config" }).then((c) => {
    if (c && c.ldmKeys) keys = Object.assign(keys, c.ldmKeys);
    if (c && c.ldmRules) window.postMessage({ [TAG]: "rules", rules: c.ldmRules }, "*");
  }).catch(() => {});
  const combo = (e) => [e.ctrlKey && "ctrl", e.altKey && "alt", e.shiftKey && "shift", e.metaKey && "meta"].filter(Boolean).join("+");
  document.addEventListener("click", (e) => {
    if (e.button !== 0) return;
    const a = e.target && e.target.closest && e.target.closest("a[href]");
    if (!a || !/^(https?|ftp):/i.test(a.href)) return;
    const c = combo(e);
    if (!c) return;
    if (keys.force && c === keys.force) {
      e.preventDefault();
      e.stopImmediatePropagation();
      B.runtime.sendMessage({ op: "force", url: a.href, referer: location.href }).catch(() => {});
    } else if (keys.prevent && c === keys.prevent) {
      B.runtime.sendMessage({ op: "skip", url: a.href }).catch(() => {});
    }
  }, true);

  function ensure() {
    if (host) return;
    host = document.createElement("ldm-video-panel");
    host.style.cssText = "all:initial;position:fixed;z-index:2147483647;top:0;left:0;display:none;";
    const sh = host.attachShadow({ mode: "closed" });
    sh.innerHTML = `<style>
      button{all:unset;font:600 12px/1 system-ui,sans-serif;background:rgba(11,95,196,.93);color:#fff;
        border:1px solid rgba(255,255,255,.35);border-radius:6px;padding:6px 10px;cursor:pointer;
        box-shadow:0 2px 10px rgba(0,0,0,.45);display:flex;align-items:center;gap:6px;white-space:nowrap}
      button:hover{background:#1a73e8} svg{width:14px;height:14px;flex:none}</style>
      <button title="Linux Download Manager"><svg viewBox="0 0 24 24" fill="#fff"><path d="M10 3h4v8h4l-6 7-6-7h4zM5 20h14v2H5z"/></svg><span>Baixar este vídeo</span></button>`;
    label = sh.querySelector("span");
    const btn = sh.querySelector("button");
    btn.addEventListener("click", onClick, true);
    btn.addEventListener("mousedown", (e) => e.stopPropagation(), true);
    host.addEventListener("mouseenter", () => clearTimeout(hideTimer));
    host.addEventListener("mouseleave", scheduleHide);
    attach();
  }

  function attach() {
    // Em tela cheia só o elemento em fullscreen é visível: o painel vai junto com ele.
    const parent = document.fullscreenElement || document.documentElement;
    if (host && host.parentNode !== parent) parent.appendChild(host);
  }
  document.addEventListener("fullscreenchange", attach, true);

  function visibleVideo(v) {
    if (!v || !v.isConnected) return false;
    const r = v.getBoundingClientRect();
    return r.width >= MIN_W && r.height >= MIN_H && r.bottom > 0 && r.top < innerHeight;
  }

  function place() {
    if (!visibleVideo(current)) return hide();
    const r = current.getBoundingClientRect();
    host.style.display = "block";
    const w = host.offsetWidth || 150;
    host.style.left = Math.max(4, Math.min(innerWidth - w - 4, r.right - w - 12)) + "px";
    host.style.top = Math.max(4, r.top + 12) + "px";
    raf = requestAnimationFrame(place);
  }

  function show(v) {
    if (!enabled || !visibleVideo(v)) return;
    ensure();
    current = v;
    clearTimeout(hideTimer);
    cancelAnimationFrame(raf);
    place();
  }

  function scheduleHide() {
    clearTimeout(hideTimer);
    hideTimer = setTimeout(hide, 2500);
  }

  function hide() {
    cancelAnimationFrame(raf);
    if (host) host.style.display = "none";
  }

  // Players costumam cobrir o <video> com camadas de controles: procura o vídeo sob o ponteiro.
  document.addEventListener("pointermove", (e) => {
    const now = performance.now();
    if (now - lastMove < 120 || !enabled) return;
    lastMove = now;
    const els = document.elementsFromPoint(e.clientX, e.clientY);
    const v = els.find((el) => el.tagName === "VIDEO");
    if (v) show(v);
    else if (host && host.style.display !== "none") scheduleHide();
  }, { passive: true, capture: true });

  document.addEventListener("play", (e) => {
    if (e.target && e.target.tagName === "VIDEO") { show(e.target); scheduleHide(); }
  }, true);

  async function onClick(e) {
    e.preventDefault();
    e.stopPropagation();
    const v = current;
    label.textContent = "Enviando ao LDM...";
    let res;
    try {
      res = await B.runtime.sendMessage({
        op: "video",
        frame_url: location.href,
        title: document.title,
        src: (v && v.currentSrc) || "",
        // dica para o LDM escolher, entre os streams capturados, o deste player
        hint: v ? { duration: isFinite(v.duration) ? v.duration : 0, width: v.videoWidth, height: v.videoHeight,
                    current_src: v.currentSrc || "", mse: (v.currentSrc || "").startsWith("blob:") } : null,
      });
    } catch (err) {
      res = { error: String(err) };
    }
    label.textContent = res && !res.error ? "Enviado ao LDM ✓" : "Abra o Linux Download Manager";
    setTimeout(() => (label.textContent = "Baixar este vídeo"), 3000);
  }
})();
