from __future__ import annotations

from PyQt6.QtWidgets import QGroupBox


def make_section(title: str, object_name: str, bg_color: str) -> QGroupBox:
    box = QGroupBox(title)
    box.setObjectName(object_name)
    box.setStyleSheet(
        f"""
        QGroupBox#{object_name} {{
            border: 1px solid #d7dce5;
            border-radius: 12px;
            margin-top: 14px;
            padding: 12px;
            background: {bg_color};
        }}
        QGroupBox#{object_name}::title {{
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 6px;
            color: #0f172a;
            font-weight: 700;
        }}
        """
    )
    return box
