# Nova Identidade Visual — Extensão do Navegador (LDM)

Esta pasta contém os ícones oficiais atualizados para a extensão do navegador (`browser_extension/`) do **Linux Download Manager (LDM)**, baseados no conceito moderno de **"Fluxo Segmentado"** com a paleta aprovada **Vermelho Rubro / Crimson Neon**.

---

## 💡 Conceito: "Fluxo Segmentado"
- **Metáfora visual:** Três faixas paralelas verticais em degradê descem e convergem unificadas em uma seta apontando para a bandeja de base.
- **Significado imediato:** Representa o motor multi-conexão em ação — múltiplos canais de dados que se unem para formar um único arquivo íntegro.
- **Forma do contêiner:** Squircle (quadrado de cantos arredondados) seguindo o padrão moderno de design do **GNOME HIG e KDE**.

---

## 🎨 Paleta Aprovada
| Elemento | Cor / Degradê | Função |
|---|---|---|
| Fundo (Squircle) | `#141316` → `#1E1A1E` (Borda `#382229`) | Base grafite carbono (Dark mode nativo) |
| Segmentos & Seta | `#FDA4AF` → `#FB7185` → `#F43F5E` → `#E11D48` | Vermelho rubro / Crimson elétrico (marca oficial) |
| Bandeja de Base | `#BE123C` → `#FB7185` → `#BE123C` | Linha de recepção do arquivo baixado |

---

## 📁 Arquivos Oficiais Gerados

### 1. Padrão Colorido (Squircle Grafite + Vermelho Crimson)
Prontos para uso no `manifest.json`:
- **[`icon16.png`](icon16.png)** (16×16 px) — Otimizado pixel-a-pixel para a barra de ferramentas padrão (1x).
- **[`icon32.png`](icon32.png)** (32×32 px) — Ícone nítido para telas HiDPI / Steam Deck.
- **[`icon48.png`](icon48.png)** (48×48 px) — Página de extensões do navegador (`chrome://extensions` / `about:addons`).
- **[`icon128.png`](icon128.png)** (128×128 px) — Chrome Web Store, Firefox Add-ons e instalador.
- **[`icon.svg`](icon.svg)** — Vetor mestre escalável.

### 2. Variante Monocromática / Fundo Transparente
- **`icon16-mono.png`** (16×16 px)
- **`icon32-mono.png`** (32×32 px)
- **`icon48-mono.png`** (48×48 px)
- **`icon128-mono.png`** (128×128 px)
- **`icon-mono.svg`** — Vetor mestre monocromático.

---

## 🔄 Como aplicar na extensão
```bash
cp icon16.png icon32.png icon48.png icon128.png ../../browser_extension/
```
