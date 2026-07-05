# VideoBuilder — Implementation Plan

Derived from `analysis.md`. Phases are ordered so each one produces something runnable/testable before moving on.

> **Revision note (2026-06-28):** Phase 2 below ("Stop Motion window") describes a separate
> launchable window. That was later removed per user feedback — see `analysis.md`'s revision note
> and `changelog.md`. Kept here for history; actual current behavior is tracked in `changelog.md`.

## Phase 0 — Scaffold
- [ ] `requirements.txt` (PySide6, Pillow), venv setup notes in `readme.md`
- [ ] Package layout:
  ```
  VideoBuilder/
    videobuilder/
      __init__.py
      main.py                # entry point, launches QApplication + start screen
      core/
        models.py            # Project, Track, Clip dataclasses
        project_io.py         # JSON save/load
        media_probe.py        # ffprobe wrapper (duration, resolution, fps)
        ffmpeg_export.py      # builds + runs ffmpeg export commands
      ui/
        start_screen.py       # choose "New Video Project" / "New Stop Motion Project" / "Open"
        main_window.py         # Video Maker window (media pool + timeline + preview)
        timeline_widget.py     # QGraphicsView-based timeline
        media_pool.py          # import + thumbnail list
        preview_player.py      # QMediaPlayer-based preview
        export_dialog.py       # output settings + progress
        stopmotion_window.py   # Stop Motion window (image list + settings + preview)
  ```
- [ ] `readme.md` with run instructions
- [ ] Verify: `python -m videobuilder.main` opens an empty start screen window

## Phase 1 — Core data model + media probing
- [ ] `core/models.py`: `Clip` (id, source_path, type, in_point, out_point, track_index, start_time), `Track` (index, kind: video/audio/text), `Project` (tracks, fps, resolution, name)
- [ ] `core/media_probe.py`: run `ffprobe -v quiet -print_format json -show_format -show_streams <file>`, parse duration/resolution/fps/codec; raise a clear error if ffprobe is missing from PATH
- [ ] `core/project_io.py`: `save_project(project, path)` / `load_project(path)` to/from `.vbproj.json`
- [ ] Verify: small script that probes a sample video and prints duration/resolution; round-trips a `Project` through save/load

## Phase 2 — Stop Motion window (simplest end-to-end path first)
- [ ] `ui/stopmotion_window.py`: "Choose folder" → list images (Pillow reads dimensions, generates thumbnail icons)
- [ ] Drag-to-reorder list (QListWidget with internal move)
- [ ] Frame duration control: global seconds-per-photo or fps, applied to all frames (per-image override deferred to a fast-follow if not needed for v1)
- [ ] Optional audio file picker for background track
- [ ] Flip-through preview (QTimer swapping the displayed image at the chosen rate)
- [ ] `core/ffmpeg_export.py` — stop-motion path: write an ffmpeg `concat` demuxer list file (`file '<path>'` / `duration <secs>`) and run `ffmpeg -f concat -safe 0 -i list.txt -vf <scale/pad to even dims> -c:v libx264 -pix_fmt yuv420p [-i audio -c:a aac -shortest] out.mp4`
- [ ] Export progress dialog: run ffmpeg in a `QThread`, parse `frame=`/`time=` from stderr, show progress bar
- [ ] Verify end-to-end: point at a real folder of photos, export, confirm output plays and matches expected duration/order

## Phase 3 — Video Maker: media pool + preview (no editing yet)
- [ ] `ui/media_pool.py`: import files via dialog + drag-and-drop, show thumbnail + filename + duration, backed by `media_probe`
- [ ] `ui/preview_player.py`: `QMediaPlayer` + `QVideoWidget`, play/pause/seek for a single selected clip
- [ ] `ui/main_window.py`: lay out media pool (left) + preview (right), empty timeline placeholder (bottom)
- [ ] Verify: import a video, see it in the pool, click to preview/play it

## Phase 4 — Timeline widget
- [ ] `ui/timeline_widget.py`: `QGraphicsView`/`QGraphicsScene`, one row per track, clips rendered as draggable/resizable rectangles with thumbnail + label
- [ ] Drag from media pool onto a track inserts a `Clip` at the drop position
- [ ] Drag clip horizontally to reposition; drag edges to trim in/out; snapping to adjacent clip edges and playhead
- [ ] Split-at-playhead action (keyboard shortcut + button)
- [ ] Playhead scrubbing drives the preview player
- [ ] Verify: build a 3-clip sequence by dragging from the pool, trim one, split another, scrub through it

## Phase 5 — Audio track + titles
- [ ] Dedicated audio track row in the timeline (same drag/trim/position model, type-restricted to audio files)
- [ ] Title/text clip type: double-click an empty text-track slot to enter text, duration; rendered as a generated PNG (Pillow/ImageDraw) for preview, and via ffmpeg `drawtext` filter at export
- [ ] Verify: a project with a video clip, a music track, and one title overlay previews/exports correctly

## Phase 6 — Export engine for full timeline
- [ ] `ffmpeg_export.py` — video-maker path: build a filter-graph string from the `Project` model:
  - per-clip `trim`/`atrim` + `setpts`/`asetpts`
  - `xfade` filter for crossfade transitions between adjacent video clips; plain concat for cut transitions
  - `overlay` for title/text clips on top of the base video stream
  - final `amix`/`concat` for audio track(s)
- [ ] `ui/export_dialog.py`: resolution + quality preset picker, output path, progress bar reusing the Phase 2 progress-parsing code
- [ ] Verify: export a project combining clips, a crossfade, a title, and background music; confirm playback matches the timeline

## Phase 7 — Project save/load + polish
- [ ] Wire "Save Project" / "Open Project" into both windows using `project_io`
- [ ] Recent-projects list on the start screen
- [ ] "Send stop-motion export to Video Maker pool" shortcut button
- [ ] Basic error surfacing (missing ffmpeg, unreadable file, failed export) as dialog messages instead of silent failures/crashes
- [ ] Verify: close and reopen a project, confirm timeline state is restored exactly

## Phase 8 — Manual verification pass
- [ ] Run the app end-to-end for both workflows with real sample media (per `/verify`-style manual testing, since headless Qt automation is out of scope for v1)
- [ ] Update `changelog.md` after each phase lands (see below)

## Out of scope for this plan (see analysis.md §5)
Webcam capture, color grading/keyframed effects, cloud sync, Windows `.exe` packaging, undo/redo.

## Tracking
Progress is recorded phase-by-phase in `changelog.md` as each phase is completed and manually verified.
