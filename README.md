# Linux Download Manager (LDM)

**English** · [Português (Brasil)](README.pt-BR.md)

A free download manager and accelerator, an **Internet Download Manager (IDM) alternative** for **Linux**, **Steam Deck** and **Windows**. It downloads with multiple connections, resumes interrupted downloads and grabs videos from any site with a button on top of the player.

![Main window](docs/screenshots/main-dark.png)

## Download

| System | File |
|---|---|
| **Linux** (x86_64) | [`Linux_Download_Manager-x86_64.AppImage`](https://github.com/jcrodriguesjr0/linux-download-manager/releases/latest) |
| **Windows 10/11** | [`Lunix_Download_Manager-Setup.exe`](https://github.com/jcrodriguesjr0/linux-download-manager/releases/latest) or `portable.zip` |

- **Linux:** `chmod +x` the file and run it. Needs glibc 2.38+ (SteamOS, Ubuntu 24.04+, Mint 22+, Fedora 39+, Debian 13, Arch). To add a menu entry: `./Linux_Download_Manager-*.AppImage install`.
- **Windows:** the app is called **Lunix Download Manager**. SmartScreen warns on first run: **More info → Run anyway**.

## Browser extension

Required for capturing downloads and for the video button. It ships with the app; LDM reminds you on first run and shows the folder under **☰ → Help → Browser extension**.

1. Open `chrome://extensions` (Chrome, Brave) or `edge://extensions` (Edge).
2. Turn on **Developer mode**.
3. Click **Load unpacked** and pick the extension folder.

**Firefox:** `about:debugging#/runtime/this-firefox` → **Load Temporary Add-on** → `manifest.json` (removed when Firefox restarts).

To check it, click the LDM icon in the browser toolbar: it should say **"connected"**. Files of 50 MB or more go to LDM; **Alt+click** lets the browser download, **Ctrl+Alt+click** forces LDM.

## Features

- **Faster downloads:** multiple connections with dynamic segmentation, resume after a drop or reboot, HTTP/HTTPS/FTP, proxy and speed limiter.
- **Videos:** "Download this video" button on any player, quality choice, MP3, subtitles and playlists; YouTube and ~1,800 sites via yt-dlp, plus HLS/DASH capture.
- **Organization:** categories, queues, scheduler, shut down when done, IDM list import.
- **Site Grabber**, tray icon, start with the system, dark and light themes.

| Button on the player | Quality choice | Progress |
|---|---|---|
| ![Video button](docs/screenshots/video-button.png) | ![Video dialog](docs/screenshots/video.png) | ![Progress](docs/screenshots/progress.png) |

## For developers

```bash
python3 ldm.py                              # run from source (Python 3.10+, GTK 3 / PyGObject)
python3 -m unittest discover -s tests       # tests
python3 linux/build_appimage.py             # AppImage (Ubuntu 24.04) into linux/dist/
```

Windows builds come from GitHub Actions (`windows/`, MSYS2 + PyInstaller + Inno Setup).

```
ldm/               app code (engine, video, local API, GTK UI)
browser_extension/ MV3 extension (Chrome, Edge, Firefox)
linux/             AppImage build
windows/           Windows build
```

## License

[MIT](LICENSE). Independent project, not affiliated with Tonec Inc. or Internet Download Manager. Bundles yt-dlp (Unlicense), FFmpeg (GPL-3.0), Deno (MIT), GTK/PyGObject (LGPL) and the Inter and JetBrains Mono fonts (OFL).
