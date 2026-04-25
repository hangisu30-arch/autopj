from pathlib import Path

from execution_core.builtin_crud import infer_schema_from_file_ops
from app.io.execution_core_apply import _normalize_schema_tables
from app.validation.generated_project_validator import validate_generated_project


def test_infer_schema_prefers_entity_default_table_when_multiple_create_tables_exist():
    file_ops = [
        {
            "path": "java/service/vo/ReservationVO.java",
            "content": """
                CREATE TABLE IF NOT EXISTS room (room_id BIGINT PRIMARY KEY AUTO_INCREMENT, room_name VARCHAR(255));
                CREATE TABLE IF NOT EXISTS reservation (reservation_id BIGINT PRIMARY KEY AUTO_INCREMENT, room_id BIGINT, title VARCHAR(255));
            """,
        }
    ]
    schema = infer_schema_from_file_ops(file_ops, entity="Reservation")
    assert schema.table == "reservation"


def test_normalize_schema_tables_breaks_duplicate_table_name_collisions():
    room_schema = type("Schema", (), {"entity": "Room", "table": "room"})()
    reservation_schema = type("Schema", (), {"entity": "Reservation", "table": "room"})()
    normalized = _normalize_schema_tables({"Room": room_schema, "Reservation": reservation_schema})
    assert normalized["Room"].table == "room"
    assert normalized["Reservation"].table == "reservation"


def test_validator_reports_duplicate_table_definitions_in_schema_sql(tmp_path: Path):
    root = tmp_path
    schema = root / "src/main/resources/schema.sql"
    schema.parent.mkdir(parents=True, exist_ok=True)
    schema.write_text(
        """
        CREATE TABLE IF NOT EXISTS room (room_id BIGINT);
        CREATE TABLE IF NOT EXISTS room (reservation_id BIGINT);
        """,
        encoding="utf-8",
    )

    cfg = type("Cfg", (), {"frontend_key": "jsp"})()
    report = validate_generated_project(root, cfg=cfg, manifest=None, include_runtime=False)
    issue_types = {item["type"] for item in report["static_issues"]}
    assert "duplicate_table_definition" in issue_types
