# Schedule calendar route/view/header consistency fix

## Fixed
- JSP task planner now creates `scheduleCalendar.jsp` instead of `scheduleList.jsp` for schedule/calendar features.
- JSP task planner now also creates `jsp/common/header.jsp`.
- Built-in JSP renderer supports `jsp/common/header.jsp` output.
- Built-in schedule JSP pages include `/WEB-INF/views/common/header.jsp`.
- Post-generation validation now checks:
  - controller `return "..."` view names must resolve to real JSP files
  - schedule controllers must not keep `/list.do`
  - schedule main return must be `schedule/scheduleCalendar`
  - JSP include of `/WEB-INF/views/common/header.jsp` must point to a real file
- Post-generation repair now auto-normalizes generated `ScheduleController.java`:
  - `/list.do` -> `/calendar.do`
  - `/detail.do` -> `/view.do`
  - `/form.do` -> `/edit.do`
  - `/delete.do` -> `/remove.do`
  - `schedule/scheduleList` -> `schedule/scheduleCalendar`
- Missing `src/main/webapp/WEB-INF/views/common/header.jsp` is auto-created during repair.

## Validation
- `python -m compileall app execution_core tests`
- `PYTHONPATH=. pytest -q tests/test_schedule_task_builder_paths.py tests/test_schedule_header_and_view_consistency.py tests/test_schedule_calendar_routes.py tests/test_schedule_fallback_builder.py`
