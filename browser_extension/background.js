// Linux Download Manager - integração com o navegador (equivale ao IDMIECC/idmmzcc + painel de vídeo do IDM).
const B = globalThis.browser ?? globalThis.chrome;
const DEFAULT_PORT = 9614;

async function cfg() {
  const c = await B.storage.local.get({ port: DEFAULT_PORT, capture: true });
  return c;
}

async function api(path, payload) {
  const { port } = await cfg();
  const opts = payload === undefined
    ? { method: "GET", headers: { "X-LDM-Client": "1" } }
    : { method: "POST", headers: { "Content-Type": "application/json", "X-LDM-Client": "1" }, body: JSON.stringify(payload) };
  const r = await fetch(`http://127.0.0.1:${port}${path}`, opts);
  if (!r.ok) throw new Error(`LDM respondeu ${r.status}`);
  return r.json();
}

async function cookiesFor(url) {
  try {
    const list = await B.cookies.getAll({ url });
    return list.map((c) => `${c.name}=${c.value}`).join("; ");
  } catch (_) {
    return "";
  }
}

function basename(p) {
  return (p || "").split(/[\\/]/).pop();
}

async function sendAdd(url, extra = {}) {
  const payload = {
    url,
    cookies: await cookiesFor(url),
    user_agent: navigator.userAgent,
    ...extra,
  };
  if (/\.m3u8(\?|$)/i.test(url)) payload.kind = "hls";
  return api("/add", payload);
}

// Cookies completos (domínio, caminho, validade) para o yt-dlp: necessários em sites com login.
async function fullCookies(urls) {
  const seen = new Map();
  for (const u of urls) {
    if (!/^https?:/i.test(u || "")) continue;
    try {
      for (const c of await B.cookies.getAll({ url: u })) {
        seen.set(`${c.domain}|${c.path}|${c.name}`, {
          domain: c.domain, hostOnly: c.hostOnly, path: c.path, secure: c.secure,
          expirationDate: c.expirationDate, name: c.name, value: c.value,
        });
      }
    } catch (_) {}
  }
  return [...seen.values()];
}

const mediaStore = () => B.storage.session ?? B.storage.local;

async function sniffedFor(tabId) {
  const key = `media_${tabId}`;
  return (await mediaStore().get({ [key]: [] }))[key];
}

// "Baixar este vídeo": o LDM analisa a página com yt-dlp e mostra também os streams capturados.
async function sendVideo(tab, extra = {}) {
  const page = tab?.url || extra.page_url || extra.frame_url;
  return api("/video", {
    page_url: page,
    frame_url: extra.frame_url || page,
    src: extra.src && !extra.src.startsWith("blob:") ? extra.src : "",
    title: tab?.title || extra.title || "",
    sniffed: tab ? await sniffedFor(tab.id) : [],
    video_hint: extra.hint || null,
    cookies: await fullCookies([page, extra.frame_url, extra.src]),
    user_agent: navigator.userAgent,
  });
}

async function sendStream(tab, m) {
  return api("/stream", {
    stream: m, page_url: tab?.url || "", title: tab?.title || "video",
    cookies: await fullCookies([tab?.url, m.url]), user_agent: navigator.userAgent,
  });
}

// ---------------------------------------------------------------- captura de downloads
// Como o IDM, olha o tráfego: os cabeçalhos da resposta (nome real no Content-Disposition, tamanho, tipo)
// chegam ANTES de o navegador criar o download. Quando o download aparece (onCreated), a decisão já usa o nome
// e o tamanho verdadeiros, mesmo em links dinâmicos como /download.php?id=123.
const CAPTURE_TIMEOUT = 5000;
const DL_HEADERS_MAX = 200;
const dlHeaders = new Map();   // url -> { name, size, mime, t }

