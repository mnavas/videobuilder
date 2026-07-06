# Installation Guide

## Prerequisites

- **Python 3.10 or newer** — [python.org/downloads](https://www.python.org/downloads/)
- **pip** (bundled with Python 3.10+)
- **git** (to clone the repository)
- **ffmpeg and ffprobe** — VideoBuilder uses ffmpeg for all media processing (thumbnails, metadata, preview rendering, and export). Both must be on your `PATH`.

---

## Linux

### 1 — System dependencies

**Ubuntu / Debian:**
```bash
sudo apt update
sudo apt install ffmpeg python3-dev python3-venv libxcb-cursor0 libgl1
```

**Fedora / RHEL:**
```bash
sudo dnf install ffmpeg python3-devel xcb-util-cursor mesa-libGL
```

**Arch:**
```bash
sudo pacman -S ffmpeg xcb-util-cursor mesa
```

> If you see `qt.qpa.plugin: could not load the Qt platform plugin "xcb"` on launch, the `libxcb-cursor0` (or `xcb-util-cursor`) package is likely missing.

### 2 — Clone and run

```bash
git clone https://github.com/mnavas/videobuilder.git
cd videobuilder
./run.sh
```

`run.sh` creates the virtual environment and installs the dependencies (PySide6, Pillow) automatically on first use, then launches the app. Subsequent launches skip straight to starting the app.

### 3 — Manual setup (if you prefer)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m videobuilder.main
```

### 4 — Desktop launcher (optional)

Create `~/.local/share/applications/videobuilder.desktop` so the app appears in your application menu:

```ini
[Desktop Entry]
Type=Application
Name=VideoBuilder
Comment=Simple timeline video editor and slideshow maker
Exec=/bin/bash -c 'cd /path/to/videobuilder && ./run.sh'
Icon=video-x-generic
Terminal=false
Categories=AudioVideo;Video;
```

Replace `/path/to/videobuilder` with the actual clone location, then run `update-desktop-database ~/.local/share/applications` (or log out and back in).

---

## macOS

### 1 — System dependencies

Install [Homebrew](https://brew.sh) if you don't have it, then:

```bash
brew install ffmpeg python git
```

### 2 — Clone and run

```bash
git clone https://github.com/mnavas/videobuilder.git
cd videobuilder
./run.sh
```

---

## Windows

### 1 — System dependencies

1. Install **Python 3.10+** from [python.org](https://www.python.org/downloads/) — check **"Add python.exe to PATH"** during setup.
2. Install **ffmpeg**: the easiest way is `winget install ffmpeg` in a terminal, or download a build from [gyan.dev/ffmpeg](https://www.gyan.dev/ffmpeg/builds/) and add its `bin` folder to your `PATH`.
3. Install **git** from [git-scm.com](https://git-scm.com/downloads) (or use GitHub Desktop).

Verify in a new terminal:

```powershell
python --version
ffmpeg -version
```

### 2 — Clone and run

`run.sh` is a bash script, so on Windows use the manual steps:

```powershell
git clone https://github.com/mnavas/videobuilder.git
cd videobuilder
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m videobuilder.main
```

For later launches, only the last three lines starting from `.venv\Scripts\activate` are needed (or just the last two).

---

## Verifying the install

Launch the app. You should see one window with:

- a **media pool** (top-left, with a hint telling you how to import files),
- a **preview pane** (top-right),
- a **three-track timeline** (Video / Audio / Titles) at the bottom.

Quick smoke test: click **Add Images… → Choose Folder…**, point it at any folder of photos, accept the dialog — the photos should appear on the Video track back-to-back. Click one of them on the timeline and press **▶** to flip through the slideshow.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| *"ffmpeg was not found on PATH"* dialog | ffmpeg isn't installed or isn't on `PATH`. Install it (see your platform above) and restart the app. Verify with `ffmpeg -version` in a terminal. |
| `qt.qpa.plugin: could not load the Qt platform plugin "xcb"` (Linux) | Install `libxcb-cursor0` (Debian/Ubuntu) or `xcb-util-cursor` (Fedora/Arch). |
| Play button is greyed out | Nothing is loaded in the preview yet — click a clip in the media pool or on the timeline first. A single static image also has nothing to "play"; select an image clip **on the timeline** to flip through the image sequence, or use **▶ Preview Full Video** to watch everything (clips + music + titles) blended together. |
| **Preview Full Video** takes a while to start | It renders the whole timeline through ffmpeg before playing (so the preview matches the export exactly). A few seconds for a short slideshow is normal; longer projects take proportionally longer. |
| Importing a huge photo folder | Thumbnails decode on a background thread — the window stays responsive and shows progress on the button. If it ever freezes, that's a bug: please [open an issue](https://github.com/mnavas/videobuilder/issues). |
| Exported file has black sections | There are gaps between clips on the Video track (gaps render as black). Click **Pack Clips Tight (No Gaps)** to close them, or drag clips together. |

---

## Updating

```bash
cd videobuilder
git pull origin main
./run.sh
```

If `requirements.txt` changed, `run.sh` installs the updates automatically (on Windows: re-run `pip install -r requirements.txt` inside the venv).
