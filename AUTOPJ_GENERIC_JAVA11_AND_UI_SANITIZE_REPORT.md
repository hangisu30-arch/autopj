# AUTOPJ Generic Java11 + UI Sanitize Patch Report

## Goal
Make the recent fixes reusable across domains instead of only masking `memberSchedule` symptoms.

## What changed

### 1) Java 11-safe initializer generation
- Rewrote `app/io/execution_core_apply.py::_write_auth_database_initializer`
- Generates `LoginDatabaseInitializer.java` from a single stable template
- Avoids malformed escaping around regex, quotes, `\0`, and `\n`
- Keeps initializer idempotent for repeated schema/data execution

### 2) Generic frontend UI sanitize expansion
- Updated `app/validation/post_generation_repair.py`
- `generation metadata`, `auth-sensitive`, and `undefined vo properties` reasons now sanitize with a broader marker set
- Removes leaks like `db`, `schemaName`, `tableName`, `packageName`, `frontendType`, `backendType`, `repeat7`, `section`
- Sanitizes full sibling UI files in the same folder, not just the single flagged file
- Works for JSP / Vue / React file extensions handled by the repair flow

### 3) Regression coverage
Added/updated tests to verify:
- Java 11-safe initializer output
- related UI file sanitize across a domain folder
- existing metadata/auth-sensitive validation compatibility

## Validation
- `python -m py_compile` passed for patched modules
- `pytest -q tests/test_generic_java_init_and_ui_sanitize.py tests/test_java11_initializer_and_metadata_guard.py tests/test_login_initializer_java11_and_metadata_sanitize.py`
- Result: **6 passed**
