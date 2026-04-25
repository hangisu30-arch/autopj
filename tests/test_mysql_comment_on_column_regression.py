from pathlib import Path

from app.validation.project_auto_repair import _sync_schema_table_from_mapper, _ensure_schema_column_comments


def test_schema_repair_never_emits_comment_on_column_for_mysql_schema(tmp_path: Path):
    mapper = tmp_path / "src/main/resources/egovframework/mapper/room/RoomMapper.xml"
    mapper.parent.mkdir(parents=True, exist_ok=True)
    mapper.write_text(
        '<mapper namespace="room">\n'
        '  <select id="list" resultType="RoomVO">SELECT reservation_id, room_id FROM room</select>\n'
        '</mapper>\n',
        encoding="utf-8",
    )
    schema = tmp_path / "src/main/resources/schema.sql"
    schema.parent.mkdir(parents=True, exist_ok=True)
    schema.write_text(
        "CREATE TABLE room (\n"
        "    room_id VARCHAR(255)\n"
        ");\n\n"
        "COMMENT ON COLUMN room.reservation_id IS 'old';\n",
        encoding="utf-8",
    )
    issue = {"details": {"table": "room", "mapper_columns": ["reservation_id", "room_id"]}}
    assert _sync_schema_table_from_mapper(mapper, issue, tmp_path) is True
    _ensure_schema_column_comments(mapper, {"details": {"table": "room", "missing_comments": ["reservation_id"]}}, tmp_path)
    text = schema.read_text(encoding="utf-8")
    assert "COMMENT ON COLUMN" not in text
    assert "reservation_id VARCHAR(255) COMMENT 'reservation_id 컬럼'" in text
