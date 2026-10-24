# Linux Download Manager (LDM)

[English](README.md) · **Português (Brasil)**

Gerenciador e acelerador de downloads gratuito, alternativa ao **Internet Download Manager (IDM)** para **Linux**, **Steam Deck** e **Windows**. Baixa com várias conexões, retoma downloads interrompidos e baixa vídeos de qualquer site com um botão sobre o player.

![Janela principal](docs/screenshots/main-dark.png)

## Download

| Sistema | Arquivo |
|---|---|
| **Linux** (x86_64) | [`Linux_Download_Manager-x86_64.AppImage`](https://github.com/jcrodriguesjr0/linux-download-manager/releases/latest) |
| **Windows 10/11** | [`Lunix_Download_Manager-Setup.exe`](https://github.com/jcrodriguesjr0/linux-download-manager/releases/latest) ou `portable.zip` |

- **Linux:** `chmod +x` no arquivo e abra. Precisa de glibc 2.38+ (SteamOS, Ubuntu 24.04+, Mint 22+, Fedora 39+, Debian 13, Arch). Para criar o atalho no menu: `./Linux_Download_Manager-*.AppImage install`.
- **Windows:** o programa se chama **Lunix Download Manager**. O SmartScreen avisa na primeira vez: **Mais informações → Executar assim mesmo**.

## Extensão do navegador

Necessária para o LDM capturar downloads e mostrar o botão de vídeo. Ela já vem com o programa; o LDM avisa na primeira execução e mostra a pasta em **☰ → Ajuda → Extensão do navegador**.

1. Abra `chrome://extensions` (Chrome, Brave) ou `edge://extensions` (Edge).
2. Ligue o **Modo do desenvolvedor**.
3. Clique em **Carregar sem compactação** e escolha a pasta da extensão.

**Firefox:** `about:debugging#/runtime/this-firefox` → **Carregar extensão temporária** → `manifest.json` (some ao reiniciar o Firefox).

Para conferir, clique no ícone do LDM na barra do navegador: deve aparecer **"conectado"**. Arquivos a partir de 50 MB vão para o LDM; **Alt+clique** deixa o navegador baixar, **Ctrl+Alt+clique** força o LDM.

## Funcionalidades

- **Downloads acelerados:** várias conexões com segmentação dinâmica, retomada após queda ou reinício, HTTP/HTTPS/FTP, proxy e limitador de velocidade.
- **Vídeos:** botão "Baixar este vídeo" sobre qualquer player, escolha de qualidade, MP3, legendas e playlists; YouTube e ~1.800 sites via yt-dlp, mais captura de HLS/DASH.
- **Organização:** categorias, filas, agendador, desligar ao terminar, importação de listas do IDM.
- **Site Grabber**, ícone na bandeja, início com o sistema, modo escuro e claro.

| Botão sobre o player | Escolha da qualidade | Progresso |
|---|---|---|
| ![Botão de vídeo](docs/screenshots/video-button.png) | ![Diálogo de vídeo](docs/screenshots/video.png) | ![Progresso](docs/screenshots/progress.png) |

## Para desenvolvedores

```bash
python3 ldm.py                              # roda pelo código (Python 3.10+, GTK 3 / PyGObject)
python3 -m unittest discover -s tests       # testes
python3 linux/build_appimage.py             # AppImage (Ubuntu 24.04) em linux/dist/
```

O Windows é gerado pelo GitHub Actions (`windows/`, MSYS2 + PyInstaller + Inno Setup).

```
ldm/              código do programa (motor, vídeo, API local, interface GTK)
browser_extension/ extensão MV3 (Chrome, Edge, Firefox)
linux/            build da AppImage
windows/          build do Windows
```

## Licença

[MIT](LICENSE). Projeto independente, sem vínculo com a Tonec Inc. ou com o Internet Download Manager. Inclui yt-dlp (Unlicense), FFmpeg (GPL-3.0), Deno (MIT), GTK/PyGObject (LGPL) e as fontes Inter e JetBrains Mono (OFL).
