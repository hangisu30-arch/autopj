# Import fix v2

## What changed
- Improved `app/ui/java_import_fixer.py` to add **missing imports** even when a Java file already compiles structurally but has no import for a referenced internal type like `ScheduleVO`.
- Fixed same-package detection so subpackages like `.service.vo` are imported correctly from `.service`.
- Added standard import inference for common Java/Spring/MyBatis/time types.
- Added `fix_generated_project_imports.py` to repair an already-generated project in place.
- Added tests for missing internal import and missing standard import.

## Main files
- `app/ui/java_import_fixer.py`
- `tests/test_java_import_fixer_missing_internal.py`
- `fix_generated_project_imports.py`
