# Boolean Getter Ambiguity Fix

## Fixed problem
MyBatis failed on VO classes where a single boolean/Boolean property declared both `getXxx()` and `isXxx()` getters.

## Applied changes
- `execution_core/builtin_crud.py`
  - stop generating duplicate `isXxx()` getter when `getXxx()` already exists for boolean/Boolean fields
- `app/validation/post_generation_repair.py`
  - normalize generated `*VO.java` files to keep only `getXxx()` for boolean/Boolean fields
- `app/ui/generated_content_validator.py`
  - reject Java files that still declare both getters for the same boolean/Boolean property
- prompt rules updated
  - `app/engine/backend/backend_prompt_builder.py`
  - `app/adapters/jsp/jsp_prompt_builder.py`
  - `app/ui/prompt_templates.py`
- tests added
  - `tests/test_boolean_getter_guard.py`

## Validation executed
- `python -m py_compile execution_core/builtin_crud.py app/validation/post_generation_repair.py app/ui/generated_content_validator.py app/engine/backend/backend_prompt_builder.py app/adapters/jsp/jsp_prompt_builder.py app/ui/prompt_templates.py tests/test_boolean_getter_guard.py`
- `PYTHONPATH=. pytest -q tests/test_boolean_getter_guard.py tests/test_date_consistency_generation.py tests/test_vo_date_format_and_active_nav.py tests/test_schedule_calendar_routes.py`
