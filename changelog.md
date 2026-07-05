# Changelog

## [0.2.2] — 2026-07-05 — QA/UX round: undo/redo, unsaved-changes safety net, 3 bugs fixed

QA pass focused on the recent features (multi-select, bulk duration, previews), then implemented
the two safety nets flagged as highest-value in every prior UX round. All changes verified with
real `QTest` interaction.

### Bugs found and fixed
- **Selection was lost after every timeline rebuild**: Set Duration for Selected (or split, etc.)
  recreated all ClipItems without carrying selection over -- so adjusting the duration *twice in a
  row* silently did nothing the second time. `rebuild()` now re-applies selection to the recreated
  items by clip identity. [timeline_widget.py](videobuilder/ui/timeline_widget.py)
- **Set Duration with nothing selected was a silent no-op** -- now shows a one-line hint explaining
  how to select clips.
- **Ctrl-click deselect still armed a drag** on the just-deselected clip; now deselecting a clip
  never starts moving it.

### New: undo/redo (Ctrl+Z / Ctrl+Shift+Z or Ctrl+Y)
- Snapshot-based history (up to 100 states) in `TimelineWidget`, pushed on every `project_modified`
  (deduped so click-without-drag emissions don't pollute the stack). Restore swaps track contents
  in place so the shared `Project` instance keeps its identity. Window-level `QShortcut`s work
  regardless of which panel has focus.
- Verified: drag → Ctrl+Z restores the exact prior position → Ctrl+Shift+Z re-applies; delete →
  Ctrl+Z brings the clip back.

### New: unsaved-changes protection
- Dirty flag tracked via `project_modified`; window title shows a `*` marker while unsaved.
- Closing a dirty window now prompts Save / Discard / Cancel (Cancel keeps it open; Save that gets
  cancelled at the file dialog also keeps it open). Saving clears the flag and the `*`.
- Ctrl+S now saves from anywhere in the window.

### Smaller UX improvements
- Double-clicking an existing title clip now edits its text/duration (previously the only way to
  change a title was delete + recreate; double-click did nothing).
- Empty media pool now shows a hint ("Click Import Media… or Add Images… above, or drag files
  here") instead of a bare white box -- the last blank-first-launch gap from the user-story round.

## [0.2.1] — 2026-06-28 — "Preview Full Video": see music, images, and titles blended together

User wanted to press play and see *all* layers together -- how the music blends with the images
and titles -- not just one clip in isolation. This is the composite-timeline-preview gap flagged
repeatedly in earlier UX rounds as the biggest thing missing for it to feel like a real editor.

- [x] New "▶ Preview Full Video" button. Renders the *entire current timeline* -- video/images,
  crossfades, titles (drawtext), and music all mixed together -- through the existing, already
  battle-tested `export_timeline()` engine to a temp file, then loads and auto-plays it in the
  preview pane. Reusing the real export path (rather than writing separate preview-only compositing
  logic) means the preview is always pixel-for-pixel what Export will actually produce -- no risk of
  the preview drifting out of sync with reality.
  [main_window.py](videobuilder/ui/main_window.py)
- [x] Temp preview file is replaced (old one deleted) each time you click the button again, and
  cleaned up on window close.
- **Verified**: built a project (3 images + music + a title), clicked Preview Full Video, confirmed
  the rendered file has both video and audio, extracted a frame and visually confirmed the title
  text is actually burned into the composited image, confirmed playback auto-starts, and confirmed
  the temp file is removed when the window closes.
- **Trade-off worth knowing**: this re-renders on every click, so for a longer project there's a
  short wait before playback starts (a few seconds for a short slideshow; longer for a multi-minute
  video) -- it's a "render preview," not an instant live scrub. A true frame-accurate live compositor
  would avoid that wait but is a much larger undertaking; flagging rather than building it
  speculatively.

## [0.2.0] — 2026-06-28 — Restored slideshow flip-through preview (lost in the Stop Motion merge)

User sent a screenshot of the real running app: a project made entirely of imported screenshots
(image clips), play button greyed out. The disabled state from v0.1.9 was actually correct -- a
single static image has nothing to "play" -- but that surfaced the real issue: when Stop Motion was
merged into the Video Maker (v0.1.4), its flip-through image-sequence preview never got carried
over. There was no way to press play and watch a slideshow of images actually play.

- [x] `PreviewPlayer.load_image_sequence(frames)`: takes an ordered list of `(path, duration)` and
  lets Play flip through them via a `QTimer` resched at each frame's own duration, looping back to
  the start -- the same experience the old Stop Motion window had, now inside the unified timeline.
- [x] `MainWindow._on_timeline_clip_selected`: selecting an image clip *on the timeline* now builds
  this sequence from that clip onward (stopping at the first non-image clip), instead of just
  showing one frozen frame. Selecting an image in the *media pool* still shows a single static
  preview, deliberately -- the pool has no inherent order/duration, only the timeline does.
  [preview_player.py](videobuilder/ui/preview_player.py), [main_window.py](videobuilder/ui/main_window.py)
- [x] Also improved the actual root cause of the "looks broken" report: the empty-preview placeholder
  text now says "Click a clip in the media pool or timeline below to preview it here" instead of the
  uninformative "No clip selected" -- a disabled button with no explanation is indistinguishable from
  a broken one.
- **Verified**: loaded a 4-image sequence, selected the first clip on the timeline, clicked Play,
  watched the displayed frame advance through all 4 indices over time; clicked Pause, confirmed it
  stopped advancing; confirmed pool-selected images still show static (no regression) and that
  stopping/restarting leaves no stray timer running.

## [0.1.9] — 2026-06-28 — Fixed the play button; built the bulk-duration feature properly this time

User reported the play button doesn't work, and that the "select several images, set their time,
with a checkbox/button to keep things smooth" request from earlier wasn't actually delivered --
correct on both counts. The earlier "Add Images" / "Add Selected to Timeline" work only set
duration at the moment images were first added to the timeline; there was no way to select clips
*already on* the timeline and change them, which is what was actually being asked for.

### Fixed: play button silently did nothing before any clip was selected
- **Root cause**: `PreviewPlayer._play_btn` was never disabled in `__init__` -- every other code path
  in the class correctly disables it when there's nothing to play, but the initial state was enabled
  by default. Clicking it before selecting any clip hit `toggle_play()`'s early-return and did
  nothing -- no error, no feedback, which looks exactly like "broken."
- **Verified the rest of the pipeline first**: confirmed real playback genuinely works in this
  environment (position advances, no errors) once a clip is actually loaded and the button is
  clicked -- so this was specifically about the disabled-state bug, not a deeper codec/backend issue.
- **Fix**: `_play_btn` and `_scrubber` now start disabled, matching every other state transition in
  the class. [preview_player.py](videobuilder/ui/preview_player.py)

### Added: select multiple clips on the timeline, bulk-set their duration, and pack them tight
- **Timeline multi-select**: `ClipItem` now supports Ctrl/Shift-click to add to selection (previously
  every click cleared all other selections, so multi-selecting clips on the timeline -- as opposed
  to the media pool, which already supported it -- was never actually possible). Ctrl+A selects all
  clips.
- **`TimelineWidget.set_duration_for_selected(seconds)`**: applies a new shown duration to every
  selected clip at once -- the actual "select all the images, set up time" feature. Video/audio clips
  are clamped to their own source length; images/titles accept any duration.
- **`TimelineWidget.remove_gaps()`** (button: "Pack Clips Tight (No Gaps)"): repacks every clip on
  the Video track back-to-back in order. Handles *both* directions raised in feedback -- shortening
  several clips leaves gaps (closed), lengthening them creates overlaps that would now auto-crossfade
  per the v0.1.6 change (resolved instead, since "smooth" for a plain slideshow means no gaps *and*
  no accidental blending, not a button + a separate checkbox for each direction).
- New toolbar row in the timeline: duration field + "Set Duration for Selected" + "Pack Clips Tight".
- **Verified**: built a 5-image sequence, Ctrl+A, set duration down to 0.7s (closes gaps via Pack
  Clips Tight, exported file exactly 3.5s) and up to 3.0s (resolves the resulting overlaps via the
  same button, clips land at exact 3.0s back-to-back positions) -- both directions confirmed via the
  model state and a real export.

## [0.1.8] — 2026-06-28 — UX round with user stories; found and fixed a real trim-boundary bug

Wrote 11 user stories (first launch, photo slideshow with music, multi-clip video, trim, crossfade,
title, timed music, mistake recovery, save/resume, export, second project) and walked through each
with real `QTest` interaction against fresh-built test media, not direct method calls.

### Bug found and fixed: trimming a clip adjacent to another was unreliable right at the seam
- **Found** while running Story 4 (trim a clip that's adjacent to another, the common case after
  "Add Selected to Timeline" or a split): trimming clip1's right edge silently did nothing when
  clip2 sat immediately to its right with zero gap.
- **Root cause**: `QGraphicsRectItem` carries a default 1px pen even though `ClipItem.paint()`
  always sets its own pen for drawing -- but the *item's own* `pen()` property (unrelated to what
  `paint()` does) still pads `boundingRect()`/the hit-test `shape()` by ~0.5px per side. For two
  clips placed exactly back-to-back, this created a ~1px zone straddling the seam where clicks
  resolved to the *later* clip instead of the earlier one's right edge -- exactly where a user would
  click to trim either clip.
- **Fix**: `ClipItem.__init__` now explicitly sets `self.setPen(QPen(Qt.PenStyle.NoPen))`, making
  the hit-test boundary exactly match the visual rect with no padding. Has no effect on rendering
  (paint() already overrides the pen for drawing). [timeline_widget.py](videobuilder/ui/timeline_widget.py)
- **Verified**: probed the exact pixel boundary between two adjacent clips before/after the fix --
  before, scene_x=359 (1px before the nominal boundary at 360) resolved to the wrong clip; after,
  the boundary is exact. Re-ran the full trim story: now trims to the exact expected in/out points.

### Confirmed gaps (not fixed yet -- flagging for a decision, not silently changing behavior)
- **Trimming a clip's left edge leaves a gap, doesn't ripple.** Trimming the start of the first
  clip in a sequence shifts its `start_time` forward and leaves the space before it empty -- which
  renders as black at export. This is "technically correct" (non-destructive, gap-preserving
  editing) but likely surprises a casual user expecting the trim to just shorten the video. Ripple
  trim (auto-closing the gap, shifting later clips left) is what most consumer editors default to.
  This is a real editing-semantics decision, not a quick patch -- flagging rather than changing it.
- **No undo (Ctrl+Z does nothing)** -- confirmed directly: dragged a clip, pressed Ctrl+Z, position
  unchanged.
- **Closing a window with unsaved changes is silent** -- confirmed directly: `close()` on a window
  with an unsaved clip on the timeline shows no warning dialog at all.
- **Adding a title is only discoverable via double-clicking the Titles row** -- no button anywhere
  says "Add Title"; the only hint is a static toolbar label.
- **Placing audio at a specific offset takes two steps** -- "Add Selected to Timeline" only appends
  at the end of the audio track; positioning music to start partway through requires a follow-up drag.
- **No onboarding for an empty project** -- first-launch screenshot shows a blank white media pool
  with zero hint text; the only inline guidance anywhere is about the least-essential feature
  (titles).
- **No visual distinction for a crossfade region** -- two overlapping clips just look like two
  plain rectangles; there's no shading/hatching to show a transition exists there before export.

## [0.1.7] — 2026-06-28 — Removed the launcher dead end; MainWindow is self-sufficient

User question: "why open project or new project could not be in the main window as a regular
program" -- correct catch. `StartScreen` was the original launcher from the very first build pass;
as toolbar buttons kept getting added to `MainWindow` afterward, it never got its own New/Open, so
closing the launcher left no way to start or open another project without restarting the app. This
was a real gap the earlier UX pass should have caught and didn't -- that pass audited the editing
feature surface (timeline, clips, export) but never checked the app's own navigation.

- [x] Deleted `ui/start_screen.py`. `main.py` now launches directly into a `MainWindow` with a
  blank project -- no separate launcher step.
- [x] Added "New Project" and "Open Project…" buttons to `MainWindow`'s own toolbar. Each opens in
  a new, fully independent window (own project, own `_open_windows` list) -- closing any one window
  never traps you.
- [x] Verified: app boots straight into the editor; New Project from window A opens window B with
  an independent project; closing A leaves B (and anything B spawns afterward) fully functional;
  Open Project loads a saved project's clips and title correctly from the new toolbar button.

## [0.1.6] — 2026-06-28 — UX pass focused on building longer (3min+) multi-clip videos

Analyzed the flow a user follows to build a several-minutes-long video specifically (not just a
handful of photos), since that's a meaningfully different usage pattern than what had been tested
so far. Found and fixed two real gaps via hands-on testing (build a multi-clip timeline, drag,
export, measure).

### Fixed: "Add Selected to Timeline" only worked for images
- **Found**: selecting several imported video clips in the pool and clicking "Add Selected to
  Timeline" did nothing but say "no images selected" -- for a video built from multiple clips (the
  normal case for anything longer than a quick photo montage), the *only* way to get clips onto the
  timeline was dragging each one individually.
