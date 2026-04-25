# Schedule calendar route/name/runtime validation patch

What changed:
- Schedule/calendar generation is no longer treated as read-only CRUD.
- `ScheduleController` main entry now uses `@GetMapping("/calendar.do")` instead of `list.do`.
- Schedule routes now use:
  - `/calendar.do`
  - `/view.do`
  - `/edit.do`
  - `/save.do`
  - `/remove.do`
- Main JSP/view name is aligned to `schedule/scheduleCalendar`.
- `index.jsp` now redirects to `/schedule/calendar.do` for schedule features.
- Builtin schedule JSP fallback now renders a real monthly calendar layout with a side event panel.
- System fields (`writerId`, `useYn`, `regDt`, `updDt`) are excluded from schedule form inputs.
- Post-generation validation now checks controller return-view ↔ actual JSP consistency and flags missing JSP targets.
- Schedule controllers using `/list.do` are treated as invalid.

Validated:
- `python -m compileall app execution_core tests`
- `PYTHONPATH=. pytest -q tests/test_schedule_calendar_routes.py tests/test_ir_analysis_calendar.py tests/test_ir_driven_jsp_builder.py tests/test_post_generation_repair.py tests/test_execution_core_apply_import_fix.py`
