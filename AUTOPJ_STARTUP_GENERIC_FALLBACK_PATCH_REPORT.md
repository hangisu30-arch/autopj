# AUTOPJ STARTUP GENERIC FALLBACK PATCH REPORT

## What changed
- Added generic startup fallback issue generation in `app/validation/post_generation_repair.py`.
- When startup fails and parsed issues resolve only to framework/internal paths or empty paths, autopj now synthesizes project-local repair targets such as:
  - `schema.sql`
  - `*DatabaseInitializer.java`
  - `*Initializer.java`
  - `*Config.java`
  - `*Mapper.xml`
  - `*ServiceImpl.java`
  - `*DAO.java`
  - `*Controller.java`
- If the first startup auto-repair pass changes nothing and only skip/no_change style results are present, autopj now reruns startup auto-repair with those fallback project-local targets.

## Why
Recent runs ended with:
- `compile=ok`
- `startup=failed`
- final invalid only `spring boot startup validation failed`

The startup parser was identifying framework stack frames rather than actionable project files, so startup repair had targets but changed nothing (`changed=0, skipped=3`).

## Validation
- `python -m py_compile app/validation/post_generation_repair.py`
- `pytest -q tests/test_startup_generic_fallback_targets.py`

## Result
Startup failures that only surface as generic Spring bean creation / application run failed traces now get mapped back to project files so startup repair can act deterministically.
