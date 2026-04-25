# AUTOPJ deterministic + generic alias patch report

Applied generic engine-level fixes to stabilize JSP field-contract repair and metadata sanitization.

## What changed
- Added generic base-name normalization for numbered placeholder fields like `title_2`, `startDate_3`, `location_2`.
- Added semantic alias replacement rules so generic UI names map deterministically to business fields:
  - `title` -> `scheduleTitle` / `reservationTitle` / `boardTitle`
  - `startDate` -> `startDatetime` / `beginDatetime`
  - `endDate` -> `endDatetime` / `finishDatetime`
  - `location` -> `locationText` / `locationName`
  - `memberNo_2` -> `memberNo`
- Updated JSP property repair to also rewrite `name/id/for/path` attributes, not only `${item.foo}` bindings.
- Strengthened metadata sanitization to remove label/header artifacts for generation metadata markers.

## Files changed
- `app/validation/generated_project_validator.py`
- `app/validation/project_auto_repair.py`
- `tests/test_generic_jsp_alias_and_metadata_repair.py`

## Validation run
- `python -m py_compile app/validation/project_auto_repair.py app/validation/generated_project_validator.py`
- `pytest -q tests/test_auth_initializer_idempotent_schema_regression.py tests/test_generic_jsp_alias_and_metadata_repair.py`
- Result: **5 passed**
