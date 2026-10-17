# Nova Identidade Visual — Logo Oficial do LDM

Esta pasta contém o **Logo Oficial** do **Linux Download Manager (LDM)**, redesenhado para substituir o círculo azul genérico herdado da era IDM 2005.

---

## 🎯 Conceito do Logo: "Fluxo Segmentado"
- **Forma do Contêiner:** Squircle (superelipse com cantos arredondados) no padrão moderno de ícones de aplicações para **GNOME HIG e KDE Plasma**.
- **Símbolo Central:** Três canais verticais paralelos em degradê (as conexões simultâneas do download multi-thread) convergindo unificadas em uma ponta de seta voltada para a linha de base (a bandeja receptora).
- **Cores Oficiais:**
  - **Fundo do Squircle:** `#141316` → `#1E1A1E` com contorno sutil `#382229` e reflexo de 16% em `#FB7185`.
  - **Fluxos & Seta:** Degradê de alto contraste `#FDA4AF` → `#FB7185` → `#F43F5E` → `#E11D48`.
  - **Bandeja:** `#BE123C` → `#FB7185` → `#BE123C`.

---

## 📁 Arquivos Disponíveis

| Arquivo | Dimensões | Uso no Projeto |
|---|---|---|
| **[`ldm.svg`](ldm.svg)** | Vetor SVG Mestre | Substitui `data/ldm.svg` (menu de aplicativos, AppImage, janelas) |
| **[`ldm.png`](ldm.png)** | 128×128 px | Substitui `data/ldm.png` (.DirIcon da AppImage) |
| **`ldm_512.png`** | 512×512 px | Resolução Ultra-HD para lojas de software (Flathub, AppCenter) |
| **`ldm_256.png`** | 256×256 px | Resolução padrão para lançadores de sistemas HiDPI / SteamOS |
| **`ldm_64.png`** | 64×64 px | Miniatura de desktop |
| **`ldm_32.png`** | 32×32 px | Barra de tarefas e janelas |
| **`ldm-symbolic.svg`** | Vetor SVG | Versão simbólica monocromática com fundo transparente |
| **`ldm-tray.png`** | 24×24 px | Ícone para a bandeja do sistema (*system tray*) |

---

## 🔄 Onde substituir no projeto:
- `data/ldm.svg` ← substituir por `ldm.svg`
- `data/ldm.png` ← substituir por `ldm.png`
- Na barra de status / bandeja (`ldm/gui/app.py`), carregar o `ldm.svg` ou `ldm-tray.png` em vez do genérico `folder-download`.

