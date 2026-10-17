# Identidade visual do Linux Download Manager

Cópia de todas as imagens, cores e ícones que o programa e a extensão usam hoje. **É só referência:** o código continua lendo os originais (veja "Onde substituir").

## Pastas

| Pasta | Conteúdo | Original no projeto |
|---|---|---|
| `logo/` | `ldm.svg` (128×128) e `ldm.png` | `data/` |
| `extensao/` | `icon16/32/48/128.png` | `browser_extension/` |
| `botao_video/` | `seta.svg` e `botao.css` do botão "Baixar este vídeo" | embutidos em `browser_extension/content.js` |
| `icones_sistema/` | 21 ícones do tema do sistema (WhiteSur-light) usados na barra, na árvore e nas janelas. **Não vão para o Git** (tema GPL-3.0 de terceiros) | não fazem parte do projeto: o GTK pega do tema instalado |
| `telas/` | capturas das janelas (principal, vídeo, progresso, opções, agendador, grabber, AppImage) | — |
| `paleta.json` | todas as cores usadas | — |

## Logo
Círculo com gradiente vertical `#3fa0ff` → `#0b5fc4`, contorno `#08458f` de 4 px, seta para baixo branca e barra branca embaixo. É a cor de marca usada em todo o resto.

## Onde cada imagem aparece
- **`data/ldm.svg`:**
  - ícone do menu de aplicativos, do início automático e da AppImage (`ldm/autostart.py`, `packaging/appimage/build_appimage.py`);
  - ícone da bandeja (`ldm/gui/app.py`, constante `ICON`).
- **`data/ldm.png`:** `.DirIcon` da AppImage (miniatura no gerenciador de arquivos).
- **`browser_extension/icon*.png`:** ícone da extensão e do botão na barra do navegador (`manifest.json`).
- **Ícones do tema** (`icones_sistema/`, referenciados pelo nome):

| Onde | Ícones |
|---|---|
| Barra de ferramentas | `list-add` (Adicionar URL), `video-x-generic` (Baixar vídeo), `media-playback-start` (Retomar), `media-playback-pause` (Parar), `media-playback-stop` (Parar todos), `edit-delete` (Excluir), `edit-clear-all` (Excluir concluídos), `preferences-system` (Opções), `alarm-symbolic`/`appointment-new` (Agendador), `go-next` (Iniciar fila), `process-stop` (Parar fila), `speedometer`/`network-wireless` (Limitador), `network-server` (Grabber) |
| Árvore lateral | `folder`, `folder-download`, `folder-documents`, `view-list-symbolic`, `view-list`, `network-server` |
| Janelas | `folder-download` (janela principal, progresso e "Sobre"; também é a reserva da bandeja), `video-x-generic` (janela de vídeo e miniatura) |
| Lista de downloads | ícone por tipo de arquivo, vindo do sistema (`text-x-generic` como padrão) |

## Onde substituir ao reconstruir
| Elemento | Arquivo/linha |
|---|---|
| Logo | trocar `data/ldm.svg` e `data/ldm.png` (mesmo nome) |
| Ícones da extensão | trocar `browser_extension/icon*.png` (mesmos tamanhos) |
| Botão sobre o vídeo | CSS e SVG em `browser_extension/content.js` (bloco `<style>`) |
| Popup da extensão | variáveis `:root` em `browser_extension/popup.html` |
| Badge da extensão | `setBadgeBackgroundColor` em `browser_extension/background.js` |
| Mapa de conexões | `cr.set_source_rgb(...)` em `ldm/gui/dialogs.py` (classe do mapa) |
| Ícones da barra/árvore | nomes em `ldm/gui/app.py` (`_build_toolbar`, `refresh_tree`) |

## Observações
- **Logo do LDM fora das janelas.** As janelas e o "Sobre" usam o ícone genérico `folder-download` do tema, não o logo. Numa reconstrução, vale passar a usar o logo nesses lugares.
- **Ícones do tema mudam de computador para computador.** Os de `icones_sistema/` são do tema WhiteSur (GPL-3.0) instalado neste Steam Deck; em outra máquina aparecem os do tema dela. Para uma identidade própria e fixa, crie ícones e carregue-os de `data/` em vez de usar nomes do tema.
- **Modo escuro** usa a variante escura do tema GTK (`gtk_application_prefer_dark_theme`); não há CSS próprio no programa.
