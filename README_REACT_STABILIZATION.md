# React Stabilization Integration

This patch adds a React planning layer that sits on top of the common analysis engine and common backend engine.

Added:
- `app/adapters/react/*`
- `app/ui/react_bridge.py`
- `tests/smoke_test_react_engine.py`
- `tests/smoke_test_react_integration.py`

Behavior:
- When frontend is `react`, the UI flow computes `react_plan.json` under `.autopj_debug`.
- The Gemini prompt now includes `[REACT GENERATION PLAN - SOURCE OF TRUTH]`.
- React planning forces central routes, API client/service separation, and page generation paths under `frontend/react`.
