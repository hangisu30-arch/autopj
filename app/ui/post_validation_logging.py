from __future__ import annotations

from app.validation.compile_error_parser import summarize_compile_errors


def post_validation_failure_message(post_validation: dict) -> str:
    runtime = post_validation.get("runtime_validation") or {}
    compile_info = runtime.get("compile") or {}
    startup_info = runtime.get("startup") or {}
    smoke_info = runtime.get("endpoint_smoke") or {}
    compile_status = compile_info.get("status", "unknown")
    startup_status = startup_info.get("status", "unknown")
    smoke_status = smoke_info.get("status", "unknown")
    remaining = int(post_validation.get("remaining_invalid_count", 0) or 0)
    reasons = []
    for item in (post_validation.get("remaining_invalid_files") or [])[:5]:
        reason = (item.get("reason") or "validation failed").strip()
        path = (item.get("path") or "").strip()
        reasons.append(f"{path}: {reason}" if path else reason)
    compile_lines = summarize_compile_errors(compile_info.get("errors") or [], limit=3)
    if compile_lines:
        reasons.extend(compile_lines)
    startup_root_cause = (startup_info.get("root_cause") or "").strip()
    startup_signature = (startup_info.get("failure_signature") or "").strip()
    startup_log = (startup_info.get("startup_log") or "").strip()
    if startup_root_cause:
        reasons.append(f"startup_root_cause={startup_root_cause}")
    if startup_signature:
        reasons.append(f"startup_signature={startup_signature}")
    if startup_log:
        reasons.append(f"startup_log={startup_log}")
    tail = "; ".join(reasons)
    return (
        f"generated project validation failed (remaining_invalid={remaining}, "
        f"compile={compile_status}, startup={startup_status}, endpoint_smoke={smoke_status})"
        + (f": {tail}" if tail else "")
    )


