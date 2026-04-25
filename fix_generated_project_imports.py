from __future__ import annotations

import sys
from pathlib import Path

from app.ui.java_import_fixer import fix_project_java_imports


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python fix_generated_project_imports.py <project_root>")
        return 2
    project_root = Path(sys.argv[1]).resolve()
    changed = fix_project_java_imports(project_root)
    print(f"changed_count={len(changed)}")
    for path in changed:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
