# VideoBuilder — Analysis

> **Revision note (2026-06-28):** §4.3/§4.1 below originally described Stop Motion as a *separate
> launchable window* ("project type") alongside the Video Maker. The user clarified that wasn't
> the intent — they wanted one interface, not two projects. The separate `StopMotionWindow` was
> removed; its capability (turn a batch of photos into a timed sequence) now lives inside the Video
> Maker itself (the "Add Images…" dialog and the media pool's multi-select → "Add Selected to
> Timeline" button — see changelog.md v0.1.2/v0.1.3/v0.1.4). The goal/scope below is kept as
> originally written for history; treat "Stop Motion Builder" as a feature of the one window, not a
> second window.

## 1. Goal

Build a self-contained desktop application, **VideoBuilder**, that covers two related but distinct workflows:

1. **Video Maker** — a simplified clone of the discontinued Windows Movie Maker: import video/audio/image clips, arrange them on a timeline, trim, add simple transitions and titles, and export a finished video file.
2. **Stop Motion Builder** — turn an existing folder of still photos into a stop-motion video by ordering the frames and choosing a frame rate / per-image duration, optionally with a music track, then exporting.

Both workflows live in one app under `VideoBuilder/` and share the same export/preview engine so effort isn't duplicated.

## 2. Decisions already made (with user)

| Decision | Choice |
|---|---|
| App type | Desktop GUI |
| Language | Python |
| Stop motion input | Assemble **existing photos** into a video (no live webcam capture) |

## 3. Tech stack

| Concern | Choice | Why |
|---|---|---|
| GUI toolkit | **PySide6** (Qt for Python) | LGPL-licensed (unlike PyQt5's GPL/commercial split), ships `QGraphicsView`/`QGraphicsScene` which is a natural fit for a timeline widget, and `QMediaPlayer`/`QVideoWidget` give built-in video preview without extra native deps. |
| Video encode/decode/probe | **ffmpeg / ffprobe** (external binary, called via `subprocess`) | Confirmed present on this machine (`/usr/bin/ffmpeg`, 6.1.1). Industry-standard, scriptable, handles every codec/container we need. The app shells out rather than bundling a Python video codec library — far less brittle than `moviepy`-style wrappers, and the same approach used in the user's other video project (`video-trim`, which also wraps ffmpeg). |
| Image handling | **Pillow** | Reading image dimensions/EXIF rotation and generating thumbnails for the media pool / stop-motion reel. |
| Project persistence | Plain JSON file (`.vbproj.json`) | Human-readable, diff-able, no DB dependency for a single-user local app. |
| Packaging | Deferred — run via `python -m videobuilder` during development; revisit PyInstaller for a distributable `.exe` only if the user asks. | Avoids speculative work; Windows packaging is a separate concern from getting the app correct. |

Risk: PySide6 is not yet installed in this environment (checked: not present). It will be added to `requirements.txt` and installed in a venv as part of implementation — not a blocker, just noted.

## 4. Feature breakdown

### 4.1 Shared core (used by both modes)
- **Project model**: `Project` → list of `Track`s → list of `Clip`s (source path, in/out points, position on timeline, type: video/audio/image/text).
- **Media pool**: import files (file dialog + drag-and-drop), shows thumbnail + duration/resolution (via `ffprobe`), drag from pool onto timeline.
- **Timeline widget**: horizontal multi-track view, drag to reposition/trim clips, snapping, zoom, playhead scrubbing.
- **Preview player**: plays the current frame/selection using `QMediaPlayer` for video, or a generated low-res proxy for the assembled timeline.
- **Export engine**: builds an `ffmpeg` command (filter graph: concat/overlay/trim/atrim as needed) and runs it in a background `QThread` with progress reporting parsed from ffmpeg's stderr.
- **Project save/load**: JSON file capturing the full timeline state so a session can be resumed.

### 4.2 Video Maker specific
- Import video clips, audio tracks, and static images.
- Trim clip in/out points; split a clip at the playhead.
- Arrange multiple clips in sequence on a video track + a separate audio track.
- Basic transitions between adjacent clips: cut (default) and crossfade.
- Title/text overlay clips (text, duration, position) rendered via ffmpeg `drawtext`.
- Export to MP4 (H.264/AAC) at a chosen resolution/quality preset.

### 4.3 Stop Motion specific
- Pick a folder of images (jpg/png); list them in a reorderable list (default sort: filename, drag to reorder).
- Set a global frame duration (e.g. "0.2s per photo" / "5 fps") or per-image override.
- Optional single background audio track, trimmed/looped to match total duration.
- Preview as a flip-through (timer-based image swap) before export.
- Export to MP4 via ffmpeg's image2 demuxer (concat list with per-file duration) muxed with the optional audio track.
- A finished stop-motion export can be imported back into the Video Maker's media pool as a regular video clip — the two features interoperate rather than being silos.

## 5. Non-goals (v1)

- No live webcam/camera capture (explicitly excluded per user's answer).
- No advanced color grading, keyframed effects, or multi-track compositing beyond simple overlay/transition.
- No cloud sync, multi-user collaboration, or mobile companion app.
- No bundled/standalone Windows `.exe` packaging in this pass — development and testing happen via Python directly; packaging is a follow-up if requested.
- No undo/redo stack in v1 (noted as a fast-follow if the editing workflow proves it's needed).

## 6. Open risks

- **ffmpeg filter-graph complexity** for crossfade transitions and concat with mixed types (video+image+text) — mitigated by building the export module incrementally and testing each clip-type combination in isolation.
- **PySide6 timeline UX** (drag/trim/snap interactions) is the most novel UI work — will be built as its own isolated widget with a small in-memory model so it can be unit-tested without running the full app.
- **No GUI test environment confirmed** in this session — implementation will need manual verification (running the app) once built; headless automated testing of Qt widgets is limited.

## 7. Next step

Produce `plan.md` with concrete, ordered implementation phases derived from the breakdown above.
