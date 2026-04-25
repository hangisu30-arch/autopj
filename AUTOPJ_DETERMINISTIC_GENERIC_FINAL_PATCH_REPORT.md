# AUTOPJ deterministic + generic final patch

## What changed
- Rewrote `LoginDatabaseInitializer.java` generation to a deterministic line-template builder.
- Removed unstable regex/text-block style generation paths for the initializer.
- Kept idempotent schema bootstrap behavior (`ALTER TABLE ... ADD COLUMN ...` skip when column already exists).
- Made non-auth UI metadata sanitize broader and generic:
  - sanitize related sibling UI files even when the primary file itself was not changed first
  - keep the same metadata marker set across validator/repair flow

## Why
Recent logs repeatedly showed:
- Java 11 compile failures in `LoginDatabaseInitializer.java`
- lingering `db/schemaName/tableName/packageName` leakage in non-auth JSP files

## Validation
- `python -m py_compile app/io/execution_core_apply.py app/validation/post_generation_repair.py`
- `pytest -q tests/test_deterministic_generic_initializer_and_ui_sanitize.py tests/test_generic_java_init_and_ui_sanitize.py tests/test_java11_initializer_and_metadata_guard.py`
- Result: 6 passed
