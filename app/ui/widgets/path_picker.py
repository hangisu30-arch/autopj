from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QPushButton, QFileDialog


class FolderPicker(QWidget):
    changed = pyqtSignal(str)

    def __init__(self, *, placeholder: str = ""):
        super().__init__()
        self._edit = QLineEdit()
        self._edit.setPlaceholderText(placeholder)
        self._btn = QPushButton("찾아보기")
        self._btn.setMinimumWidth(96)
        self._btn.clicked.connect(self._pick)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self._edit, 1)
        layout.addWidget(self._btn, 0)

        self._edit.textChanged.connect(lambda _: self.changed.emit(self.value()))

    def value(self) -> str:
        return self._edit.text().strip()

    def set_value(self, v: str) -> None:
        self._edit.setText(v or "")

    def _pick(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "프로젝트 출력 폴더 선택")
        if d:
            self._edit.setText(d)
