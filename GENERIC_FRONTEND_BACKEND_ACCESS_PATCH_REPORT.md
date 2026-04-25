# Generic access-control and auth-sensitive UI patch

## Goal
Patch autopj so owner/admin separation and auth-sensitive field exclusion work as generic policy, not JSP-only hardcoding.

## What changed
- Added generic IR metadata for:
  - `access.mode`
  - owner field candidates
  - role field candidates
  - auth-sensitive fields
- Marked password-like fields as `authSensitive` in the analysis data model.
- Carried the metadata into:
  - backend plan
  - JSP plan
  - React plan
  - Vue plan
- Strengthened prompt generation so JSP/React/Vue/backend all receive the same rules:
  - do not expose auth-sensitive fields outside auth screens
  - when requirements imply owner/admin split, separate user/admin surfaces using owner + role + session/token context
- Added generic content validation to reject non-auth JSP/React/Vue UI files that expose password-like fields.

## Files changed
- `app/engine/analysis/ir_builder.py`
- `app/engine/analysis/ir_support.py`
- `app/engine/backend/backend_contracts.py`
- `app/engine/backend/backend_task_builder.py`
- `app/engine/backend/backend_prompt_builder.py`
- `app/adapters/jsp/jsp_contracts.py`
- `app/adapters/jsp/jsp_task_builder.py`
- `app/adapters/jsp/jsp_prompt_builder.py`
- `app/adapters/jsp/jsp_validator.py`
- `app/adapters/react/react_contracts.py`
- `app/adapters/react/react_task_builder.py`
- `app/adapters/react/react_prompt_builder.py`
- `app/adapters/react/react_validator.py`
- `app/adapters/vue/vue_contracts.py`
- `app/adapters/vue/vue_task_builder.py`
- `app/adapters/vue/vue_prompt_builder.py`
- `app/adapters/vue/vue_validator.py`
- `app/ui/generated_content_validator.py`
- `app/ui/prompt_templates.py`
- `tests/test_generic_access_and_sensitive_field_rules.py`

## Validation
- Targeted new regression tests: passed
- Selected existing regression/smoke subset: passed
- Combined run reported: 9 passed
