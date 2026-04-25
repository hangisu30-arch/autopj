# IR-centered analysis/planning patch

## What changed
- Added `domain.ir` generation with classification, mainEntry, capabilities, dataModel, queries, actions, ui, backendArtifacts, frontendArtifacts, validationRules.
- Added top-level `ir_version` and `generation_policy` to `analysis_result.json`.
- Switched analysis flow to build IR first, then derive legacy `pages`, `api_endpoints`, and `file_generation_plan` from IR.
- Updated backend/JSP/React/Vue/Nexacro task builders to prefer IR artifact paths and main-entry definitions over generic CRUD defaults.
- Extended classifier with calendar/schedule intent so monthly-calendar style domains can be represented as `feature_kind=schedule` + `primaryPattern=calendar`.
- Strengthened validation to require IR blocks and check calendar main-entry consistency / hidden form fields.
- Added IR-focused tests.

## Key files changed
- `app/engine/analysis/analysis_result.py`
- `app/engine/analysis/analysis_engine.py`
- `app/engine/analysis/requirement_parser.py`
- `app/engine/analysis/domain_classifier.py`
- `app/engine/analysis/artifact_planner.py`
- `app/engine/analysis/ir_builder.py` (new)
- `app/engine/analysis/ir_support.py` (new)
- `app/engine/backend/backend_task_builder.py`
- `app/adapters/jsp/jsp_task_builder.py`
- `app/adapters/react/react_task_builder.py`
- `app/adapters/vue/vue_task_builder.py`
- `app/adapters/nexacro/nexacro_task_builder.py`
- `app/ui/analysis_bridge.py`
- `app/validation/global_validator.py`
- `app/validation/error_classifier.py`
- `app/validation/repair_dispatcher.py`
- `tests/test_ir_analysis_calendar.py` (new)
- `tests/test_ir_driven_jsp_builder.py` (new)
- `tests/test_ir_driven_react_builder.py` (new)

## Validation run
- `python -m compileall app execution_core tests`
- `PYTHONPATH=. pytest -q tests/test_ir_analysis_calendar.py tests/test_ir_driven_jsp_builder.py tests/test_ir_driven_react_builder.py`
- `PYTHONPATH=. python tests/smoke_test_analysis_integration.py`
- `PYTHONPATH=. python tests/smoke_test_jsp_engine.py`
- `PYTHONPATH=. python tests/smoke_test_react_integration.py`
- `PYTHONPATH=. python tests/smoke_test_vue_integration.py`
- `PYTHONPATH=. python tests/smoke_test_analysis.py`
- `PYTHONPATH=. python tests/smoke_test_backend_integration.py`
- `PYTHONPATH=. python tests/smoke_test_validation_feature_kind_mismatch.py`
