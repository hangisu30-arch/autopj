# AUTOPJ idempotent schema init patch report

## Base
- autopj_success2_dao_alignment_manifestless_ui_patch.zip

## Changes
- Patched `app/io/execution_core_apply.py`
  - `LoginDatabaseInitializer.java` generator no longer uses `ResourceDatabasePopulator` blindly.
  - Generated initializer now reads SQL resources statement-by-statement.
  - Detects `ALTER TABLE ... ADD COLUMN ...` statements.
  - Checks column existence via `DatabaseMetaData.getColumns(...)` before execution.
  - Skips duplicate add-column statements to avoid startup failures like duplicate `role_cd`.
- Patched `app/ui/prompt_templates.py`
  - Added idempotent schema change rule.
  - Explicitly requires DB metadata / information_schema based guard before `ALTER TABLE ... ADD COLUMN`.

## Regression coverage
- Added `tests/test_auth_initializer_idempotent_schema_regression.py`
  - verifies generated initializer contains column guard logic
  - verifies prompt template includes idempotent alter rule

## Validation
- `python -m py_compile app/io/execution_core_apply.py app/ui/prompt_templates.py`
- `pytest -q tests/test_auth_and_shared_assets_regression.py tests/test_auth_initializer_idempotent_schema_regression.py`
- Result: **8 passed**
