# AUTOPJ Search Metadata & Smoke Guard Patch Report

## What changed

1. `app/validation/generated_project_validator.py`
   - Added shared generation-metadata/auth-sensitive marker sets.
   - Search UI completeness validation now excludes generation metadata fields (`db`, `schemaName`, `tableName`, `packageName`, etc.) and auth-sensitive fields.
   - This removes the contradiction where a non-auth UI was told to both hide and expose metadata fields.

2. `app/validation/post_generation_repair.py`
   - Added project source snapshot/restore helpers for smoke-repair safety.
   - Added compile/startup health predicate.
   - Smoke repair now restores prior source state when a smoke-only repair degrades compile/startup from an already healthy compile/startup baseline.
   - Prevents endpoint-smoke repairs from turning a compile-ok/startup-ok project back into compile-failed.

3. Tests
   - Added `tests/test_search_metadata_and_smoke_degrade_guard.py`
   - Covers metadata exclusion from search field completeness and smoke repair degradation guard.

## Validation

- `python -m py_compile app/validation/generated_project_validator.py app/validation/post_generation_repair.py`
- `pytest -q tests/test_search_metadata_and_smoke_degrade_guard.py`
- Result: `2 passed`