function filenameFromCD(cd) {
  let m = /filename\*\s*=\s*([^']*)'[^']*'([^;]+)/i.exec(cd);
  if (m) { try { return decodeURIComponent(m[2].trim().replace(/^"|"$/g, "")); } catch (_) {} }
  m = /filename\s*=\s*("([^"]*)"|[^;]+)/i.exec(cd);
  return m ? (m[2] ?? m[1]).trim() : "";
}

B.webRequest.onHeadersReceived.addListener((d) => {
  if (d.statusCode < 200 || d.statusCode >= 300) return;
  const h = {};
  for (const x of d.responseHeaders || []) h[x.name.toLowerCase()] = x.value || "";
  const cd = h["content-disposition"] || "";
  const ct = (h["content-type"] || "").split(";")[0].trim().toLowerCase();
  const attachment = /attachment|filename/i.test(cd);
  const renderable = /^(text\/|image\/|application\/(json|javascript|xml|xhtml|pdf)|$)/.test(ct);
  if (!attachment && renderable) return;      // página/recursos comuns: não é download
  const total = /\/(\d+)$/.exec(h["content-range"] || "");
  dlHeaders.set(d.url, { name: filenameFromCD(cd), size: total ? +total[1] : (+h["content-length"] || -1), mime: ct, t: Date.now() });
  if (dlHeaders.size > DL_HEADERS_MAX) dlHeaders.delete(dlHeaders.keys().next().value);
}, { urls: ["<all_urls>"], types: ["main_frame", "sub_frame", "other", "xmlhttprequest"] }, ["responseHeaders"]);

async function captureDecision(item) {
  const { capture } = await cfg();
  if (!capture) return false;
  const url = item.finalUrl || item.url;
  if (!/^(https?|ftp):/i.test(url)) return false;          // blob:, data: ficam com o navegador
  if (item.byExtensionId && item.byExtensionId === B.runtime.id) return false;
  const now = Date.now();
  for (const [u, t] of skipUntil) if (t < now) skipUntil.delete(u);
  if (skipUntil.has(url) || skipUntil.has(item.url) || skipUntil.has("*")) return false;   // usuário pediu o navegador
  const hdr = dlHeaders.get(url) || dlHeaders.get(item.url) || {};
  const size = item.totalBytes > 0 ? item.totalBytes : (item.fileSize > 0 ? item.fileSize : (hdr.size > 0 ? hdr.size : -1));
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), CAPTURE_TIMEOUT);
  try {
    const { port } = await cfg();
    const r = await fetch(`http://127.0.0.1:${port}/capture`, {
      method: "POST", signal: ctl.signal,
      headers: { "Content-Type": "application/json", "X-LDM-Client": "1" },
      body: JSON.stringify({
        url,
        filename: hdr.name || basename(item.filename),
        referer: item.referrer || "",
        mime: item.mime || hdr.mime || "",
        size,
        cookies: await cookiesFor(url),
        user_agent: navigator.userAgent,
      }),
    });
    return r.ok && (await r.json()).accepted === true;
  } catch (_) {
    return false;   // LDM fechado ou sem resposta: o navegador continua o download normalmente
  } finally {
    clearTimeout(timer);
  }
}

B.downloads.onCreated.addListener(async (item) => {
  if (await captureDecision(item)) {
    try { await B.downloads.cancel(item.id); } catch (_) {}
    try { await B.downloads.erase({ id: item.id }); } catch (_) {}
  }
});

