# Linux Download Manager (LDM)

**English** · [Português (Brasil)](README.pt-BR.md)

A download manager for Linux inspired by Internet Download Manager. It speeds up downloads with multiple connections, grabs videos from any website through a browser extension, and includes queues, a scheduler, a speed limiter and a site grabber.

![Main window](docs/screenshots/main-dark.png)

> The interface is in Brazilian Portuguese. English covers menus and columns only.

## Download

| System | File |
|---|---|
| **Linux** | [`Linux_Download_Manager-1.4.0-x86_64.AppImage`](https://github.com/jcrodriguesjr0/linux-download-manager/releases/latest) |
| **Windows 10/11** (64-bit) | [`Lunix_Download_Manager-1.4.0-Setup.exe`](https://github.com/jcrodriguesjr0/linux-download-manager/releases/latest) (installer, no admin rights) or `…-portable.zip` |

On Windows the app is called **Lunix Download Manager**. Being unsigned, Windows SmartScreen shows a warning on first run: click **More info → Run anyway**. Error log: `%LOCALAPPDATA%\LDM\ldm.log`.

### Linux

Single file (~145 MB), nothing to install.

It bundles Python 3.12, GTK 3, yt-dlp, Deno and ffmpeg.

**Requirements**
- **CPU:** x86_64 (Intel/AMD 64-bit). ARM is not supported.
- **glibc:** 2.38 or newer.
  - Works on SteamOS, Ubuntu 24.04+, Linux Mint 22+, Fedora 39+, Debian 13, Arch/Manjaro and openSUSE Tumbleweed.
  - **Does not work** on Ubuntu 22.04, Linux Mint 21, Debian 12 or RHEL/Alma/Rocky 9.
- **Display:** X11, or Wayland with XWayland (standard on current desktops).
- **FUSE:** `fusermount` is needed to mount the AppImage. The old `libfuse2` is not required. Without FUSE, run it with `--appimage-extract-and-run`.
- **Tray icon:** works on KDE and Cinnamon. Plain GNOME needs the "AppIndicator" extension.

```bash
chmod +x Linux_Download_Manager-1.4.0-x86_64.AppImage
./Linux_Download_Manager-1.4.0-x86_64.AppImage            # open the program
./Linux_Download_Manager-1.4.0-x86_64.AppImage install    # add it to the application menu
./Linux_Download_Manager-1.4.0-x86_64.AppImage selftest   # check the bundled components
```

Then install the browser extension: [step-by-step guide](#browser-extension).

## Features

**Download engine**
- Multiple connections with dynamic segmentation: when a connection finishes, it takes over half of the largest remaining part.
- Resume after pause, crash or reboot.
- HTTP, HTTPS and FTP; HLS streams to `.mp4`.
- Proxy, per-site logins, cookies, referer and custom User-Agent.
- Global and per-file speed limiter.

**Video grabber**
- A **"Download this video"** button over any `<video>` on any site, including iframes and fullscreen. Choose **Full** (icon + text + resolution) or **Mini** (icon only) in the extension popup.
- Quality selection, audio-only/MP3, embedded subtitles and whole playlists.
- YouTube and about 1,800 sites via yt-dlp. Direct streams use LDM's multi-connection engine and are merged with ffmpeg.
- **Passive capture**, as IDM does, for sites yt-dlp does not know:
  - records the media requests the player makes;
  - reassembles files downloaded in slices (`range=`);
  - reads `fetch`/XHR responses to find HLS/DASH manifests hidden in JSON APIs;
  - marks the clicked video with ★ and separates ads.
- Sites that need a login use the browser's cookies.

**Browser integration**
- Captures downloads in Chrome, Edge, Chromium and Firefox, filtered by file type, minimum size and exception sites.
- Context menu: "Download with LDM", "Download all links", "Download selected links".
- **Alt+click** lets the browser download; **Ctrl+Alt+click** forces LDM. Both keys are configurable.

**Organization**
- Categories (Compressed, Documents, Music, Programs, Video) with their own extensions and folders.
- Search, configurable columns, file properties.
- Import/export of IDM `.ef2` and plain-text lists.
- ZIP preview before downloading.

**Queues and scheduler**
- Multiple queues with parallel downloads.
- Start and stop at set times or on set weekdays, and periodic re-sync.
- After finishing: quit, shut down or open the file.

**Site grabber**
- Crawl a site by link depth, file types, paths and size, and save projects.

**Desktop integration**
- Tray icon, optional start at login (minimized).
- Dark-first "Segmented Flow" design with light mode, own icon set and bundled Inter / JetBrains Mono fonts. Assets live in `identidade_visual/`.
- Notifications and sounds; antivirus scan after a download.

| Video button on any player | Quality selection | Progress |
|---|---|---|
| ![Video button](docs/screenshots/video-button.png) | ![Video dialog](docs/screenshots/video.png) | ![Progress](docs/screenshots/progress.png) |

Light mode: ![Light mode](docs/screenshots/main-light.png)

## Browser extension

The extension is what makes LDM capture downloads and show the **"Download this video"** button on players. It is not on the browser stores yet, so it is installed manually, once. It takes about two minutes.

### Step 1: find the extension folder

The easiest way is from the program itself: **☰ menu → Ajuda (Help) → Extensão do navegador... (Browser extension)**. The window shows the exact folder, and **Abrir pasta** opens it.

| How you run LDM | Extension folder |
|---|---|
| Linux AppImage | `~/Documents/LinuxDownloadManager-extensao`. The menu above creates it, so open it once first. |
| Windows installer | `%LOCALAPPDATA%\Programs\Lunix Download Manager\_internal\browser_extension` |
| Windows, installed "for all users" | `C:\Program Files\Lunix Download Manager\_internal\browser_extension` |
| Windows portable zip | `<unzipped folder>\_internal\browser_extension` |
| From source | `browser_extension/` in this repository |

You can also download `ldm-browser-extension-<version>.zip` from the [releases page](https://github.com/jcrodriguesjr0/linux-download-manager/releases/latest) and unzip it into a folder of your own.

> **Keep the folder where it is.** The browser loads the extension from that folder every time; if you move or delete it, the extension stops working.

### Step 2: install it in the browser

**Google Chrome, Brave, Chromium, Vivaldi, Opera**
1. Type `chrome://extensions` in the address bar and press Enter. Brave also accepts `brave://extensions`.
2. Turn on **Developer mode**, the switch in the top-right corner.
3. Click **Load unpacked**.
4. Select the extension folder from step 1 (the folder itself, the one that contains `manifest.json`) and confirm.
5. Click the puzzle-piece icon in the toolbar and **pin** "Linux Download Manager" (or "Lunix") to keep its icon visible.

**Microsoft Edge**
1. Go to `edge://extensions`.
2. Turn on **Developer mode**. In recent versions it is in the left sidebar; if the sidebar is hidden, click ☰ at the top left.
3. Click **Load unpacked** and select the extension folder.
4. Pin it with the puzzle-piece icon, as above.

**Firefox**
1. Go to `about:debugging#/runtime/this-firefox`.
2. Click **Load Temporary Add-on…**.
3. Select the `manifest.json` file inside the extension folder.

> Firefox only allows unsigned extensions temporarily: **it disappears when Firefox restarts** and has to be loaded again. A permanent version needs to be published on addons.mozilla.org, which is planned.

### Step 3: check that it works

1. Open LDM.
2. Click the LDM icon in the browser toolbar: the popup should say **"conectado · v1.4.0"** (connected). If it says **"LDM fechado"**, LDM is not running.
3. Open any page with a video and hover over the player: the **"Baixar este vídeo"** button appears in the top-right corner of the video.
4. Download any file of 50 MB or more: LDM takes over the download.

### Options in the popup
- **Capturar downloads do navegador:** turns automatic capture on or off.
- **Mostrar "Baixar este vídeo" sobre os players:** shows or hides the button on videos.
- **Tamanho do botão:** **Completo** (icon, text and resolution) or **Mini** (icon only, in a small circle).
- **Alt+click** on a link lets the browser download it; **Ctrl+Alt+click** forces LDM.

### Updating
After installing a new version of LDM, open the extensions page (`chrome://extensions` or `edge://extensions`) and click **↻ Reload** on the LDM card, then reload the open tabs. For the AppImage, open **☰ → Ajuda → Extensão do navegador** once so the folder is updated.

### Troubleshooting
- **The browser downloaded instead of LDM:** the file was smaller than 50 MB (default rule, changed in **Options → Tipos de arquivo**), LDM was closed, or capture is off in the popup.
- **"Developer mode extensions" warning:** this is normal for extensions installed by hand; click to keep it enabled.
- **Flatpak browsers (SteamOS, Fedora Silverblue…):** use the `~/Documents/LinuxDownloadManager-extensao` folder. Flatpak browsers can read Documents but not the inside of the AppImage.
- **Port:** the extension talks to LDM on `127.0.0.1:9614`. If you change the port in LDM, change it in the popup too.

### How it talks to LDM
The extension uses a local API on `127.0.0.1:9614`, so it also works with Flatpak browsers, which cannot run native-messaging hosts. The API only accepts requests from `chrome-extension://` or `moz-extension://` origins, or from local clients that send the `X-LDM-Client` header without an `Origin`. Web pages are blocked.

## Running from source

Requirements:
- Python 3.10+ with GTK 3 (PyGObject); only the standard library is used.
- Optional: `ffmpeg` (merging and HLS), `yt-dlp` (video sites), `canberra-gtk-play` (sounds) and `notify-send` (notifications).

```bash
python3 ldm.py                 # GUI
python3 ldm.py --tray          # start minimized to the tray
python3 ldm.py install         # add to the application menu
python3 ldm.py add URL         # send a URL to the running instance
python3 ldm.py video URL       # download the video on a page (opens quality selection)
python3 ldm.py get URL -o ~/Downloads -c 8 -l 2048   # terminal only: 8 connections, 2 MB/s limit
```

**yt-dlp:** LDM looks for it in this order:
1. the path set in Options → Video;
2. the copy bundled in the AppImage;
3. `~/.local/share/ldm/ytdlp`;
4. `PATH`;
5. a distrobox named in the options (useful on immutable systems such as SteamOS).

**Options → Video → Install/update yt-dlp** keeps it current. Do this whenever a site stops working.

Settings live in `~/.config/ldm/settings.json`. The download list, queues, temporary files and grabber projects are in `~/.local/share/ldm/`.

## Project layout

```
ldm.py                 launcher and CLI
ldm/engine.py          multi-connection engine (dynamic segmentation, resume, sparse .part file)
ldm/media.py           video grabber: yt-dlp, quality list, native engine + ffmpeg, passive capture
ldm/hls.py             HLS -> mp4 fallback without yt-dlp
ldm/net.py             HTTP/FTP, proxy, per-site logins, speed limiter, ZIP preview
ldm/manager.py         persistent list, queues, scheduler, completion actions
ldm/grabber.py         site grabber
ldm/server.py          local API for the extension and the CLI
ldm/gui/               GTK 3 windows and dialogs
browser_extension/     MV3 extension (Chrome/Edge/Firefox): video button, network sniffer, page hook
packaging/appimage/    AppImage build script
identidade_visual/     logo, icons, colors and screenshots
tests/                 unit tests and an end-to-end browser test
```

## Tests

```bash
python3 -m unittest discover -s tests -v
```

`tests/e2e_browser.py` loads the extension in a real Chromium with Playwright and runs 12 scenarios: page button, sniffer, download capture, MSE player, JSON APIs, embedded MPD, `range=` reassembly and capture keys. Run it with `PLAYWRIGHT_BROWSERS_PATH` pointing to your Playwright browsers.

## Building the AppImage

On Ubuntu 24.04 (a distrobox works), with `python3-gi python3-gi-cairo gir1.2-gtk-3.0 librsvg2-common libgdk-pixbuf2.0-bin python3-pip`:

```bash
python3 packaging/appimage/build_appimage.py      # output in dist/
```

**Windows:** built by GitHub Actions (`.github/workflows/windows.yml`): MSYS2 + PyInstaller + Inno Setup, then the installer is installed and smoke-tested on a Windows runner. Locally, in an MSYS2 UCRT64 shell: `python packaging/windows/build.py`.

## Limitations

- DRM-protected streams (Netflix, Prime Video, Disney+) cannot be downloaded.
- When YouTube serves a video only through its SABR/UMP protocol, there is no reusable link to capture; such videos are downloaded through yt-dlp.

## Third-party components in the AppImage

| Component | License |
|---|---|
| [Python](https://www.python.org/) | PSF |
| [GTK 3](https://gtk.org/), GLib, PyGObject | LGPL-2.1+ |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Unlicense |
| [Deno](https://deno.com/) | MIT |
| [Inter](https://rsms.me/inter/), [JetBrains Mono](https://www.jetbrains.com/lp/mono/) fonts (`data/fonts`) | SIL OFL 1.1 |
| [FFmpeg](https://ffmpeg.org/), static build by [John Van Sickle](https://johnvansickle.com/ffmpeg/) | GPL-3.0; source code at the links |

## License

[MIT](LICENSE). LDM is an independent project, not affiliated with Tonec Inc. or Internet Download Manager.
