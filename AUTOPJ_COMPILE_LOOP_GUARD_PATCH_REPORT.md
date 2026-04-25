# AUTOPJ Compile Loop Guard Patch Report

## Summary
Patched autopj to stop repeated compile-repair re-entry when the latest compile repair round already ended with a terminal failure such as `compile_failure_unchanged`, `compile_repair_loop_guard`, or `wrapper_bootstrap_repeated`.

## Root cause fixed
The runtime follow-up orchestrator could call `_run_compile_repair_loop()` again even after the previous compile-repair attempt had already concluded with an unchanged failure signature. That produced repeated `COMPILE-REPAIR round=1` style behavior for the same compile error.

## Files changed
- `app/validation/post_generation_repair.py`
- `tests/test_post_validation_loop_guards.py`

## Key changes
- Added `_compile_repair_exhausted()` helper.
- In `_run_runtime_followup_loops()`, compile repair is no longer re-entered once compile repair is already exhausted.
- Deep-repair and final deep-repair follow-up runtime loops are also blocked when compile repair is exhausted.
- Added regression test ensuring `compile_failure_unchanged` stops repeated compile repair re-entry.

## Validation
- `python -m py_compile app/validation/post_generation_repair.py tests/test_post_validation_loop_guards.py`
- `pytest -q tests/test_post_validation_loop_guards.py`
- Result: `4 passed`
