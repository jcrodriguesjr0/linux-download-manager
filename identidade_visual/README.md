# Nova Identidade Visual do Linux Download Manager (LDM)

> **Status:** aplicada a partir da versão 1.3.0. No código, a paleta e o CSS estão em `ldm/gui/theme.py`, a "linha de download viva" em `ldm/gui/live.py`, o logo e os ícones em `data/` (`data/icons/ldm-*.svg`) e as fontes em `data/fonts/`. Capturas reais em [`docs/screenshots/`](../docs/screenshots/).

Este diretório contém a especificação e todos os arquivos vetoriais e rasterizados da **nova identidade visual** do **Linux Download Manager (LDM)**.

A nova identidade afasta o LDM da estética de clone do IDM de 2005 e o transforma em um **aplicativo Linux moderno**, nativo para ambientes GNOME, KDE Plasma e SteamOS (Steam Deck).

---

## 💡 Conceito Central: "Fluxo Segmentado"
O símbolo do LDM traduz visualmente a principal vantagem do software: **várias conexões simultâneas de rede convergindo em um único arquivo baixado na bandeja**.
- Três canais verticais em degradê descem e se juntam unificados em uma seta voltada para a linha receptora de base.
- O usuário entende o funcionamento veloz e multi-thread de forma instantânea sem precisar de textos explicativos.

---

## 🎨 Paleta Oficial Aprovada

Pensada prioritariamente para tema escuro (*Dark Mode* / Steam Deck / KDE escuro):

| Papel | Cor | Amostra | Uso |
|---|---|:---:|---|
| **Base** | `#141316` | Grafite Carbono | Fundo das janelas e diálogos |
| **Superfície** | `#1E1A1E` | Grafite Suave | HeaderBar, painel lateral e cartões |
| **Borda / Divisor** | `#382229` | Contorno Sutil | Separação de áreas e contorno do squircle |
| **Primária (Download)** | `#F43F5E` | Vermelho Rubro / Crimson | Marca oficial, botões de ação e segmentos de download |
| **Degradê da Marca** | `#FDA4AF` → `#FB7185` → `#F43F5E` → `#E11D48` | Degradê Rubro | Fluxos do logo e indicadores de alta velocidade |
| **Destaque (Vídeo)** | `#F59E0B` | Âmbar Elétrico | Tudo relacionado a vídeo: botão sobre players, capturas e filtros |
| **Sucesso** | `#22C55E` | Verde | Downloads concluídos e validação de hash |
| **Erro** | `#EF4444` | Vermelho Alerta | Falhas de conexão ou links expirados |

> **Nota de Design:** O âmbar separa com precisão as duas vocações do software: **Vermelho Rubro é Download**, **Âmbar é Vídeo**. O azul genérico do IDM 2005 foi totalmente substituído.

---

## 📁 Estrutura de Pastas e Recursos Criados

| Pasta | Conteúdo e Formatos | Descrição |
|---|---|---|
| **[`logo/`](logo/)** | `ldm.svg`, `ldm.png` (16, 32, 64, 128, 256, 512 px), `ldm-symbolic.svg`, `ldm-tray.png` | Logo do app em squircle GNOME/KDE e versão simbólica para a bandeja. |
| **[`extensao/`](extensao/)** | `icon16.png`, `icon32.png`, `icon48.png`, `icon128.png`, `icon.svg` + versões monocromáticas | Ícones para navegadores (Chrome, Firefox, Brave) prontos para o `manifest.json`. |
| **[`icones_sistema/`](icones_sistema/)** | 21 ícones em `.svg`, `.png` (24 px) e `@2x.png` (48 px) | Conjunto próprio de ícones de linha (traço 2px, grade 24px) que elimina o tema WhiteSur. |
| **[`botao_video/`](botao_video/)** | `seta.svg`, `botao.css`, `preview.html` | Pílula escura semitransparente em vidro fosco com logo em âmbar injetada sobre players. |
| **[`telas/`](telas/)** | `main.png`, `progress.png`, SVGs vetoriais dos mockups | Mockups da nova janela HeaderBar e da assinatura "Linha de Download Viva". |
| **[`paleta.json`](paleta.json)** | JSON com definições completas | Tokens de cores, papéis semânticos e tipografia. |

---

## 🛠️ Onde Substituir ao Aplicar no Projeto

Quando for reconstruir ou atualizar o código do LDM, utilize esta tabela prática:

| Elemento | Onde Substituir no Código | Arquivo da Nova Identidade |
|---|---|---|
| **Logo do AppImage e Menu** | `data/ldm.svg` e `data/ldm.png` | `logo/ldm.svg` e `logo/ldm.png` |
| **Ícones da Extensão** | `browser_extension/icon*.png` | `extensao/icon*.png` |
| **Botão Flutuante de Vídeo** | `browser_extension/content.js` (CSS e SVG inline) | `botao_video/botao.css` e `botao_video/seta.svg` |
| **Popup da Extensão** | `:root` em `browser_extension/popup.html` | Variáveis de `paleta.json` |
| **Badge da Extensão** | `setBadgeBackgroundColor` em `browser_extension/background.js` | Cor `#F43F5E` |
| **Linha/Mapa de Conexões** | `cr.set_source_rgb(...)` em `ldm/gui/dialogs.py` | Cores de `mapa_de_conexoes` em `paleta.json` |
| **Ícones da Barra e Árvore** | `ldm/gui/app.py` (`_build_toolbar`, `refresh_tree`) | Carregar ícones autorais de `icones_sistema/` |

