# JSP Controller Guard Patch

This patch keeps JSP MVC controllers thin and blocks malformed JSP/MyBatis backend artifacts that were appearing in generated CRUD output.

## What changed
- Added stricter JSP/MyBatis backend rules to backend/jsp prompt builders and the global prompt template.
- Added extra validation in `execution_core/generator.py` for:
  - invalid `MyBatisConfig.java`
  - missing `Service` / `ServiceImpl` imports
  - mixed annotation + XML mapper generation
  - invalid JSP controller VO binding
  - polluted `Mapper.xml` content
  - boot scan mismatch risk
- Kept the existing JSP controller guard and added a final deterministic builtin fallback after repeated validation failure when a builtin template is available.
- Expanded validation error classification and repair mapping for the new backend guard failures.
- Added a new smoke test that reproduces the malformed file patterns and verifies they are rejected.

## Files changed
- `execution_core/generator.py`
- `app/engine/backend/backend_prompt_builder.py`
- `app/adapters/jsp/jsp_prompt_builder.py`
- `app/ui/prompt_templates.py`
- `app/validation/error_classifier.py`
- `app/validation/repair_dispatcher.py`
- `tests/smoke_test_jsp_controller_guard.py`
- `tests/smoke_test_prompt_contains_jsp_controller_rules.py`
- `tests/smoke_test_jsp_backend_file_guards.py`

## Validation
- `python -m compileall app execution_core tests`
- `PYTHONPATH=. python tests/smoke_test_jsp_controller_guard.py`
- `PYTHONPATH=. python tests/smoke_test_prompt_contains_jsp_controller_rules.py`
- `PYTHONPATH=. python tests/smoke_test_jsp_backend_file_guards.py`
