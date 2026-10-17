// Painel "Baixar este vídeo" sobre qualquer <video> (equivale ao painel do IDM sobre players web).
(() => {
  if (window.__ldmPanel) return;
  window.__ldmPanel = true;
  const B = globalThis.browser ?? globalThis.chrome;
  const MIN_W = 160, MIN_H = 90;
  let enabled = true;
  let size = "full";                       // "full" = ícone + texto + qualidade; "mini" = só o ícone
  B.storage.local.get({ overlay: true, overlay_size: "full" }).then((c) => { enabled = c.overlay; setSize(c.overlay_size); });
  B.storage.onChanged.addListener((ch) => {
    if (ch.overlay) { enabled = ch.overlay.newValue; if (!enabled) hide(); }
    if (ch.overlay_size) setSize(ch.overlay_size.newValue);
  });

  let host, pill, label, quality, qualityDiv, current, hideTimer, raf, lastMove = 0;

  function setSize(s) {
    size = s === "mini" ? "mini" : "full";
    if (pill) pill.classList.toggle("mini", size === "mini");
  }

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
    // Identidade "Fluxo Segmentado": pílula escura em vidro fosco, âmbar = vídeo.
    sh.innerHTML = `<style>
      .pill{display:inline-flex;align-items:center;background:rgba(20,22,27,.88);backdrop-filter:blur(12px);
        -webkit-backdrop-filter:blur(12px);border:1px solid rgba(245,158,11,.35);border-radius:9999px;
        box-shadow:0 4px 18px rgba(0,0,0,.55),0 0 0 1px rgba(255,255,255,.04);padding:2px 4px;color:#f1f5f9;
        font-family:Inter,system-ui,-apple-system,sans-serif;transition:all .2s cubic-bezier(.16,1,.3,1);user-select:none}
      .pill:hover{background:rgba(26,29,36,.96);border-color:#f59e0b;box-shadow:0 6px 22px rgba(0,0,0,.65),0 0 16px rgba(245,158,11,.28)}
      button{all:unset;display:flex;align-items:center;cursor:pointer;line-height:1;white-space:nowrap}
      .main{gap:7px;padding:6px 10px 6px 8px;font-size:12px;font-weight:600;letter-spacing:.01em;color:#f1f5f9}
      .main:hover{color:#fff}
      svg.ic{width:14px;height:14px;flex:none;filter:drop-shadow(0 0 4px rgba(245,158,11,.4))}
      .div{width:1px;height:14px;background:rgba(245,158,11,.25);margin:0 2px}
      .q{padding:6px 8px;color:#f59e0b;font-size:11px;font-weight:600;border-radius:9999px;transition:background .15s,color .15s}
      .q:hover{background:rgba(245,158,11,.15);color:#fbbf24}
      .q svg{width:10px;height:10px;margin-left:2px}
      .hid{display:none}
      /* mini: só o símbolo, num círculo de 36px (visível sem cobrir o vídeo) */
      .pill.mini{padding:0}
      .pill.mini .main{padding:8px;gap:0}
      .pill.mini .main span,.pill.mini .div,.pill.mini .q{display:none}
      .pill.mini svg.ic{width:18px;height:18px}
      .pill[data-state=ok]{border-color:#22c55e;box-shadow:0 0 14px rgba(34,197,94,.45)}
      .pill[data-state=err]{border-color:#ef4444;box-shadow:0 0 14px rgba(239,68,68,.45)}
      .pill[data-state=busy] svg.ic{animation:pulse .8s ease-in-out infinite alternate}
      @keyframes pulse{from{opacity:1}to{opacity:.35}}</style>
      <div class="pill" title="Linux Download Manager">
        <button class="main"><svg class="ic" viewBox="0 0 24 24"><rect x="3" y="20.5" width="18" height="2.5" rx="1.25" fill="#F59E0B"/><rect x="5" y="2" width="3" height="8.5" rx="1.5" fill="#FBBF24"/><rect x="10.5" y="0.5" width="3" height="10" rx="1.5" fill="#F59E0B"/><rect x="16" y="2" width="3" height="8.5" rx="1.5" fill="#FBBF24"/><path d="M12 18 3.5 9.5h17z" fill="#F59E0B"/></svg><span>Baixar este vídeo</span></button>
        <span class="div hid"></span>
        <button class="q hid" title="Escolher a qualidade no LDM"><b></b><svg viewBox="0 0 10 10"><path d="M2 3.5 5 6.5 8 3.5" fill="none" stroke="#F59E0B" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
      </div>`;
    label = sh.querySelector(".main span");
    quality = sh.querySelector(".q");
    qualityDiv = sh.querySelector(".div");
    pill = sh.querySelector(".pill");                // a pílula inteira é clicável (botão, divisor e qualidade)
    setSize(size);
    pill.addEventListener("click", onClick, true);
    pill.addEventListener("mousedown", (e) => e.stopPropagation(), true);
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
    // resolução que o player está tocando agora; o LDM mostra todas as qualidades ao clicar
    const h = v.videoHeight || 0;
    quality.classList.toggle("hid", !h);
    qualityDiv.classList.toggle("hid", !h);
    if (h) quality.querySelector("b").textContent = `${h}p`;
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
    pill.dataset.state = "busy";
    pill.title = "Enviando ao LDM...";
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
    const ok = res && !res.error;
    label.textContent = ok ? "Enviado ao LDM ✓" : "Abra o Linux Download Manager";
    pill.dataset.state = ok ? "ok" : "err";          // no modo mini a cor da borda mostra o resultado
    pill.title = label.textContent;
    setTimeout(() => {
      label.textContent = "Baixar este vídeo";
      delete pill.dataset.state;
      pill.title = "Linux Download Manager: baixar este vídeo";
    }, 3000);
  }
})();
