# Linux Download Manager (LDM)

**English** · [Português (Brasil)](README.pt-BR.md)

A download manager for Linux inspired by Internet Download Manager. It speeds up downloads with multiple connections, grabs videos from any website through a browser extension, and includes queues, a scheduler, a speed limiter and a site grabber.

![Main window](docs/screenshots/main-dark.png)

> The interface is in Brazilian Portuguese. English covers menus and columns only.

## Download

**[⬇ Linux_Download_Manager-1.3.0-x86_64.AppImage](https://github.com/jcrodriguesjr0/linux-download-manager/releases/latest)** (~144 MB, single file, nothing to install)

It bundles Python 3.12, GTK 3, yt-dlp, Deno and ffmpeg. It runs on any x86_64 Linux with glibc ≥ 2.39: SteamOS, Ubuntu 24.04+, Fedora 40+, Arch.

```bash
chmod +x Linux_Download_Manager-1.3.0-x86_64.AppImage
./Linux_Download_Manager-1.3.0-x86_64.AppImage            # open the program
./Linux_Download_Manager-1.3.0-x86_64.AppImage install    # add it to the application menu
./Linux_Download_Manager-1.3.0-x86_64.AppImage selftest   # check the bundled components
```

Then install the browser extension (see below).

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

The extension lives in `browser_extension/`. Inside the AppImage, **Help → Browser extension** copies it to `~/Documents/LinuxDownloadManager-extensao` and opens the browser.

- **Chrome / Edge / Chromium:**
  1. Open `chrome://extensions` and turn on **Developer mode**.
  2. Click **Load unpacked** and select the extension folder.
- **Firefox:**
  1. Open `about:debugging` → **This Firefox** → **Load Temporary Add-on**.
  2. Select `manifest.json`.

The extension talks to a local API on `127.0.0.1:9614`, so it also works with Flatpak browsers, which cannot run native-messaging hosts. The API only accepts requests from `chrome-extension://` or `moz-extension://` origins, or from local clients that send the `X-LDM-Client` header without an `Origin`. Web pages are blocked.

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