- **Fix**: `TimelineWidget.add_image_sequence()` generalized into `add_clips_sequence()` (the old
  name kept as a thin wrapper for the image-only Add Images dialog). Video and image clips append
  to the end of the Video track, audio clips to the end of the Audio track, each using its own real
  duration (not the image-duration spinbox, which now only affects images and says so via tooltip).
  [timeline_widget.py](videobuilder/ui/timeline_widget.py), [main_window.py](videobuilder/ui/main_window.py)
- **Verified**: selecting 2 video clips + later a music file and clicking the one button correctly
  routed each to the right track, end-to-end, via real Ctrl-click multi-select and a real button click.

### Fixed: overlapping clips without "Mark as crossfade" silently rendered wrong (WYSIWYG violation)
- **Found**: dragging a clip to overlap another looked like an overlap on the timeline, but unless
  you *also* knew to right-click and choose "Mark as crossfade", the export ignored the overlap
  entirely and played both clips full-length back to back. Measured directly: timeline showed
  13.0s, exported file was 16.0s.
- **Fix**: removed the separate crossfade toggle entirely. Any timeline overlap between adjacent
  clips on the same track is now automatically a crossfade of that length -- matching how
  iMovie/Premiere work, and collapsing a two-step "drag + right-click" gesture into one drag. The
  now-unused `Clip.transition_in` field was removed from the model (old save files with the stray
  key still load fine -- `from_dict` just ignores keys it doesn't recognize).
  [ffmpeg_export.py](videobuilder/core/ffmpeg_export.py), [models.py](videobuilder/core/models.py)
- **Verified**: same overlap scenario now exports at exactly 13.0s, matching the timeline exactly.

### Added: live "Total:" duration readout on the timeline
- For tracking progress toward a target length (3 minutes or any other target), added a bold
  "Total:" label next to the timeline's zoom controls. It shows what Export will *actually*
  produce -- governed by the video track's length (with crossfade shrinkage already reflected, for
  free, since overlap reduces `max(end_time)` naturally), falling back to the audio track's length
  only when the video track is empty. A tooltip clarifies that audio extending past the video gets
  trimmed at export.
