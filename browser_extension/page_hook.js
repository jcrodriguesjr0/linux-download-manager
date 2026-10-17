// Roda no contexto da PÁGINA (world: MAIN), como o document.js do IDM.
// Observa o conteúdo das respostas de fetch/XMLHttpRequest e procura vídeos escondidos em APIs:
// manifests HLS/DASH, MPD embutido em JSON (Instagram/Facebook), URLs de mídia em campos de player.
// Nada é alterado na resposta: o corpo é lido de um clone e o site continua funcionando igual.
(() => {
  if (window.__ldmHook) return;
  window.__ldmHook = true;
  const TAG = "__ldm_page_hook__";
  const MAX_BODY = 6 * 1024 * 1024;
  let rules = {
    // URLs cujas respostas valem a pena ler (APIs de players e páginas de vídeo)
    scan_url: "(api|graphql|player|video|media|manifest|playlist|stream|watch|embed|config|ajax|v\\d|json)",
    // nomes de campos que costumam carregar endereços de vídeo
    // campos que carregam endereço de vídeo mesmo sem extensão na URL (sem extensão + campo fraco = ignorado)
    keys: "^(.*_)?(manifest(_?url)?|playlist(_?url)?|hls(_?url|_?manifest(_?url)?)?|dash(_?url|_?manifest(_?url)?)?|m3u8(_?url)?|mpd(_?url)?|video_?url|playable_?url(_quality_hd)?|play_?url|stream_?url|playback_?url|hd_?src|sd_?src|hd_?url|sd_?url|browser_native_(hd|sd)_url|baseurl|contenturl|file_?url|progressive_?url)$",
    media_ext: "(m3u8|mpd|mp4|m4v|m4a|webm|mov|flv|f4m|mp3|aac|ogg|ts)",
    ignore_url: "(doubleclick|googlesyndication|googleadservices|adservice|/ads?[/?]|adsystem|pagead|ptracking|/api/stats|analytics|telemetry|/log(ging|_event)?[/?]|/stats?[/?]|/beacon|/pixel|generate_204|\\[[A-Z_]+\\])",
  };
  let reScan, reKeys, reExt, reIgnore, reUrlInText;
  function compile() {
    reScan = new RegExp(rules.scan_url, "i");
    reKeys = new RegExp(rules.keys, "i");
    reExt = new RegExp(`\\.${rules.media_ext}(?:[?#/]|$)`, "i");
    reIgnore = new RegExp(rules.ignore_url, "i");
    reUrlInText = new RegExp(`https?:(?:\\\\?/){2}[^"'\\s<>\\\\]+?\\.${rules.media_ext}(?:\\?[^"'\\s<>]*)?(?=["'\\s<>\\\\]|$)`, "gi");
  }
  compile();

  const seen = new Set();
  function report(items, from) {
    const fresh = items.filter((i) => {
      const k = i.url || (i.manifest_text || "").slice(0, 200);
      if (!k || seen.has(k)) return false;
      seen.add(k);
      return true;
    });
    if (fresh.length) window.postMessage({ [TAG]: "found", items: fresh, from, page: location.href }, "*");
  }

  function clean(u) {
    return u.replace(/\\\//g, "/").replace(/\\u0026/gi, "&").replace(/&amp;/g, "&");
  }

  function absolute(u, base) {
    try { return new URL(clean(u), base).href; } catch (_) { return null; }
  }

  // Percorre JSON procurando URLs de mídia e MPD embutido
  function walk(obj, base, out, path, depth) {
    if (depth > 40 || out.length > 60 || obj == null) return;
    if (typeof obj === "string") {
      const s = obj;
      if (s.length > 40 && /<MPD[\s>]/.test(s) && /urn:mpeg:dash/i.test(s)) {
        out.push({ kind: "manifest", type: "DASH", manifest_text: s.slice(0, 2_000_000), key: path, base });
      } else if (s.length < 4000 && /^(https?:)?\/\//i.test(s)) {
        const key = path.split(".").pop() || "";
        if (reExt.test(s) || reKeys.test(key)) {
          const u = absolute(s, base);
          if (u && !reIgnore.test(u)) out.push({ url: u, key: path });
        }
      }
      return;
    }
    if (Array.isArray(obj)) {
      obj.forEach((v, i) => walk(v, base, out, `${path}[${i}]`, depth + 1));
      return;
    }
    if (typeof obj === "object") {
      for (const k of Object.keys(obj)) walk(obj[k], base, out, path ? `${path}.${k}` : k, depth + 1);
    }
  }

  function scanText(text, url, ctype) {
    if (!text || text.length > MAX_BODY) return;
    const out = [];
    const t = text.trimStart();
    if (t[0] === "{" || t[0] === "[" || /json/i.test(ctype || "")) {
      try {
        const body = t.startsWith(")]}'") ? t.slice(t.indexOf("\n") + 1) : t;  // prefixo anti-XSSI do Google
        walk(JSON.parse(body), url, out, "", 0);
      } catch (_) { /* não era JSON válido: cai na busca por texto */ }
    }
    if (!out.length) {
      if (/<MPD[\s>]/.test(t) && /urn:mpeg:dash/i.test(t)) out.push({ kind: "manifest", type: "DASH", manifest_text: t.slice(0, 2_000_000), base: url, url });
      else if (t.startsWith("#EXTM3U")) out.push({ kind: "manifest", type: "HLS", url });
      else {
        const m = text.match(reUrlInText);
        if (m) for (const u of m.slice(0, 40)) { const a = absolute(u, url); if (a && !reIgnore.test(a)) out.push({ url: a, key: "texto" }); }
      }
    }
    if (out.length) report(out, url);
  }

  function interesting(url) {
    try {
      const u = new URL(url, location.href);
      if (reIgnore.test(u.href)) return false;
      if (/^(blob|data):/.test(u.protocol)) return false;
      return reScan.test(u.pathname + u.search) || reExt.test(u.pathname) || u.origin === location.origin;
    } catch (_) { return false; }
  }

  // ---- fetch
  const origFetch = window.fetch;
  if (origFetch) {
    window.fetch = function (input, init) {
      const p = origFetch.apply(this, arguments);
      try {
        const url = typeof input === "string" ? input : (input && input.url) || String(input);
        if (interesting(url)) {
          p.then((resp) => {
            try {
              const ct = resp.headers.get("content-type") || "";
              const len = +resp.headers.get("content-length") || 0;
              if (!resp.ok || /^(video|audio|image|font)\//i.test(ct) || len > MAX_BODY) return;
              resp.clone().text().then((txt) => scanText(txt, resp.url || url, ct)).catch(() => {});
            } catch (_) {}
          }).catch(() => {});
        }
      } catch (_) {}
      return p;
    };
  }

  // ---- XMLHttpRequest
  const XO = XMLHttpRequest.prototype.open;
  const XS = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (method, url) {
    try { this.__ldmUrl = String(url); } catch (_) {}
    return XO.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function () {
    try {
      if (this.__ldmUrl && interesting(this.__ldmUrl)) {
        this.addEventListener("load", function () {
          try {
            const ct = this.getResponseHeader("content-type") || "";
            if (/^(video|audio|image|font)\//i.test(ct)) return;
            let txt = null;
            if (this.responseType === "" || this.responseType === "text") txt = this.responseText;
            else if (this.responseType === "json") { const out = []; walk(this.response, this.responseURL, out, "", 0); if (out.length) report(out, this.responseURL); return; }
            if (txt) scanText(txt, this.responseURL || this.__ldmUrl, ct);
          } catch (_) {}
        });
      }
    } catch (_) {}
    return XS.apply(this, arguments);
  };

  // ---- dados que o player já deixou na página (ex.: ytInitialPlayerResponse, __NEXT_DATA__, JSON-LD)
  function scanPageGlobals() {
    const out = [];
    try {
      for (const name of ["ytInitialPlayerResponse", "__NEXT_DATA__", "__INITIAL_STATE__", "__PRELOADED_STATE__", "playerConfig", "flashvars"]) {
        if (window[name] && typeof window[name] === "object") walk(window[name], location.href, out, name, 0);
      }
      for (const s of document.querySelectorAll('script[type="application/ld+json"],script[type="application/json"]')) {
        if (s.textContent && s.textContent.length < MAX_BODY) { try { walk(JSON.parse(s.textContent), location.href, out, "json", 0); } catch (_) {} }
      }
    } catch (_) {}
    if (out.length) report(out, location.href);
  }
  addEventListener("DOMContentLoaded", () => setTimeout(scanPageGlobals, 500));
  addEventListener("load", () => setTimeout(scanPageGlobals, 1500));

  // ---- MSE: registra os codecs que o player usa (ajuda a casar vídeo/áudio)
  try {
    const MS = window.MediaSource || window.ManagedMediaSource;
    if (MS && MS.prototype.addSourceBuffer) {
      const orig = MS.prototype.addSourceBuffer;
      MS.prototype.addSourceBuffer = function (mime) {
        try { window.postMessage({ [TAG]: "mse", mime: String(mime), page: location.href }, "*"); } catch (_) {}
        return orig.apply(this, arguments);
      };
    }
  } catch (_) {}

  // regras atualizadas vindas do LDM (via content script)
  window.addEventListener("message", (e) => {
    const d = e.data;
    if (e.source === window && d && d[TAG] === "rules" && d.rules && typeof d.rules === "object") {
      rules = Object.assign({}, rules, d.rules);
      try { compile(); } catch (_) {}
      scanPageGlobals();
    }
  });
})();
