# AUTOPJ startup remap + global UI sanitize patch

## What changed
- Runtime startup diagnostics now remap Spring/internal framework paths to real project files.
- Added startup issue inference from runtime log text:
  - `class path resource [schema.sql]`
  - SQL/schema mismatch signals
  - bean creation / dependency wiring signals
- Startup runtime issue map expanded to include:
  - `application_run_failed`
  - `bean_creation`
  - `unsatisfied_dependency`
  - `sql_error`
  - `mapper_xml_missing`
  - `mybatis_binding`
- Added global frontend sanitize for non-auth UI metadata leakage across JSP/React/Vue UI trees.
- Added startup auto-repair handlers:
  - `startup_sql_schema_issue`
  - `startup_bean_wiring_issue`
- Schema auto-repair can dedupe duplicate `ALTER TABLE ... ADD COLUMN ...` statements.
- Database initializer startup repair can rewrite `*DatabaseInitializer.java` using the deterministic Java 11-safe generator.
- Runtime invalid aggregation now ignores Spring/internal framework source paths.

## Files changed
- `app/validation/post_generation_repair.py`
- `app/validation/project_auto_repair.py`
- `tests/test_startup_path_remap_and_global_ui_sanitize.py`

## Validation
- `python -m py_compile app/validation/post_generation_repair.py app/validation/project_auto_repair.py`
- `PYTHONPATH=. pytest -q tests/test_runtime_smoke_pipeline.py tests/test_generic_java_init_and_ui_sanitize.py tests/test_deterministic_generic_initializer_and_ui_sanitize.py tests/test_startup_path_remap_and_global_ui_sanitize.py`
- Result: `20 passed`
