# path: app/ui/file_loader.py
from __future__ import annotations

from typing import Tuple


def read_text_file_best_effort(path: str) -> Tuple[bool, str]:
    for enc in ("utf-8", "utf-8-sig", "cp949"):
        try:
            with open(path, "r", encoding=enc) as f:
                return True, f.read()
        except Exception:
            continue
    return False, "파일을 읽을 수 없습니다. (utf-8/utf-8-sig/cp949 모두 실패)"