def post_validation_diagnostic_lines(post_validation: dict) -> list[str]:
    lines: list[str] = []
    delta = post_validation.get("invalid_delta") or {}
    added = list(delta.get("added") or [])
    removed = list(delta.get("removed") or [])
    if delta:
        lines.append(
            f"[POST-VALIDATION-DELTA] added={int(delta.get('added_count', 0) or 0)}, removed={int(delta.get('removed_count', 0) or 0)}, grew={'yes' if delta.get('grew') else 'no'}"
        )
        for item in added[:3]:
            reason = (item.get("reason") or "validation failed").strip()
            path = (item.get("path") or "").strip()
            lines.append(f"[POST-VALIDATION-DELTA] added {path}: {reason}" if path else f"[POST-VALIDATION-DELTA] added {reason}")
        for item in removed[:2]:
            reason = (item.get("reason") or "validation failed").strip()
            path = (item.get("path") or "").strip()
            lines.append(f"[POST-VALIDATION-DELTA] removed {path}: {reason}" if path else f"[POST-VALIDATION-DELTA] removed {reason}")

    unresolved = list(post_validation.get("unresolved_initial_invalid") or [])
    if unresolved:
        lines.append(f"[POST-VALIDATION-UNRESOLVED] count={len(unresolved)}")
        for item in unresolved[:3]:
            reason = (item.get("reason") or "validation failed").strip()
            path = (item.get("path") or "").strip()
            lines.append(f"[POST-VALIDATION-UNRESOLVED] {path}: {reason}" if path else f"[POST-VALIDATION-UNRESOLVED] {reason}")

    compile_rounds = list(post_validation.get("compile_repair_rounds") or [])
    for round_info in compile_rounds:
        round_no = int(round_info.get("round", 0) or 0)
        before = round_info.get("before") or {}
        after = round_info.get("after") or {}
        lines.append(
            f"[COMPILE-REPAIR] round={round_no}, targets={len(round_info.get('targets') or [])}, changed={len(round_info.get('changed') or [])}, skipped={len(round_info.get('skipped') or [])}"
        )
        if before or after:
            lines.append(
                f"[COMPILE-RETRY-{round_no}] before compile={before.get('compile_status', 'unknown')}, startup={before.get('startup_status', 'unknown')}, endpoint_smoke={before.get('endpoint_smoke_status', 'unknown')} -> after compile={after.get('compile_status', 'unknown')}, startup={after.get('startup_status', 'unknown')}, endpoint_smoke={after.get('endpoint_smoke_status', 'unknown')}"
            )
        if round_info.get("terminal_failure"):
            lines.append(f"[COMPILE-RETRY-{round_no}] terminal={round_info.get('terminal_failure')}")
        for line in (after.get("compile_errors") or [])[:3]:
            lines.append(f"[COMPILE-RETRY-{round_no}] {line}")
    if not compile_rounds:
        compile_repair = post_validation.get("compile_repair") or {}
        if compile_repair.get("attempted"):
            lines.append(
                f"[COMPILE-REPAIR] targets={len(compile_repair.get('targets') or [])}, changed={len(compile_repair.get('changed') or [])}, skipped={len(compile_repair.get('skipped') or [])}"
            )

    startup_rounds = list(post_validation.get("startup_repair_rounds") or [])
    for round_info in startup_rounds:
        round_no = int(round_info.get("round", 0) or 0)
        before = round_info.get("before") or {}
        after = round_info.get("after") or {}
        lines.append(
            f"[STARTUP-REPAIR] round={round_no}, targets={len(round_info.get('targets') or [])}, changed={len(round_info.get('changed') or [])}, skipped={len(round_info.get('skipped') or [])}"
        )
        if before or after:
            lines.append(
                f"[STARTUP-RETRY-{round_no}] before compile={before.get('compile_status', 'unknown')}, startup={before.get('startup_status', 'unknown')}, endpoint_smoke={before.get('endpoint_smoke_status', 'unknown')} -> after compile={after.get('compile_status', 'unknown')}, startup={after.get('startup_status', 'unknown')}, endpoint_smoke={after.get('endpoint_smoke_status', 'unknown')}"
            )
        if round_info.get("terminal_failure"):
            lines.append(f"[STARTUP-RETRY-{round_no}] terminal={round_info.get('terminal_failure')}")
        for line in (after.get("compile_errors") or [])[:3]:
            lines.append(f"[STARTUP-RETRY-{round_no}] {line}")
        if after.get("startup_root_cause"):
            lines.append(f"[STARTUP-RETRY-{round_no}] root_cause={after.get('startup_root_cause')}")
        if after.get("startup_signature"):
            lines.append(f"[STARTUP-RETRY-{round_no}] signature={after.get('startup_signature')}")
        if after.get("startup_log"):
            lines.append(f"[STARTUP-RETRY-{round_no}] log={after.get('startup_log')}")
        for line in (after.get("endpoint_errors") or [])[:3]:
            lines.append(f"[STARTUP-RETRY-{round_no}] {line}")
    if not startup_rounds:
        startup_repair = post_validation.get("startup_repair") or {}
        if startup_repair.get("attempted"):
            lines.append(
                f"[STARTUP-REPAIR] targets={len(startup_repair.get('targets') or [])}, changed={len(startup_repair.get('changed') or [])}, skipped={len(startup_repair.get('skipped') or [])}"
            )

    smoke_rounds = list(post_validation.get("smoke_repair_rounds") or [])
    for round_info in smoke_rounds:
        round_no = int(round_info.get("round", 0) or 0)
        before = round_info.get("before") or {}
        after = round_info.get("after") or {}
        lines.append(
            f"[SMOKE-REPAIR] round={round_no}, targets={len(round_info.get('targets') or [])}, changed={len(round_info.get('changed') or [])}, skipped={len(round_info.get('skipped') or [])}"
        )
        if before or after:
            lines.append(
                f"[SMOKE-RETRY-{round_no}] before compile={before.get('compile_status', 'unknown')}, startup={before.get('startup_status', 'unknown')}, endpoint_smoke={before.get('endpoint_smoke_status', 'unknown')} -> after compile={after.get('compile_status', 'unknown')}, startup={after.get('startup_status', 'unknown')}, endpoint_smoke={after.get('endpoint_smoke_status', 'unknown')}"
            )
        if round_info.get("terminal_failure"):
            lines.append(f"[SMOKE-RETRY-{round_no}] terminal={round_info.get('terminal_failure')}")
        for line in (after.get("compile_errors") or [])[:3]:
            lines.append(f"[SMOKE-RETRY-{round_no}] {line}")
        for line in (after.get("endpoint_errors") or [])[:3]:
            lines.append(f"[SMOKE-RETRY-{round_no}] {line}")
    if not smoke_rounds:
        smoke_repair = post_validation.get("smoke_repair") or {}
        if smoke_repair.get("attempted"):
            lines.append(
                f"[SMOKE-REPAIR] targets={len(smoke_repair.get('targets') or [])}, changed={len(smoke_repair.get('changed') or [])}, skipped={len(smoke_repair.get('skipped') or [])}"
            )
    return _append_startup_summary_lines(lines, post_validation)



def _append_startup_summary_lines(lines: list[str], post_validation: dict) -> list[str]:
    startup_info = (post_validation.get("runtime_validation") or {}).get("startup") or {}
    if startup_info.get("root_cause"):
        lines.append(f"[STARTUP] root_cause={startup_info.get('root_cause')}")
    if startup_info.get("failure_signature"):
        lines.append(f"[STARTUP] signature={startup_info.get('failure_signature')}")
    if startup_info.get("startup_log"):
        lines.append(f"[STARTUP] log={startup_info.get('startup_log')}")
    return lines
