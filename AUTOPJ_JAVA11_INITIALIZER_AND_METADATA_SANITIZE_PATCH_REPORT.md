# AUTOPJ Java 11 Initializer + Metadata Sanitize Patch Report

## Summary
Patched autopj to address two recurring failures seen in generated member schedule projects:

1. `LoginDatabaseInitializer.java` emitted Java text/char escaping that broke Java 11 compilation.
2. Non-auth JSP sanitize logic could leave generation metadata (`db`, `schemaName`, `tableName`, `packageName`) behind, and in one case removed neighboring safe markup due to an overly broad regex.

## Files changed
- `app/io/execution_core_apply.py`
- `app/validation/post_generation_repair.py`
- `tests/test_login_initializer_java11_and_metadata_sanitize.py`

## Details
### 1) Java 11-safe `LoginDatabaseInitializer.java`
The generator now writes escaped Java literals correctly:
- `replace("\"", "")`
- `'\\0'`
- `'\\n'`
- `'\\''`

This prevents compile errors such as:
- `text blocks are not supported in -source 11`
- `illegal text block open delimiter sequence`
- `empty character literal`
- `illegal line end in character literal`
- `unclosed character literal`

### 2) Stronger metadata sanitize
`_sanitize_frontend_ui_file()` now:
- removes metadata-bearing HTML comments
- uses tag-name-aware paired-tag removal instead of a broad greedy pattern
- removes self-closing/common form tags with metadata attributes safely
- preserves neighboring safe markup while removing metadata leaks

## Validation
- `python -m py_compile app/validation/post_generation_repair.py app/io/execution_core_apply.py`
- `PYTHONPATH=. pytest -q tests/test_login_initializer_java11_and_metadata_sanitize.py tests/test_auth_initializer_idempotent_schema_regression.py`

Result: **4 passed**