- **Found while verifying this**: the first version computed the label from `Project.total_duration()`
  (longest of *all* tracks), which is wrong whenever audio is longer than video -- it would show a
  bigger number than what actually exports. Fixed to mirror the export engine's actual duration logic.
- **Found while verifying that fix**: the label only refreshed inside `rebuild()`, but a plain clip
  drag (move/trim) only emits `project_modified` without calling `rebuild()` -- so the label went
  stale after exactly the gesture most likely to change the total (dragging a clip). Fixed by
  connecting the label refresh directly to `project_modified`.

### Confirmed: no practical scale ceiling for longer videos
- Built and exported a 24-clip / 180-second (3-minute) timeline: completed in 18.2s wall time,
  exact correct output duration. The linear filter-graph fold has no apparent ceiling worth
  worrying about for typical multi-clip video lengths.

## [0.1.5] — 2026-06-28 — Full QA pass: 3 real bugs found and fixed

Acted as QA end-to-end (real `QTest` mouse/keyboard events + screenshots under `QT_QPA_PLATFORM=offscreen`,
not direct method calls) across start screen, every import path, the full timeline, export (incl. crossfade,
image-only, audio-only, missing-ffmpeg), project save/load, and the two previously-fixed regressions.
All test media generated fresh (videos w/ audio, photos, a corrupt file, an 80-photo 3500x2500 folder).

