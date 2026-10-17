# Linux Download Manager (LDM)

[English](README.md) · **Português (Brasil)**

Gerenciador de downloads para Linux inspirado no Internet Download Manager. Acelera downloads com várias conexões e baixa vídeos de qualquer site por meio de uma extensão do navegador. Também tem filas, agendador, limitador de velocidade e Site Grabber.

![Janela principal](docs/screenshots/main-dark.png)

## Download

| Sistema | Arquivo |
|---|---|
| **Linux** | [`Linux_Download_Manager-1.4.0-x86_64.AppImage`](https://github.com/jcrodriguesjr0/linux-download-manager/releases/latest) |
| **Windows 10/11** (64 bits) | [`Lunix_Download_Manager-1.4.0-Setup.exe`](https://github.com/jcrodriguesjr0/linux-download-manager/releases/latest) (instalador, sem pedir administrador) ou `…-portable.zip` |

No Windows o programa se chama **Lunix Download Manager**. Como não tem assinatura digital, o SmartScreen avisa na primeira execução: clique em **Mais informações → Executar assim mesmo**. Log de erros: `%LOCALAPPDATA%\LDM\ldm.log`.

### Linux

Arquivo único (~145 MB), sem instalar nada.

Traz Python 3.12, GTK 3, yt-dlp, Deno e ffmpeg.

**Requisitos**
- **Processador:** x86_64 (Intel/AMD de 64 bits). ARM não é suportado.
- **glibc:** 2.38 ou mais nova.
  - Funciona no SteamOS, Ubuntu 24.04+, Linux Mint 22+, Fedora 39+, Debian 13, Arch/Manjaro e openSUSE Tumbleweed.
  - **Não funciona** no Ubuntu 22.04, Linux Mint 21, Debian 12 nem no RHEL/Alma/Rocky 9.
- **Tela:** X11, ou Wayland com XWayland (padrão nos desktops atuais).
- **FUSE:** o `fusermount` é necessário para montar a AppImage. A antiga `libfuse2` não é necessária. Sem FUSE, rode com `--appimage-extract-and-run`.
- **Ícone na bandeja:** funciona no KDE e no Cinnamon. No GNOME puro é preciso a extensão "AppIndicator".

```bash
chmod +x Linux_Download_Manager-1.4.0-x86_64.AppImage
./Linux_Download_Manager-1.4.0-x86_64.AppImage            # abre o programa
./Linux_Download_Manager-1.4.0-x86_64.AppImage install    # cria o atalho no menu de aplicativos
./Linux_Download_Manager-1.4.0-x86_64.AppImage selftest   # diagnóstico dos componentes embutidos
```

Depois, instale a extensão do navegador: [passo a passo](#extensão-do-navegador).

## Funcionalidades

**Motor de download**
- Várias conexões com segmentação dinâmica: a conexão que termina assume metade do maior trecho restante.
- Retomada após pausa, travamento ou reinício do computador.
- HTTP, HTTPS e FTP; streams HLS convertidos para `.mp4`.
- Proxy, logins por site, cookies, referer e User-Agent personalizado.
- Limitador de velocidade global e por arquivo.

**Grabber de vídeo**
- Botão **"Baixar este vídeo"** sobre qualquer `<video>` de qualquer site, inclusive em iframes e em tela cheia. No popup da extensão dá para escolher **Completo** (ícone, texto e resolução) ou **Mini** (só o ícone).
- Escolha de qualidade, somente áudio/MP3, legendas embutidas e playlists inteiras.
- YouTube e cerca de 1.800 sites via yt-dlp. Os streams diretos usam o motor multi-conexão do LDM e são mesclados com ffmpeg.
- **Captura passiva**, como no IDM, para sites que o yt-dlp não conhece:
  - registra as requisições de mídia que o player faz;
  - remonta arquivos baixados em fatias (`range=`);
  - lê as respostas de `fetch`/XHR para achar manifests HLS/DASH escondidos em APIs JSON;
  - marca com ★ o vídeo clicado e separa anúncios.
- Sites que exigem login usam os cookies do navegador.

**Integração com o navegador**
- Captura downloads no Chrome, Edge, Chromium e Firefox, filtrando por tipo de arquivo, tamanho mínimo e sites de exceção.
- Menu de contexto: "Baixar com o LDM", "Baixar todos os links" e "Baixar links selecionados".
- **Alt+clique** deixa o navegador baixar; **Ctrl+Alt+clique** força o LDM. As duas teclas são configuráveis.

**Organização**
- Categorias (Compactados, Documentos, Músicas, Programas, Vídeos), cada uma com suas extensões e pastas.
- Pesquisa, colunas configuráveis e propriedades do arquivo.
- Importação e exportação de listas `.ef2` do IDM e de texto.
- Prévia de ZIP antes de baixar.

**Filas e agendador**
- Várias filas com downloads simultâneos.
- Início e parada em horários ou dias da semana, e sincronização periódica.
- Ao concluir: sair, desligar ou abrir o arquivo.

**Site Grabber**
- Explora um site por níveis de links, tipos de arquivo, caminhos e tamanho, e salva projetos.

**Integração com o desktop**
- Ícone na bandeja e início automático ao ligar o computador (minimizado, opcional).
- Identidade "Fluxo Segmentado": escuro primeiro, com modo claro, ícones próprios e as fontes Inter e JetBrains Mono embutidas. Os arquivos ficam em `identidade_visual/`.
- Notificações e sons; antivírus após o download.

| Botão sobre qualquer player | Escolha da qualidade | Progresso |
|---|---|---|
| ![Botão de vídeo](docs/screenshots/video-button.png) | ![Diálogo de vídeo](docs/screenshots/video.png) | ![Progresso](docs/screenshots/progress.png) |

Modo claro: ![Modo claro](docs/screenshots/main-light.png)

## Extensão do navegador

É a extensão que faz o LDM capturar downloads e mostrar o botão **"Baixar este vídeo"** sobre os players. Ela ainda não está nas lojas dos navegadores, então a instalação é manual, uma vez só. Leva uns dois minutos.

### Passo 1: encontre a pasta da extensão

O jeito mais fácil é pelo próprio programa: **menu ☰ → Ajuda → Extensão do navegador...**. A janela mostra a pasta exata, e o botão **Abrir pasta** abre ela.

| Como você usa o LDM | Pasta da extensão |
|---|---|
| AppImage (Linux) | `~/Documents/LinuxDownloadManager-extensao`. O menu acima cria a pasta, então abra o menu uma vez antes. |
| Instalador do Windows | `%LOCALAPPDATA%\Programs\Lunix Download Manager\_internal\browser_extension` |
| Windows instalado "para todos os usuários" | `C:\Program Files\Lunix Download Manager\_internal\browser_extension` |
| Zip portátil do Windows | `<pasta descompactada>\_internal\browser_extension` |
| Código-fonte | `browser_extension/` deste repositório |

Também dá para baixar `ldm-browser-extension-<versão>.zip` na [página de releases](https://github.com/jcrodriguesjr0/linux-download-manager/releases/latest) e descompactar numa pasta sua.

> **Não mova nem apague a pasta depois.** O navegador carrega a extensão dessa pasta toda vez que abre; se ela sumir, a extensão para de funcionar.

### Passo 2: instale no navegador

**Google Chrome, Brave, Chromium, Vivaldi, Opera**
1. Digite `chrome://extensions` na barra de endereço e tecle Enter. No Brave também funciona `brave://extensions`.
2. Ligue o **Modo do desenvolvedor**, no botão do canto superior direito.
3. Clique em **Carregar sem compactação**.
4. Escolha a pasta da extensão do passo 1 (a própria pasta, a que contém o `manifest.json`) e confirme.
5. Clique no ícone de quebra-cabeça da barra e **fixe** o "Linux Download Manager" (ou "Lunix") para o ícone ficar sempre visível.

**Microsoft Edge**
1. Acesse `edge://extensions`.
2. Ligue o **Modo de desenvolvedor**. Nas versões novas ele fica na barra lateral esquerda; se ela estiver escondida, clique em ☰ no canto superior esquerdo.
3. Clique em **Carregar sem pacote** (o nome varia com a versão: *Carregar descompactada* ou, em inglês, *Load unpacked*) e escolha a pasta da extensão.
4. Fixe o ícone pelo quebra-cabeça, como acima.

**Firefox**
1. Acesse `about:debugging#/runtime/this-firefox`.
2. Clique em **Carregar extensão temporária...**.
3. Escolha o arquivo `manifest.json` dentro da pasta da extensão.

> O Firefox só aceita extensões não assinadas de forma temporária: **ela some quando o Firefox é reiniciado** e precisa ser carregada de novo. A versão permanente depende de publicar no addons.mozilla.org, o que está nos planos.

### Passo 3: confira se funcionou

1. Abra o LDM.
2. Clique no ícone do LDM na barra do navegador: o popup deve mostrar **"conectado · v1.4.0"**. Se aparecer **"LDM fechado"**, o programa não está aberto.
3. Abra qualquer página com vídeo e passe o mouse sobre o player: o botão **"Baixar este vídeo"** aparece no canto superior direito do vídeo.
4. Baixe qualquer arquivo de 50 MB ou mais: o LDM assume o download.

### Opções do popup
- **Capturar downloads do navegador:** liga ou desliga a captura automática.
- **Mostrar "Baixar este vídeo" sobre os players:** mostra ou esconde o botão nos vídeos.
- **Tamanho do botão:** **Completo** (ícone, texto e resolução) ou **Mini** (só o ícone, num círculo pequeno).
- **Alt+clique** num link deixa o navegador baixar; **Ctrl+Alt+clique** força o LDM.

### Atualizar
Depois de instalar uma versão nova do LDM, abra a página de extensões (`chrome://extensions` ou `edge://extensions`) e clique em **↻ Recarregar** no cartão do LDM; depois recarregue as abas abertas. Na AppImage, abra **☰ → Ajuda → Extensão do navegador** uma vez para a pasta ser atualizada.

### Problemas comuns
- **O navegador baixou em vez do LDM:** o arquivo tinha menos de 50 MB (regra padrão, que se muda em **Opções → Tipos de arquivo**), o LDM estava fechado ou a captura está desligada no popup.
- **Aviso de "extensões do modo de desenvolvedor":** é normal em extensões instaladas à mão; mantenha ativada.
- **Navegadores Flatpak (SteamOS, Fedora Silverblue...):** use a pasta `~/Documents/LinuxDownloadManager-extensao`. O navegador Flatpak consegue ler Documentos, mas não o interior da AppImage.
- **Porta:** a extensão conversa com o LDM em `127.0.0.1:9614`. Se você mudar a porta no LDM, mude também no popup.

### Como ela conversa com o LDM
A extensão usa uma API local em `127.0.0.1:9614`, por isso funciona também com navegadores Flatpak, que não conseguem executar hosts de native messaging. A API só aceita requisições de origem `chrome-extension://` ou `moz-extension://`, ou de clientes locais que enviam o cabeçalho `X-LDM-Client` sem `Origin`. Páginas web ficam bloqueadas.

## Rodar pelo código-fonte

Requisitos:
- Python 3.10+ com GTK 3 (PyGObject); só a biblioteca padrão é usada.
- Opcionais: `ffmpeg` (mesclagem e HLS), `yt-dlp` (sites de vídeo), `canberra-gtk-play` (sons) e `notify-send` (notificações).

```bash
python3 ldm.py                 # interface
python3 ldm.py --tray          # inicia minimizado na bandeja
python3 ldm.py install         # cria o atalho no menu de aplicativos
python3 ldm.py add URL         # envia uma URL para a instância aberta
python3 ldm.py video URL       # baixa o vídeo da página (abre a escolha de qualidade)
python3 ldm.py get URL -o ~/Downloads -c 8 -l 2048   # só terminal: 8 conexões, limite de 2 MB/s
```

**yt-dlp:** o LDM procura nesta ordem:
1. o caminho definido em Opções → Vídeo;
2. a cópia embutida na AppImage;
3. `~/.local/share/ldm/ytdlp`;
4. o `PATH`;
5. uma distrobox indicada nas opções (útil em sistemas imutáveis como o SteamOS).

Use **Opções → Vídeo → Instalar/atualizar yt-dlp** sempre que um site parar de funcionar.

As configurações ficam em `~/.config/ldm/settings.json`. A lista de downloads, as filas, os temporários e os projetos do grabber ficam em `~/.local/share/ldm/`.

## Estrutura

```
ldm.py                 lançador e CLI
ldm/engine.py          motor multi-conexão (segmentação dinâmica, retomada, arquivo .part esparso)
ldm/media.py           grabber de vídeo: yt-dlp, qualidades, motor nativo + ffmpeg, captura passiva
ldm/hls.py             HLS -> mp4 sem yt-dlp (alternativa)
ldm/net.py             HTTP/FTP, proxy, logins por site, limitador de velocidade, prévia de ZIP
ldm/manager.py         lista persistente, filas, agendador, ações ao concluir
ldm/grabber.py         Site Grabber
ldm/server.py          API local para a extensão e a CLI
ldm/gui/               janelas e diálogos GTK 3
browser_extension/     extensão MV3 (Chrome/Edge/Firefox): botão sobre o vídeo, sniffer de rede, hook na página
packaging/appimage/    script de geração da AppImage
identidade_visual/     logo, ícones, cores e capturas de tela
tests/                 testes unitários e teste ponta a ponta no navegador
```

## Testes

```bash
python3 -m unittest discover -s tests -v
```

O `tests/e2e_browser.py` carrega a extensão num Chromium real com Playwright e roda 12 cenários: botão na página, sniffer, captura de download, player MSE, APIs JSON, MPD embutido, remontagem de `range=` e teclas de captura. Para rodar, aponte `PLAYWRIGHT_BROWSERS_PATH` para os navegadores do Playwright.

## Gerar a AppImage

No Ubuntu 24.04 (pode ser numa distrobox), com `python3-gi python3-gi-cairo gir1.2-gtk-3.0 librsvg2-common libgdk-pixbuf2.0-bin python3-pip`:

```bash
python3 packaging/appimage/build_appimage.py      # resultado em dist/
```

**Windows:** gerado pelo GitHub Actions (`.github/workflows/windows.yml`): MSYS2 + PyInstaller + Inno Setup; depois o instalador é instalado e testado numa máquina Windows. Localmente, num shell MSYS2 UCRT64: `python packaging/windows/build.py`.

## Limitações

- Conteúdo com DRM (Netflix, Prime Video, Disney+) não pode ser baixado.
- Quando o YouTube entrega um vídeo só pelo protocolo SABR/UMP, não há link reaproveitável para capturar; esses vídeos são baixados pelo yt-dlp.

## Componentes de terceiros na AppImage

| Componente | Licença |
|---|---|
| [Python](https://www.python.org/) | PSF |
| [GTK 3](https://gtk.org/), GLib, PyGObject | LGPL-2.1+ |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Unlicense |
| [Deno](https://deno.com/) | MIT |
| Fontes [Inter](https://rsms.me/inter/) e [JetBrains Mono](https://www.jetbrains.com/lp/mono/) (`data/fonts`) | SIL OFL 1.1 |
| [FFmpeg](https://ffmpeg.org/), build estático de [John Van Sickle](https://johnvansickle.com/ffmpeg/) | GPL-3.0; código-fonte nos links |

## Licença

[MIT](LICENSE). O LDM é um projeto independente, sem vínculo com a Tonec Inc. ou com o Internet Download Manager.