// ---------------------------------------------------------------- sniffer de mídia (modo IDM)
// Como o IDM: observa TODA requisição de mídia que o player faz, remonta arquivos pedidos em fatias
// (Range / &range= do googlevideo) e registra manifests HLS/DASH. O LDM decide o que baixar.
const MEDIA_MAX = 40;
const MEDIA_CT = /^(video\/(?!mp2t)|audio\/(?!mp2t)|application\/(vnd\.apple\.mpegurl|x-mpegurl|dash\+xml|vnd\.yt-ump|octet-stream))/i;
const SEGMENT = /\.(ts|m4s|aac|vtt|webvtt)(\?|$)|\/seg(ment)?[-_]?\d+|\/chunk[-_]?\d+|\/frag(ment)?[-_(]?\d+/i;
const VOLATILE = ["range", "rn", "rbuf", "ump", "srfvp", "bytestart", "byteend", "alr", "cpn", "cver", "altitags", "pot_hint"];
const reqHeaders = new Map();   // requestId -> {referer, origin}

function stripParams(u, names) {
  try {
    const x = new URL(u);
    for (const n of names) x.searchParams.delete(n);
    return x.href;
  } catch (_) { return u; }
}

function classify(d, h) {
  const url = d.url;
  const ct = (h["content-type"] || "").toLowerCase();
  let x;
  try { x = new URL(url); } catch (_) { return null; }
  const q = x.searchParams;
  const cr = h["content-range"] || "";
  const crTotal = /\/(\d+)/.test(cr) ? parseInt(cr.split("/")[1], 10) : -1;
  const len = parseInt(h["content-length"] || "-1", 10);
  // 1) googlevideo / videoplayback (YouTube, Google Drive, Blogger...)
  if (/\/videoplayback/.test(x.pathname)) {
    if (q.get("sabr") === "1" || /vnd\.yt-ump/.test(ct)) {
      return { key: `sabr:${q.get("id") || x.host}`, kind: "sabr", type: "SABR", url: stripParams(url, VOLATILE), size: -1 };
    }
    const mime = q.get("mime") || ct.split(";")[0];
    const itag = q.get("itag") || "";
    const kind = /^audio\//.test(mime) ? "audio" : /^video\//.test(mime) ? "video" : "media";
    return {
      key: `gv:${q.get("id") || ""}:${itag}`, kind, type: mime || "video", itag,
      url: stripParams(url, VOLATILE), size: parseInt(q.get("clen") || crTotal || "-1", 10) || crTotal,
      dur: parseFloat(q.get("dur") || "0") || 0, group: `gv:${q.get("id") || ""}`,
    };
  }
  const isM3u8 = /\.m3u8(\?|$)/i.test(x.pathname) || /mpegurl/.test(ct);
  const isMpd = /\.mpd(\?|$)/i.test(x.pathname) || /dash\+xml/.test(ct);
  if (isM3u8 || isMpd) {
    return { key: `m:${stripParams(url, ["_", "t", "ts", "token_ts"])}`, kind: "manifest", type: isM3u8 ? "HLS" : "DASH", url, size: -1 };
  }
  if (!MEDIA_CT.test(ct) || /octet-stream/.test(ct) && !/\.(mp4|m4v|m4a|webm|mkv|mov|flv|mp3|ogg|opus)(\?|$)/i.test(x.pathname)) return null;
  if (SEGMENT.test(x.pathname) || /mp2t/.test(ct)) return null;
  // 2) arquivo pedido em fatias: remonta pelo total do Content-Range (ou ?range=/bytestart=)
  const full = stripParams(url, ["range", "bytestart", "byteend"]);
  const total = crTotal > 0 ? crTotal : len;
  if (total >= 0 && total < 300 * 1024) return null;            // ícones, prévias, sons de interface
  const mime = ct.split(";")[0];
  return { key: `f:${full}`, kind: /^audio\//.test(mime) ? "audio" : "video", type: mime, url: full, size: total };
}

B.webRequest.onBeforeSendHeaders.addListener(
  (d) => {
    if (d.tabId < 0) return;
    const h = Object.fromEntries((d.requestHeaders || []).map((x) => [x.name.toLowerCase(), x.value || ""]));
    if (h.referer || h.origin) reqHeaders.set(d.requestId, { referer: h.referer || "", origin: h.origin || "" });
  },
  { urls: ["<all_urls>"], types: ["media", "xmlhttprequest", "other", "object"] },
  ["requestHeaders"]
);

B.webRequest.onHeadersReceived.addListener(
  (d) => {
    if (d.tabId < 0 || d.statusCode >= 400) return;
    const h = Object.fromEntries((d.responseHeaders || []).map((x) => [x.name.toLowerCase(), x.value || ""]));
    const m = classify(d, h);
    const rh = reqHeaders.get(d.requestId);
    reqHeaders.delete(d.requestId);
    if (!m) return;
    m.frameId = d.frameId;
    m.ts = Date.now();
    m.source = "rede";
    if (rh) m.headers = rh;
    rememberMedia(d.tabId, m);
  },
  { urls: ["<all_urls>"], types: ["media", "xmlhttprequest", "other", "object"] },
  ["responseHeaders"]
);
for (const ev of ["onErrorOccurred", "onCompleted"]) {
  B.webRequest[ev].addListener((d) => reqHeaders.delete(d.requestId), { urls: ["<all_urls>"] });
}

// Itens achados pelo page_hook.js no conteúdo das respostas (APIs JSON, MPD embutido...)
function fromPage(it, frameId, page) {
  const url = it.url || "";
  let type = it.type || "";
  let kind = it.kind || "";
  if (!kind) {
    if (/\.m3u8(\?|$)/i.test(url)) { kind = "manifest"; type = "HLS"; }
    else if (/\.mpd(\?|$)/i.test(url)) { kind = "manifest"; type = "DASH"; }
    else if (/\.(m4a|mp3|aac|opus|ogg)(\?|$)/i.test(url)) { kind = "audio"; type = "audio"; }
    else { kind = "video"; type = (url.match(/\.(\w{2,4})(\?|$)/) || [])[1] || "video"; }
  }
  const key = url ? `p:${url}` : `pm:${(it.manifest_text || "").length}:${(it.base || "").slice(0, 80)}`;
  return { key, kind, type, url, size: -1, manifest_text: it.manifest_text, base: it.base || page,
           field: it.key || "", frameId, ts: Date.now(), source: "página" };
}

const mediaQueue = new Map();
async function rememberMedia(tabId, m) {
  // serializa as gravações por aba (vários eventos chegam ao mesmo tempo)
  const prev = mediaQueue.get(tabId) || Promise.resolve();
  const next = prev.then(async () => {
    const key = `media_${tabId}`;
    const store = mediaStore();
    const cur = (await store.get({ [key]: [] }))[key];
    const old = cur.find((x) => x.key === m.key);
    const list = cur.filter((x) => x.key !== m.key);
    if (old && old.size > 0 && !(m.size > 0)) m.size = old.size;
    list.unshift(m);
    await store.set({ [key]: list.slice(0, MEDIA_MAX) });
    const visible = list.filter((x) => x.kind !== "sabr").length;
    try {
      await B.action.setBadgeText({ tabId, text: visible ? String(Math.min(visible, 99)) : "" });
      await B.action.setBadgeBackgroundColor({ tabId, color: "#F43F5E" });
    } catch (_) {}
  }).catch(() => {});
  mediaQueue.set(tabId, next);
  return next;
}

B.tabs.onRemoved.addListener((tabId) => mediaStore().remove(`media_${tabId}`));
B.tabs.onUpdated.addListener((tabId, info) => {
  // nova página (não navegação SPA dentro do mesmo site): zera a lista
  if (info.status === "loading" && info.url) {
    mediaStore().get({ [`page_${tabId}`]: "" }).then((o) => {
      const prevOrigin = o[`page_${tabId}`];
      let origin = "";
      try { origin = new URL(info.url).origin; } catch (_) {}
      if (prevOrigin !== origin) mediaStore().remove(`media_${tabId}`);
      mediaStore().set({ [`page_${tabId}`]: origin });
    });
  }
});

// ---------------------------------------------------------------- configuração vinda do LDM (regras, teclas)
async function syncConfig() {
  try {
    const p = await api("/ping");
    await B.storage.local.set({ ldmRules: p.rules || null, ldmKeys: p.keys || null });
  } catch (_) {}
}
syncConfig();
B.runtime.onStartup?.addListener(syncConfig);

// Alt+clique (padrão) = o navegador baixa; Ctrl+Alt+clique (padrão) = força o LDM
const skipUntil = new Map();   // url -> expiração

// ---------------------------------------------------------------- menus de contexto
function setupMenus() {
  B.contextMenus.removeAll(() => {
    B.contextMenus.create({ id: "ldm-link", title: "Baixar com o LDM", contexts: ["link"] });
    B.contextMenus.create({ id: "ldm-media", title: "Baixar esta mídia com o LDM", contexts: ["video", "audio", "image"] });
    B.contextMenus.create({ id: "ldm-selected", title: "Baixar links selecionados com o LDM", contexts: ["selection"] });
    B.contextMenus.create({ id: "ldm-all", title: "Baixar todos os links com o LDM", contexts: ["page"] });
    B.contextMenus.create({ id: "ldm-video", title: "Baixar o vídeo desta página com o LDM", contexts: ["page", "video", "frame", "link"] });
    B.contextMenus.create({ id: "ldm-last-media", title: "Baixar a última mídia detectada com o LDM", contexts: ["page", "video", "audio"] });
  });
}
B.runtime.onInstalled.addListener(setupMenus);
B.runtime.onStartup?.addListener(setupMenus);

async function collectLinks(tabId, selectedOnly) {
  const [res] = await B.scripting.executeScript({
    target: { tabId },
    args: [selectedOnly],
    func: (sel) => {
      let anchors = [...document.querySelectorAll("a[href]")];
      if (sel) {
        const s = window.getSelection();
        anchors = anchors.filter((a) => s && s.containsNode(a, true));
      }
      const media = sel ? [] : [...document.querySelectorAll("video[src],audio[src],source[src]")].map((m) => ({ url: m.src, text: "mídia" }));
      return anchors.map((a) => ({ url: a.href, text: (a.innerText || a.title || "").trim().slice(0, 200) })).concat(media);
    },
  });
  return res?.result || [];
}

B.contextMenus.onClicked.addListener(async (info, tab) => {
  try {
    if (info.menuItemId === "ldm-link") {
      await sendAdd(info.linkUrl, { referer: info.pageUrl, description: info.selectionText || "" });
    } else if (info.menuItemId === "ldm-video") {
      await sendVideo(tab, { frame_url: info.linkUrl || info.frameUrl || info.pageUrl, src: info.srcUrl });
    } else if (info.menuItemId === "ldm-media") {
      await sendAdd(info.srcUrl, { referer: info.pageUrl });
    } else if (info.menuItemId === "ldm-all" || info.menuItemId === "ldm-selected") {
      const links = await collectLinks(tab.id, info.menuItemId === "ldm-selected");
      await api("/links", { page: info.pageUrl, links });
    } else if (info.menuItemId === "ldm-last-media") {
      const key = `media_${tab.id}`;
      const list = (await (B.storage.session ?? B.storage.local).get({ [key]: [] }))[key];
      if (list.length) await sendStream(tab, list[0]);
      else await sendVideo(tab, { frame_url: info.frameUrl || info.pageUrl });
    }
  } catch (e) {
    console.warn("LDM indisponível:", e);
  }
});

// mensagens do popup
B.runtime.onMessage.addListener((msg, _sender, reply) => {
  (async () => {
    try {
      if (msg.op === "ping") reply(await api("/ping"));
      else if (msg.op === "video") reply(await sendVideo(_sender.tab || (await B.tabs.get(msg.tabId)), msg));
      else if (msg.op === "stream") reply(await sendStream(await B.tabs.get(msg.tabId), msg.stream));
      else if (msg.op === "add") reply(await sendAdd(msg.url, msg.extra || {}));
      else if (msg.op === "links") reply(await api("/links", { page: msg.page, links: await collectLinks(msg.tabId, false) }));
      else if (msg.op === "show") reply(await api("/show", {}));
      else if (msg.op === "status") reply(await api("/status"));
      else if (msg.op === "found") {
        for (const it of msg.items || []) await rememberMedia(_sender.tab.id, fromPage(it, _sender.frameId, msg.page));
        reply({ ok: true });
      } else if (msg.op === "skip") {
        skipUntil.set(msg.url, Date.now() + 15000);
        skipUntil.set("*", Date.now() + 2500);
        reply({ ok: true });
      } else if (msg.op === "force") {
        reply(await sendAdd(msg.url, { referer: msg.referer || "", force: true }));
      } else if (msg.op === "config") {
        reply(await B.storage.local.get({ ldmRules: null, ldmKeys: null }));
      }
    } catch (e) {
      reply({ error: String(e) });
    }
  })();
  return true;
});
