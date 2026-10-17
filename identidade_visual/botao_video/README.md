# Nova Identidade Visual — Botão sobre o Vídeo (LDM)

Esta pasta contém os recursos visuais para o **Botão de Captura Flutuante** que a extensão do navegador (`browser_extension/content.js`) injeta sobre os elementos `<video>` em páginas como YouTube, Twitch, Vimeo e portais web.

---

## 🎯 Conceito do Botão
- **Forma:** Pílula escura semitransparente (*capsule pill*) com cantos totalmente arredondados (`border-radius: 9999px`) e efeito de vidro fosco (*frosted glass* / `backdrop-filter: blur(12px)`).
- **Cor de Destaque:** Âmbar (`#F59E0B`), separando visualmente tudo o que é vídeo do download geral (que usa o Vermelho Crimson `#F43F5E`).
- **Comportamento:** Discreto enquanto o vídeo roda, mas ganha brilho âmbar e destaque visual suave ao passar o cursor (*hover*).
- **Estrutura:** 
  1. Ícone da marca em âmbar (`seta.svg`);
  2. Rótulo textual "Baixar este vídeo" (ou "Baixar");
  3. Divisor sutil;
  4. Seletor de qualidade rápida com chevron (`1080p ▾`).

---

## 📁 Arquivos Disponíveis
- **[`seta.svg`](seta.svg):** Ícone vetorial da convergência de 3 faixas em âmbar (`#F59E0B`).
- **[`botao.css`](botao.css):** Folha de estilos completa pronta para injeção no Shadow DOM.
- **[`preview.html`](preview.html):** Demonstração interativa do botão sobre um player de vídeo simulado.

---

## 🔄 Onde substituir no projeto
Em `browser_extension/content.js`:
- Substituir o bloco `<style>` injetado no shadow DOM pelo CSS de `botao.css`.
- Substituir a string do SVG inline pelo conteúdo de `seta.svg`.

