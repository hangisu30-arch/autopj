import argparse
import json
import re
from pathlib import Path

from .config_loader import load_config
from .context import ExecutionContext
from .generator import generate_files
from .profiles import get_profile
from .plan_validator import validate_plan
from .logger import log
from .project_patcher import detect_boot_base_package, patch_application_properties, patch_boot_application, patch_datasource_properties, patch_pom_mysql_driver, patch_pom_jsp_support, write_schema_sql_from_db_ops, write_database_initializer, ensure_maven_wrapper


def run_engine(
    plan: dict,
    project_root: str,
    config_path: str,
    overwrite=False,
    db_apply=False,
    dry_run=False,
):
    log("ENGINE START")

    log("Loading config...")
    config = load_config(config_path)

    backend = plan.get("backend", "egov_spring")
    frontend = plan.get("frontend", "jsp")

    pr = Path(project_root)

    # Base package: prefer explicit plan value, otherwise use existing boot package.
    # If the existing package still uses the sample placeholder 'example',
    # replace that segment with the project root name.
    boot_pkg = detect_boot_base_package(pr)
    project_seg = re.sub(r"[^a-zA-Z0-9_]+", "", pr.name or "") or "app"
    project_seg = (project_seg[0].lower() + project_seg[1:]) if project_seg else "app"
    base_package = (plan.get("base_package") or "").strip()
    if not base_package.startswith("egovframework."):
        base_package = f"egovframework.{project_seg}"

    plan["base_package"] = base_package

    log(f"Backend={backend}, Frontend={frontend}")
    log(f"base_package={base_package}")
    log(f"Dry-run={dry_run}, Overwrite={overwrite}, DB-Apply={db_apply}")

    context = ExecutionContext(
        project_root=project_root,
        backend=backend,
        frontend=frontend,
        base_package=base_package,
        config=config,
        overwrite=overwrite,
        db_apply=db_apply,
        dry_run=dry_run,
    )

    profile = get_profile(context)

    log("Validating plan...")
    validate_plan(plan)

    log("Generating files...")
    result = generate_files(plan, profile)

    # Patch Spring Boot config to ensure JSP & MyBatis work at runtime
    if not dry_run:
        boot_path = patch_boot_application(pr, base_package)
        log(f"Patched boot application: {boot_path}")

        patched = patch_application_properties(pr, base_package, frontend)
        log(f"Patched application.properties: {patched}")

        try:
            wrapper_paths = ensure_maven_wrapper(pr)
            log(f"Patched Maven wrapper: {[str(p) for p in wrapper_paths]}")
        except Exception as e:
            log(f"maven wrapper write skipped: {e}")

        try:
            init_path = write_database_initializer(pr, base_package)
            log(f"Patched database initializer: {init_path}")
        except Exception as e:
            log(f"database initializer write skipped: {e}")

        # MySQL-only: ensure mysql JDBC driver exists in pom.xml
        try:
            changed = patch_pom_mysql_driver(pr)
            if frontend == "jsp":
                try:
                    jsp_changed = patch_pom_jsp_support(pr)
                    if jsp_changed:
                        log("Patched pom.xml: added JSP dependencies (jasper+jstl)")
                except Exception:
                    pass
            if changed:
                log("Patched pom.xml: added mysql-connector-j (runtime)")
        except Exception:
            pass

        # MySQL-only: write spring.datasource.* from execution_core config
        try:
            db_conf = config.get("database") or config.get("db") or {}
            patch_datasource_properties(pr, db_conf)
        except Exception:
            pass
        # Write schema.sql from plan db_ops so Spring Boot creates tables on startup
        try:
            schema_path = write_schema_sql_from_db_ops(pr, plan.get("db_ops") or [])
            log(f"Wrote schema.sql: {schema_path}")
        except Exception as e:
            log(f"schema.sql write skipped: {e}")

    if db_apply and not dry_run:
        log("Applying DB operations...")
        from .db_executor import apply_db_ops
        apply_db_ops(plan.get("db_ops", []), config)

    log("ENGINE COMPLETE")
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--db-apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with open(args.plan, "r", encoding="utf-8") as f:
        plan = json.load(f)

    result = run_engine(
        plan=plan,
        project_root=args.project_root,
        config_path=args.config,
        overwrite=args.overwrite,
        db_apply=args.db_apply,
        dry_run=args.dry_run,
    )

    print("\n=== RESULT ===")
    print(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
