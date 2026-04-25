# AUTOPJ deterministic/generic search-metadata + smoke-loop guard patch

## What changed
- Excluded generation metadata and synthetic placeholder fields from search-field completeness validation.
- Tightened UI metadata exposure validator so it only triggers on real binding/rendering contexts, not arbitrary plain text.
- Hardened search auto-repair to strip forbidden metadata/auth fields before adding missing search inputs.
- Added smoke-repair guard to revert any smoke change that does not improve runtime quality, and stop further smoke loops on `endpoint_smoke_unchanged`.

## Files changed
- app/validation/generated_project_validator.py
- app/ui/generated_content_validator.py
- app/validation/project_auto_repair.py
- app/validation/post_generation_repair.py
- tests/test_generic_search_metadata_and_smoke_round_guard.py

## Verification
- `python -m py_compile app/validation/generated_project_validator.py app/ui/generated_content_validator.py app/validation/project_auto_repair.py app/validation/post_generation_repair.py`
- `pytest -q tests/test_generic_search_metadata_and_smoke_round_guard.py`
- Result: 3 passed
