const B = globalThis.browser ?? globalThis.chrome;
const $ = (id) => document.getElementById(id);
const send = (msg) => new Promise((res) => B.runtime.sendMessage(msg, res));

function fmt(n) {
  if (!(n > 0)) return "";
  const u = ["B", "KB", "MB", "GB"];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i ? 1 : 0)} ${u[i]}`;
}

(async () => {
  const [tab] = await B.tabs.query({ active: true, currentWindow: true });
  const c = await B.storage.local.get({ port: 9614, capture: true, overlay: true, overlay_size: "full" });
  $("capture").checked = c.capture;
  $("overlay").checked = c.overlay;
  const sizeBox = $("sizebox");
  const syncSize = () => sizeBox.style.opacity = $("overlay").checked ? "1" : ".4";
  $("overlay").onchange = (e) => { B.storage.local.set({ overlay: e.target.checked }); syncSize(); };
  for (const r of document.querySelectorAll("input[name=osize]")) {
    r.checked = r.value === c.overlay_size;
    r.onchange = () => B.storage.local.set({ overlay_size: r.value });
  }
  syncSize();
  $("video").onclick = async () => {
    $("video").textContent = "Enviando...";
    const r = await send({ op: "video", tabId: tab.id, frame_url: tab.url });
    $("video").textContent = r && !r.error ? "Enviado ao LDM ✓" : "LDM não está aberto";
    if (r && !r.error) setTimeout(() => window.close(), 700);
  };
  $("port").value = c.port;
  $("capture").onchange = (e) => B.storage.local.set({ capture: e.target.checked });
  $("port").onchange = (e) => B.storage.local.set({ port: parseInt(e.target.value, 10) || 9614 });

  const p = await send({ op: "ping" });
  $("st").textContent = p && !p.error ? `conectado · v${p.version}` : "LDM fechado";
  if (p && p.name) $("appname").textContent = p.name;   // "Linux" ou "Lunix" Download Manager

  const key = `media_${tab.id}`;
  const list = (await (B.storage.session ?? B.storage.local).get({ [key]: [] }))[key];
  if (list.length) {
    const box = $("media");
    box.textContent = "";
    for (const m of list) {
      const row = document.createElement("div");
      row.className = "m";
      const name = decodeURIComponent(new URL(m.url).pathname.split("/").pop() || m.url);
      const span = document.createElement("span");
      span.title = m.url;
      span.textContent = `${m.type} ${fmt(m.size)} · ${name}`;
      const b = document.createElement("button");
      b.textContent = "Baixar";
      b.onclick = async () => {
        await send({ op: "stream", tabId: tab.id, stream: m });
        window.close();
      };
      row.append(span, b);
      box.append(row);
    }
  }
  $("all").onclick = async () => { await send({ op: "links", tabId: tab.id, page: tab.url }); window.close(); };
  $("show").onclick = async () => { await send({ op: "show" }); window.close(); };
})();
