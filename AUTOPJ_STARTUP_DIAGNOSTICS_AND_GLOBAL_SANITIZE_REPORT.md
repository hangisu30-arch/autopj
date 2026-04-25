# AUTOPJ startup diagnostics + global frontend sanitize patch

## What changed
- Added generic startup log source extraction in `app/validation/runtime_smoke.py`
  - stacktrace FQCN -> `src/main/java/...`
  - `class path resource [schema.sql]` -> `src/main/resources/schema.sql`
  - duplicate column detail extraction
- Added generic startup repair mapping in `app/validation/post_generation_repair.py`
  - `sql_error`, `bean_creation`, `application_run_failed` -> `startup_sql_schema_issue`
- Added global frontend metadata sanitize pass in `app/validation/post_generation_repair.py`
  - sanitizes all JSP/React/Vue UI files for generation metadata markers before final validation
- Added generic startup SQL/schema repair in `app/validation/project_auto_repair.py`
  - rewrites `*DatabaseInitializer.java` / `LoginDatabaseInitializer.java` to deterministic Java 11-safe initializer template
  - strips unconditional `ALTER TABLE ... ADD COLUMN ...` statements from schema SQL when targeted

## Why
- Startup failures were ending as generic `spring boot startup validation failed` because runtime errors had no repairable path.
- Non-auth generation metadata sometimes remained in sibling UI files such as `memberScheduleList.jsp` even after local sanitize.

## Validation
- `python -m py_compile` passed for patched modules
- `pytest -q tests/test_startup_runtime_diagnostics_and_global_metadata_sanitize.py tests/test_post_validation_loop_guards.py`
- 7 tests passed
