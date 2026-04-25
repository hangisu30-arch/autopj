from pathlib import Path

from execution_core.builtin_crud import extract_explicit_requirement_schemas
from app.io.execution_core_apply import _write_schema_sql_from_schemas, apply_file_ops_with_execution_core
from app.ui.state import ProjectConfig

REQ = """
[테이블 정의 1: room]
- 테이블명: room
- 최소 컬럼은 아래를 사용한다
  - room_id
  - room_name
  - use_yn

[테이블 정의 2: reservation]
- 테이블명: reservation
- 최소 컬럼은 아래를 사용한다
  - reservation_id
  - room_id
  - reservation_title
  - start_datetime
  - end_datetime
"""


def test_extract_explicit_requirement_schemas_keeps_room_and_reservation_blocks():
    schema_map = extract_explicit_requirement_schemas(REQ)
    assert set(schema_map.keys()) == {"Room", "Reservation"}
    assert schema_map["Room"].table == "room"
    assert schema_map["Reservation"].table == "reservation"
    assert [col for _prop, col, _jt in schema_map["Room"].fields] == ["room_id", "room_name", "use_yn"]
    assert [col for _prop, col, _jt in schema_map["Reservation"].fields][:3] == ["reservation_id", "room_id", "reservation_title"]


def test_write_schema_sql_orders_room_before_reservation(tmp_path: Path):
    schema_map = extract_explicit_requirement_schemas(REQ)
    path = _write_schema_sql_from_schemas(tmp_path, schema_map)
    body = path.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS room" in body
    assert "CREATE TABLE IF NOT EXISTS reservation" in body
    assert body.index("CREATE TABLE IF NOT EXISTS room") < body.index("CREATE TABLE IF NOT EXISTS reservation")


def test_apply_file_ops_reports_missing_explicit_tables_when_schema_sql_drops_room(tmp_path: Path, monkeypatch):
    def _bad_schema_writer(project_root, schema_map):
        path = project_root / "src/main/resources/schema.sql"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("CREATE TABLE IF NOT EXISTS reservation (reservation_id VARCHAR(50) PRIMARY KEY);", encoding="utf-8")
        return path

    monkeypatch.setattr("app.io.execution_core_apply._write_schema_sql_from_schemas", _bad_schema_writer)

    cfg = ProjectConfig(project_name="demo", frontend_key="jsp", extra_requirements=REQ)
    report = apply_file_ops_with_execution_core([], tmp_path, cfg, overwrite=True)

    reasons = [str(item.get("reason") or "") for item in report.get("errors", [])]
    assert any("missing_explicit_tables=room" in reason for reason in reasons)
