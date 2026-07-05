"""Video Maker main window: media pool + preview + timeline."""
from __future__ import annotations

import os
import tempfile

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..core.ffmpeg_export import FfmpegNotFoundError, export_timeline, require_ffmpeg
from ..core.models import ClipType, Project, Track, TrackKind
from ..core.project_io import PROJECT_EXTENSION, load_project, save_project
from .add_images_dialog import AddImagesDialog
from .export_dialog import ExportProgressDialog
from .export_worker import ExportWorker
from .media_pool import MEDIA_PATH_ROLE, MEDIA_TYPE_ROLE, MediaPool
from .preview_player import PreviewPlayer
from .timeline_widget import TimelineWidget


def _new_default_project() -> Project:
    return Project(
        tracks=[
            Track(kind=TrackKind.VIDEO),
            Track(kind=TrackKind.AUDIO),
            Track(kind=TrackKind.TEXT),
        ]
    )


class MainWindow(QMainWindow):
    def __init__(self, project: Project | None = None, project_path: str | None = None):
        super().__init__()
        self.project = project or _new_default_project()
        self.project_path = project_path
        self.setWindowTitle(f"VideoBuilder — {self.project.name}")
        self.resize(1100, 700)
        self._open_windows: list[MainWindow] = []
        self._preview_tmp_path: str | None = None

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        toolbar = QHBoxLayout()
        new_project_btn = QPushButton("New Project")
        new_project_btn.clicked.connect(self._new_project)
        toolbar.addWidget(new_project_btn)
        open_project_btn = QPushButton("Open Project…")
        open_project_btn.clicked.connect(self._open_project)
        toolbar.addWidget(open_project_btn)
        toolbar.addSpacing(16)
        import_btn = QPushButton("Import Media…")
        import_btn.clicked.connect(self._import_media)
        toolbar.addWidget(import_btn)
        self._add_images_btn = QPushButton("Add Images…")
        self._add_images_btn.clicked.connect(self._add_images)
        toolbar.addWidget(self._add_images_btn)
        save_btn = QPushButton("Save Project…")
        save_btn.clicked.connect(self._save_project)
        toolbar.addWidget(save_btn)
        self._preview_full_btn = QPushButton("▶ Preview Full Video")
        self._preview_full_btn.setToolTip(
            "Renders the whole timeline -- video/images, crossfades, titles, and music mixed together "
            "-- and plays it back here, so you can check how everything blends before exporting."
        )
        self._preview_full_btn.clicked.connect(self._preview_full_video)
        toolbar.addWidget(self._preview_full_btn)
        export_btn = QPushButton("Export Video…")
        export_btn.clicked.connect(self._export_video)
        toolbar.addWidget(export_btn)
        toolbar.addStretch()
        root.addLayout(toolbar)

        splitter = QSplitter()

        pool_panel = QWidget()
        pool_layout = QVBoxLayout(pool_panel)
        pool_layout.setContentsMargins(0, 0, 0, 0)
        self.media_pool = MediaPool()
        self.media_pool.currentItemChanged.connect(self._on_pool_selection_changed)
        pool_layout.addWidget(self.media_pool, stretch=1)

        add_selected_row = QHBoxLayout()
        duration_label = QLabel("Seconds per image:")
        duration_label.setToolTip("Only applies to image clips -- video and audio clips keep their own length.")
        add_selected_row.addWidget(duration_label)
        self._pool_duration_spin = QDoubleSpinBox()
        self._pool_duration_spin.setRange(0.1, 60.0)
        self._pool_duration_spin.setSingleStep(0.5)
        self._pool_duration_spin.setValue(2.0)
        self._pool_duration_spin.setToolTip("Only applies to image clips -- video and audio clips keep their own length.")
        add_selected_row.addWidget(self._pool_duration_spin)
        add_selected_btn = QPushButton("Add Selected to Timeline (at end)")
        add_selected_btn.setToolTip(
            "Video/image clips append to the end of the Video track; audio clips append to the end of the Audio track."
        )
        add_selected_btn.clicked.connect(self._add_selected_to_timeline)
        add_selected_row.addWidget(add_selected_btn)
        pool_layout.addLayout(add_selected_row)

        splitter.addWidget(pool_panel)

        self.preview_player = PreviewPlayer()
        splitter.addWidget(self.preview_player)
        splitter.setSizes([350, 750])
        root.addWidget(splitter, stretch=1)

        self.timeline = TimelineWidget(self.project)
        self.timeline.clip_selected.connect(self._on_timeline_clip_selected)
        root.addWidget(self.timeline)

        self._dirty = False
        self.timeline.project_modified.connect(self._mark_dirty)
        QShortcut(QKeySequence.StandardKey.Save, self, activated=self._save_project)
        QShortcut(QKeySequence.StandardKey.Undo, self, activated=self.timeline.undo)
        QShortcut(QKeySequence.StandardKey.Redo, self, activated=self.timeline.redo)

    def _mark_dirty(self) -> None:
        self._dirty = True
        self.setWindowTitle(f"VideoBuilder — {self.project.name} *")

    def _new_project(self) -> None:
        window = MainWindow()
        window.show()
        self._open_windows.append(window)

    def _open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Project", "", f"VideoBuilder Project (*{PROJECT_EXTENSION})"
        )
        if not path:
            return
        try:
            project = load_project(path)
        except Exception as exc:
            QMessageBox.critical(self, "Could not open project", str(exc))
            return
        window = MainWindow(project=project, project_path=path)
        window.show()
        self._open_windows.append(window)

    def _import_media(self) -> None:
        self.media_pool.import_files_dialog()

    def _add_images(self) -> None:
        dialog = AddImagesDialog(self)
        if dialog.exec() != AddImagesDialog.DialogCode.Accepted:
            return
        if not dialog.image_paths:
            return

        def after_import() -> None:
            self._add_images_btn.setEnabled(True)
            self._add_images_btn.setText("Add Images…")
            if dialog.arrange_sequentially:
                self.timeline.add_image_sequence(
                    dialog.image_paths, dialog.seconds_per_image, thumbnail_lookup=self.media_pool.icon_for_path
                )

        self._add_images_btn.setEnabled(False)
        self._add_images_btn.setText(f"Importing {len(dialog.image_paths)} images…")
        self.media_pool.import_images_async(dialog.image_paths, on_finished=after_import)

    def _add_selected_to_timeline(self) -> None:
        selected_items = sorted(self.media_pool.selectedItems(), key=self.media_pool.row)
        entries = [
            (item.data(MEDIA_PATH_ROLE), ClipType(item.data(MEDIA_TYPE_ROLE)))
            for item in selected_items
        ]
        if not entries:
            QMessageBox.information(
                self, "Nothing selected",
                "Select one or more items in the pool above (Ctrl/Shift-click for multiple), then click this button.",
            )
            return
        self.timeline.add_clips_sequence(
            entries, self._pool_duration_spin.value(), thumbnail_lookup=self.media_pool.icon_for_path
        )

    def _on_pool_selection_changed(self, current, _previous) -> None:
        if current is None:
            self.preview_player.clear()
            return
        path = current.data(MEDIA_PATH_ROLE)
        clip_type = ClipType(current.data(MEDIA_TYPE_ROLE))
        self.preview_player.load(path, clip_type)

    def _on_timeline_clip_selected(self, clip) -> None:
        if clip is None:
            self.preview_player.clear()
            return
        if clip.clip_type == ClipType.IMAGE:
            # A lone static image has nothing to "play" -- but if it's part
            # of a run of image clips on the timeline, flip through that run
            # (in order, at each clip's own duration) starting from this one,
            # like previewing a slideshow rather than seeing one frozen frame.
            video_track = self.project.tracks[self.timeline._track_index_for_kind(TrackKind.VIDEO)]
            clips_sorted = sorted(video_track.clips, key=lambda c: c.start_time)
            start_idx = next(i for i, c in enumerate(clips_sorted) if c is clip)
            sequence = []
            for c in clips_sorted[start_idx:]:
                if c.clip_type != ClipType.IMAGE:
                    break
                sequence.append((c.source_path, c.duration))
            self.preview_player.load_image_sequence(sequence)
            return
        self.preview_player.load(clip.source_path, clip.clip_type, text=clip.text)

    def _preview_full_video(self) -> None:
        has_clips = any(track.clips for track in self.project.tracks)
        if not has_clips:
            QMessageBox.information(self, "Nothing to preview", "Add some clips to the timeline first.")
            return

        try:
            require_ffmpeg()
        except FfmpegNotFoundError as exc:
            QMessageBox.critical(self, "ffmpeg not found", str(exc))
            return

        self._cleanup_preview_tmp_file()
        fd, tmp_path = tempfile.mkstemp(suffix=".mp4", prefix="videobuilder_preview_")
        os.close(fd)
        self._preview_tmp_path = tmp_path

        worker = ExportWorker(export_timeline, project=self.project, output_path=tmp_path)
        dialog = ExportProgressDialog(worker, title="Rendering preview…", parent=self)
        if dialog.run():
            self.preview_player.load(tmp_path, ClipType.VIDEO)
            self.preview_player.toggle_play()

    def _cleanup_preview_tmp_file(self) -> None:
        if self._preview_tmp_path and os.path.exists(self._preview_tmp_path):
            try:
                os.remove(self._preview_tmp_path)
            except OSError:
                pass
        self._preview_tmp_path = None

    def closeEvent(self, event) -> None:
        if self._dirty:
            choice = QMessageBox.question(
                self,
                "Unsaved changes",
                "This project has unsaved changes. Save before closing?",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )
            if choice == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if choice == QMessageBox.StandardButton.Save:
                self._save_project()
                if self._dirty:  # user cancelled the save dialog
                    event.ignore()
                    return
        self._cleanup_preview_tmp_file()
        super().closeEvent(event)

    def _export_video(self) -> None:
        has_clips = any(track.clips for track in self.project.tracks)
        if not has_clips:
            QMessageBox.information(self, "Nothing to export", "Add some clips to the timeline first.")
            return

        output_path, _ = QFileDialog.getSaveFileName(self, "Export Video", "video.mp4", "MP4 Video (*.mp4)")
        if not output_path:
            return
        if not output_path.lower().endswith(".mp4"):
            output_path += ".mp4"

        try:
            require_ffmpeg()
        except FfmpegNotFoundError as exc:
            QMessageBox.critical(self, "ffmpeg not found", str(exc))
            return

        worker = ExportWorker(export_timeline, project=self.project, output_path=output_path)

        dialog = ExportProgressDialog(worker, title="Exporting video…", parent=self)
        if dialog.run():
            QMessageBox.information(self, "Export complete", f"Saved to:\n{output_path}")

    def _save_project(self) -> None:
        path = self.project_path
        if not path:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Project", f"{self.project.name}{PROJECT_EXTENSION}",
                f"VideoBuilder Project (*{PROJECT_EXTENSION})",
            )
            if not path:
                return
            self.project_path = path
        try:
            save_project(self.project, path)
        except Exception as exc:
            QMessageBox.critical(self, "Could not save project", str(exc))
            return
        self._dirty = False
        self.setWindowTitle(f"VideoBuilder — {self.project.name}")
        QMessageBox.information(self, "Saved", f"Project saved to:\n{path}")
