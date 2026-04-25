# Validation / Auto-repair Integration

This stage adds a global validation layer and a targeted auto-repair planning layer.

## Added modules
- `app/validation/global_validator.py`
- `app/validation/error_classifier.py`
- `app/validation/repair_dispatcher.py`
- `app/validation/file_regenerator.py`
- `app/ui/validation_bridge.py`

## What it does
- Validates the combined generation context:
  - analysis result
  - backend plan
  - JSP plan (when frontend is JSP)
  - React plan (when frontend is React)
- Saves `.autopj_debug/validation_report.json`
- Saves `.autopj_debug/repair_plan.json`
- Injects validation + repair source-of-truth blocks into the Gemini planner prompt
- Strengthens single-file regenerate prompts with targeted repair hints

## Current scope
This is a deterministic validation and repair-planning layer. It does not replace the existing generation engine. It narrows repair to the most relevant files/modules and reinforces the current regenerate loop.
