from pathlib import Path

from app.validation.project_auto_repair import _sync_schema_table_from_mapper


def test_sync_uses_primary_schema_as_authority_and_updates_db_variant(tmp_path: Path):
    project = tmp_path
    mapper = project / "src/main/resources/egovframework/mapper/reservation/ReservationMapper.xml"
    mapper.parent.mkdir(parents=True, exist_ok=True)
    mapper.write_text(
        """
<mapper namespace="x">
  <insert id="insert">
    INSERT INTO reservation (reservation_id, room_id, status_cd)
    VALUES (#{reservationId}, #{roomId}, #{statusCd})
  </insert>
</mapper>
""",
        encoding="utf-8",
    )

    primary = project / "src/main/resources/schema.sql"
    primary.parent.mkdir(parents=True, exist_ok=True)
    primary.write_text(
        """
CREATE TABLE reservation (
    reservation_id VARCHAR(255) COMMENT 'id'
);
""",
        encoding="utf-8",
    )

    db_schema = project / "src/main/resources/db/schema.sql"
    db_schema.parent.mkdir(parents=True, exist_ok=True)
    db_schema.write_text(
        """
CREATE TABLE reservation (
    legacy_only VARCHAR(255) COMMENT 'legacy'
);
""",
        encoding="utf-8",
    )

    changed = _sync_schema_table_from_mapper(
        mapper,
        {"details": {"table": "reservation", "mapper_columns": ["reservation_id", "room_id", "status_cd"], "schema_path": "src/main/resources/db/schema.sql"}},
        project,
    )

    assert changed is True
    primary_text = primary.read_text(encoding="utf-8")
    db_text = db_schema.read_text(encoding="utf-8")
    assert "reservation_id" in primary_text
    assert "room_id" in primary_text
    assert "status_cd" in primary_text
    assert "legacy_only" not in primary_text
    assert db_text == primary_text