### Bug found: ruler-click scrubbing silently deselected the current clip
- **Found** while testing the natural "select a clip → scrub the playhead inside it → Split" workflow: it
  never worked, because `TimelineGraphicsView.mousePressEvent`'s ruler-click branch unconditionally fell
  through to `super().mousePressEvent(event)`, and Qt's default `QGraphicsScene` click-handling clears the
  current selection whenever the clicked item isn't itself selectable (ruler ticks/labels aren't) — so every
  ruler click silently dropped whatever clip was selected.
- **Fix**: `return` immediately after handling a ruler click, skipping the call to `super()` entirely for
  that case. [timeline_widget.py](videobuilder/ui/timeline_widget.py)
- **Verified**: select a clip, click the ruler (including landing exactly on a tick-mark line, the original
  trigger condition from the earlier ruler-click bug), confirm `isSelected()` stays `True`, then Split at
  playhead actually produces two correctly-bounded clips.

### Bug found: `except FfmpegNotFoundError` around export was unreachable dead code
- **Found** while probing the missing-ffmpeg error path: the dialog title shown was the generic
  "Export failed" (from the worker-thread's catch-all) instead of the intended "ffmpeg not found", because
  `ExportWorker.__init__` doesn't execute anything that could raise — the check only happened later, inside
  the background thread. Functionally harmless (user still got a clear error), but the exception handling
  around it was misleading dead code.
- **Fix**: made `core.ffmpeg_export.require_ffmpeg()` public and call it eagerly in `MainWindow._export_video`
  *before* constructing the worker, so the intended dialog/title actually fires.
- **Found alongside it**: two unrelated `FfmpegNotFoundError` classes existed (one in `media_probe.py`, one in
  `ffmpeg_export.py`) that happened to never collide today, but an `except FfmpegNotFoundError` imported from
  the "wrong" module would have silently failed to catch. Unified to one class (`media_probe.FfmpegNotFoundError`,
  re-exported from `ffmpeg_export`).
- **Fix for the root cause**: `core/media_probe.py`'s `probe()` also called `ffprobe -v quiet`, which suppresses
  ffprobe's own error text — so failure messages shown to the user were just "ffprobe failed for X: " with
  nothing after the colon. Changed to `-v error` (still suppresses normal logging, but error text now comes
  through).
- **Verified**: missing-ffmpeg export now shows the correct dialog title with the eager check; a corrupt
  video file now produces a real diagnostic ("moov atom not found... Invalid data found when processing
  input") instead of an empty one.

### Everything else: held up, no regressions
- Start screen, all five media-import paths (multi-file, drag-and-drop, Add Images x Choose Images, Add
  Images x Choose Folder, pool multi-select), full timeline (drag/trim/split/scrub/zoom/crossfade/titles/
  audio-track-drop), and full export (mixed clips, real crossfade, image-only, audio-only, empty-timeline)
  all passed real-interaction testing, each with at least one adversarial probe (huge trims that must clamp,
  cancelled dialogs, empty selections, mixed valid/invalid file batches, a corrupted project file, a project
  referencing a deleted source file).
- Project save/load round-trips every field exactly (in/out points, crossfade flag, title text) and the
  reopened window's timeline widget is fully populated, not just the data model.
- Re-confirmed both earlier fixes hold under the *current* code path: ruler-click scrub (now doubly verified
  per the bug above) and the large-folder freeze fix — re-measured on a fresh 80-photo, 3500x2500 folder
  through the real "Add Images → Choose Folder" button: 0.86s wall time, longest UI-thread gap 55ms (was
  10.98s/10.98s before the original fix).

## [0.1.4] — 2026-06-28 — Unify Stop Motion into the Video Maker (one window, not two)

User feedback: "I wanted one interface for both, otherwise I would have asked for 2 projects." The
original analysis.md framed Stop Motion as a separate launchable window/project type, which wasn't
the intent. Removed it; its capability now lives inside the single Video Maker window.

- [x] Deleted `ui/stopmotion_window.py` entirely, and the now-dead `core/ffmpeg_export.export_stop_motion()`
  (the concat-demuxer image-sequence export path) — `export_timeline()` already covers a pure image
  sequence equally well (and additionally supports crossfades between images, which the old path didn't).
- [x] `ui/start_screen.py` simplified to two buttons: "New Project" and "Open Project" — no more choosing
  between project *types*.
- [x] Closed the one real capability gap vs. the old Stop Motion window: `AddImagesDialog` now has a
  "Choose Folder…" button alongside "Choose Images…" — pick an entire folder of photos at once, not just
  a multi-file selection.
- [x] New `ui/image_batch_worker.py` (`ImageBatchWorker`, a generalized version of the old per-window
  `FolderLoadWorker`) + `MediaPool.import_images_async()`: importing a folder/batch of images now always
  decodes thumbnails on a background thread regardless of entry point, so the "freeze on a big folder" bug
  class (see v0.1.1) can't reappear here. The "Add Images…" button shows "Importing N images…" and disables
  itself while the batch runs.
- [x] Added `MediaPool.icon_for_path()` + `TimelineWidget.add_image_sequence(..., thumbnail_lookup=...)`:
  the timeline reuses the pool's already-decoded icon for a clip's thumbnail instead of decoding the image
  from disk a second time — avoids doubling the work for large batches.
- [x] Updated stale "Stop Motion" mentions in docstrings/readme; added revision notes to `analysis.md` and
  `plan.md` pointing here, since their original two-window framing is what caused the disconnect.
- [x] Verified end-to-end with real clicks: start screen now shows exactly two buttons; "Add Images…" →
  "Choose Folder…" (folder picker mocked, nothing else) → button shows "Importing 6 images…" during the
  async load → 6 images land on the timeline back-to-back at the chosen duration → pool count matches →
  every clip has a reused (non-`None`) thumbnail. Also re-ran a full export of that project: valid MP4,
  duration exactly matching (6 images x 1.0s = 6.0s).

## [0.1.3] — 2026-06-28 — Multi-select images already in the pool, add to timeline end

- [x] `MediaPool` selection mode changed from single- to `ExtendedSelection` (Ctrl/Shift-click to
  select several already-imported images) — the existing single-item drag-out (`startDrag`, still
  keyed off `currentItem()`) is unaffected.
- [x] `MainWindow`: the pool panel now has a "Seconds per image" field + "Add Selected to Timeline
  (at end)" button right below the pool list. Clicking it takes the selected pool items that are
  images, sorts them by their position in the pool (not click order) for a predictable result, and
  calls the same `TimelineWidget.add_image_sequence()` used by the batch-import dialog — so it
  appends after whatever's already on the timeline.
- [x] Selecting no images (or only non-image items) shows a one-line hint instead of doing nothing
  silently.
- [x] Verified with real Ctrl-click multi-select (`QTest.mouseClick` with `ControlModifier`) and a
  real button click: selecting items in reverse visual order still produced timeline clips in pool
  order; empty selection triggered the hint message; screenshot confirms the selected items show the
  blue highlight and the new controls render correctly under the pool.

## [0.1.2] — 2026-06-28 — Batch image add with auto-sequencing

- [x] `ui/add_images_dialog.py` (new): pick several images at once (`QFileDialog.getOpenFileNames`),
  set one "seconds per image" duration applied to all of them, and a checkbox ("Arrange one after
  another on the timeline (auto-adjust)", checked by default) — live total-duration label, e.g.
  "10 image(s) x 2.0s = 20.0s total".
- [x] `TimelineWidget.add_image_sequence()`: appends the batch to the video track back-to-back,
  starting right after the track's current last clip (0 if the track is empty) — so calling it
  again after manual edits composes correctly instead of overwriting.
- [x] New "Add Images…" button in `MainWindow`, next to "Import Media…". Images are always added to
  the media pool either way; the checkbox only controls whether they're *also* auto-placed on the
  timeline.
- [x] Verified via real button clicks (`QTest.mouseClick`, only the native file-picker mocked):
  10 images at 2s each produced exactly a 20.0s sequence with correct per-clip start times; checkbox
  unchecked left the timeline untouched (pool-only); a second batch added after an existing 5s clip
  started at 5.0s rather than overwriting it.

## [0.1.1] — 2026-06-28 — Real-display verification + responsiveness fix

Ran the app for real (mouse-driven, via `QTest` + real screenshots, no Xvfb available/installable
in this environment) instead of only offscreen logic checks. Found and fixed two bugs.

### Verification (real interaction, not just logic tests)
- [x] Drove both windows end-to-end via real `QTest.mouseClick`/`mousePress`/`mouseMove`/`mouseRelease`
  on the actual widgets (not direct method calls): opening from the start screen, importing media,
  dragging a clip, trimming an edge, scrubbing the playhead, splitting, and exporting — all through
  the real buttons, with screenshots captured via `widget.grab()` confirming the rendering.
- [x] Both real-button exports (stop motion + full timeline) produced valid MP4s with `ffprobe`-confirmed
  durations matching the interactively-edited clip positions exactly.

### Bug: ruler-click scrubbing did nothing
- **Found**: clicking the timeline ruler to move the playhead silently failed almost everywhere,
  because `TimelineGraphicsView.mousePressEvent` checked `itemAt(pos) is None` to detect an "empty"
  click — but the ruler's tick-mark lines and track-row backgrounds are themselves `QGraphicsItem`s
  spanning the full timeline, so `itemAt()` almost never actually returns `None` there.
- **Fix**: check `not isinstance(item, ClipItem)` instead (matching the already-correct pattern in
  `mouseDoubleClickEvent`). Re-verified with a real mouse click: playhead now moves to the exact
  clicked position. [timeline_widget.py](videobuilder/ui/timeline_widget.py)

### Bug: importing a folder of photos froze the app ("python is not responding")
- **Found** (real user report, reproduced and measured): `StopMotionWindow._load_folder` decoded
  every image at full camera resolution synchronously on the UI thread with no opportunity to
  process events. Measured on 150 synthetic 4000×3000 photos: **10.98s with zero event-loop
  responsiveness for the entire duration** — easily long enough to trigger the OS's force-quit prompt.
- **Fix**:
  - `ui/thumbnail_utils.py` (new): decodes thumbnails via `QImageReader.setScaledSize` so formats like
    JPEG downscale *during* decode (libjpeg DCT scaling) instead of decoding at full resolution first —
    also now honors EXIF orientation via `setAutoTransform`, which the old `QPixmap(path)` did not.
  - `ui/stopmotion_window.py`: folder loading now runs on a `FolderLoadWorker` (`QThread`), streaming
    images into the list incrementally via signals, with a live "Loading… N/M" label and the folder
    button disabled until done. The flip-through preview (`_show_preview_frame`) uses the same fast
    decode path.
  - `ui/media_pool.py`: applied the same fast-decode path to the Video Maker's image thumbnails for
    consistency (same risk if many images are imported at once).
- **Verified**: re-measured the same 150-photo folder through the new code path — **2.16s total,
  longest event-loop gap 0.06s** (vs. 10.98s/10.98s before). All 150 images loaded correctly, list
  populates live during the load, button re-enables on completion.

## [0.1.0] — 2026-06-25 — Initial implementation

All planned phases implemented and verified by automated/offscreen testing against real ffmpeg.
Human verification on a real display (mouse-driven drag/trim/playback) is still outstanding — see Phase 8.

### Phase 0 — Project Scaffold
- [x] `videobuilder/` package: `core/` (data model, ffmpeg/ffprobe wrappers, persistence) + `ui/` (PySide6 windows/widgets)
- [x] Python venv with `PySide6` 6.11 + `Pillow` 12.2 (`requirements.txt`)
- [x] Entry point `python -m videobuilder.main` → `StartScreen` (New Video Project / New Stop Motion Project / Open Project)
- [x] Verified ffmpeg 6.1.1 / ffprobe present on PATH

### Phase 1 — Core data model + media probing
- [x] `core/models.py`: `Project` → `Track` → `Clip` dataclasses (`ClipType`, `TrackKind`), with `to_dict`/`from_dict`
- [x] `core/media_probe.py`: `ffprobe` wrapper returning duration/resolution/fps/has_video/has_audio; raises `FfmpegNotFoundError` if `ffprobe` is missing
- [x] `core/project_io.py`: JSON save/load (`.vbproj.json`)
- [x] Verified: round-tripped a `Project` through save/load; probed a generated sample MP4 and got correct duration/resolution/fps

### Phase 2 — Stop Motion window (end-to-end)
- [x] `core/ffmpeg_export.py`: `export_stop_motion()` — builds an ffmpeg `concat` demuxer list (per-image duration), scales to even dimensions, optional audio mux with `-shortest`; progress parsed from `-progress pipe:1`'s `out_time=`
- [x] `ui/stopmotion_window.py`: choose a photo folder → thumbnail filmstrip (`QListWidget`, `IconMode`, drag-to-reorder via `InternalMove`) → seconds-per-photo control → optional audio track picker → flip-through preview (`QTimer`) → Export
- [x] `ui/export_worker.py` / `ui/export_dialog.py`: generic `QThread` export runner + modal progress dialog, reusable by the Video Maker exporter later
- [x] Verified (offscreen Qt, `QT_QPA_PLATFORM=offscreen`): folder loading, manual drag-reorder simulation, preview frame rendering, and a full export run through `ExportWorker` producing a correct-duration MP4 (with and without an audio track)

### Phase 3 — Video Maker: media pool + preview
- [x] `ui/media_pool.py`: import via file dialog or drag-and-drop, classifies by extension (video/audio/image), generates a video thumbnail via `core/thumbnail.py` (ffmpeg single-frame grab) or loads an image thumbnail directly, supports drag-out (`QDrag`) onto the timeline carrying path + clip type + thumbnail image in the MIME data
- [x] `ui/preview_player.py`: `QMediaPlayer` + `QAudioOutput` + `QVideoWidget` for video/audio playback with scrub bar; static display for images and title/text clips (rendered via `QPainter` onto a `QPixmap`)
- [x] `ui/main_window.py`: media pool (left) + preview (right) in a splitter; selecting a pool item loads it into the preview
- [x] Verified (offscreen): imported a generated sample MP4 and a PNG, confirmed thumbnail/duration/type metadata and correct preview-stack switching between video and image

### Phase 4 — Timeline widget
- [x] `ui/timeline_widget.py`: `QGraphicsView`/`QGraphicsScene` timeline. **Scope decision**: exactly one track per kind (video/audio/text) in v1 — see analysis.md non-goals; this removes the need for cross-track vertical movement entirely (clips only move horizontally on their fixed row)
- [x] `ClipItem`: custom mouse handling (not the built-in `ItemIsMovable`) for move / trim-left / trim-right, with edge-grab zones, hover cursor feedback, and a context menu (toggle crossfade, delete)
- [x] Drag-and-drop from the media pool onto the timeline routes video/image clips to the video track and audio clips to the audio track automatically; thumbnail carried via `QMimeData` image data is cached and painted on the clip rectangle
- [x] Snapping (to 0, the playhead, and adjacent clip edges on the same track) on move/drop
- [x] Split-at-playhead (`S` key or button) — splits the selected clip into two `Clip`s at the current playhead time
- [x] Ruler with adaptive tick spacing, playhead drag-to-scrub (click/drag in the ruler area), zoom +/− (rebuilds geometry from the model at the new scale)
- [x] Double-click an empty slot on the Titles row to add a text/title clip (`QInputDialog` for text + duration)
- [x] Verified: drop+snap, trim-left/trim-right (including clamping a trim-right to the source clip's real duration), move, split-at-playhead, title clip creation, audio-clip routing to the audio track, zoom, delete — all exercised via direct method calls and synthetic events under `QT_QPA_PLATFORM=offscreen`

### Phase 5 — Audio track + title/text overlay clips
- [x] UI mechanics landed as part of Phase 4 (generic drag/drop + double-click-to-add already cover audio and title clips); this phase's remaining scope (drawtext rendering, music mixing) is in Phase 6's export engine

### Phase 6 — Full timeline export engine
- [x] `core/ffmpeg_export.export_timeline()` + `_TimelineGraphBuilder`: builds one `-filter_complex` graph per export —
  - folds the video track left-to-right: trims each clip to its in/out points, scales+pads to the project resolution, concatenates with black-filler segments for any timeline gaps
  - adjacent clips marked `transition_in="crossfade"` are blended with `xfade` (video) / `acrossfade` (audio) using the **visual overlap on the timeline** as the transition length — what you see is what renders, no separate "crossfade duration" setting to keep in sync
  - each video clip's own embedded audio is folded in parallel (mirroring the exact same gap/crossfade structure), with `anullsrc` silence substituted for video clips with no audio stream or for image clips
  - title/text clips are overlaid via `drawtext` with `enable='between(t,start,end)'`, using a `_rendered_time()` mapping that accounts for any time previously removed by completed crossfades, so titles stay aligned after a crossfade shrinks the output
  - the dedicated audio (music) track is delayed per-clip via `adelay` (using the same rendered-time mapping) and mixed in with `amix`
  - handles the no-video-clips edge case (audio/titles only) by synthesizing a black/silent base track
- [x] Reuses the `ExportWorker`/`ExportProgressDialog` from Phase 2; wired to a new "Export Video…" button in `MainWindow`
- [x] Verified against real ffmpeg: cut+gap timeline (exact duration), crossfade timeline (duration = sum − overlap, confirmed exact), mixed video+image clips, and a no-video-clips (audio+title only) edge case — all produced valid playable MP4s with `ffprobe`-confirmed durations

### Phase 7 — Project save/load + polish
- [x] Save/Open Project wired in `MainWindow` (`_save_project`) and `StartScreen._open_project`, using the Phase 1 JSON persistence
- [x] Stop Motion → Video Maker handoff: after a successful stop-motion export, an optional prompt opens a new Video Maker window with the export already in its media pool (verified offscreen)
- [x] ffmpeg-not-found and file-import errors surfaced via `QMessageBox` instead of crashing, in both windows
- [ ] Deferred (not required for v1, noted as a fast-follow): a "recent projects" list on the start screen; Stop Motion has no save/load of its own in-progress session (a session is just "pick a folder + settings," cheap to redo)

### Phase 8 — Manual verification
- [x] Automated verification only — this sandbox has no display server (no Xvfb available, confirmed). Every interaction (drag, trim, split, scrub, export, handoff) was exercised programmatically under `QT_QPA_PLATFORM=offscreen` against real ffmpeg, and `python -m videobuilder.main` was confirmed to boot and run its event loop without error.
- [ ] **Still needs a human pass on a real display**: actually dragging with a mouse, watching video playback, and confirming the UI looks right — run `python -m videobuilder.main` after `source .venv/bin/activate` (see readme.md).
