"""Page 1 · Start: drop or browse for one or more data folders."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

from ..model import Session
from ..theme import Header, vbox


class MainPage(QWidget):
    folders_added = Signal()

    def __init__(self, session: Session, on_readme):
        super().__init__()
        self.session = session
        from ..widgets.drop_zone import FolderDropZone
        lay = vbox(self)
        self.header = Header("", on_readme)
        lay.addWidget(self.header)
        body = QWidget()
        bl = vbox(body, (24, 24, 24, 24))
        self.zone = FolderDropZone(self.browse)
        self.zone.dropped.connect(self.add_paths)
        bl.addStretch(1)
        bl.addWidget(self.zone, 0, Qt.AlignCenter)
        bl.addStretch(1)
        lay.addWidget(body, 1)

    def browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Choose a data folder", os.path.expanduser("~"))
        if d:
            self.add_paths([d])

    def add_paths(self, paths) -> None:
        errors = []
        for p in paths:
            e = self.session.add_root(p)
            if e:
                errors.append(e)
        if errors:
            QMessageBox.warning(self, "Folder not added", "\n\n".join(errors))
        if self.session.roots:
            self.folders_added.emit()
