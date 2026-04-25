# AUTOPJ DAO Overload and UI Sanitize Patch Report

## Summary
This patch fixes two recurring error classes observed in generated `memberSchedule` projects:

1. `MemberScheduleDAO.java` compile failures caused by mapper overload/signature mismatch.
2. `memberScheduleList.jsp` and related JSPs exposing generation metadata or placeholder fields in non-auth UI.

## Changes
- `execution_core/builtin_crud.py`
  - Read-only mapper interface now includes both:
    - `select{E}List()`
    - `select{E}List(Map<String, Object> params)`
  - Read-only service interface and service implementation now expose the same overload pair.
- `app/validation/backend_compile_repair.py`
  - DAO→Mapper alignment upgraded from name-only matching to signature-aware matching.
  - Missing overloaded mapper methods are added even when a method with the same name already exists.
- `app/validation/post_generation_repair.py`
  - Stronger sanitization for non-auth UI:
    - generation metadata fields: `db`, `schemaName`, `tableName`, `packageName`, `frontendType`, `backendType`
    - placeholder fields: `repeat7`, `section`
  - Plain text headers/labels and bound expressions are removed more aggressively.
- `tests/test_read_only_mapper_signature_and_ui_sanitize.py`
  - Added regression coverage for read-only mapper overload generation, overload-aware DAO/Mapper alignment, and JSP metadata sanitization.

## Validation
- `python -m py_compile` on modified modules: passed
- `pytest -q tests/test_read_only_mapper_signature_and_ui_sanitize.py tests/test_compile_dao_alignment_and_manifestless_ui_sanitize.py tests/test_generic_dao_fallback_and_ui_sanitize.py`
- Result: `7 passed`
