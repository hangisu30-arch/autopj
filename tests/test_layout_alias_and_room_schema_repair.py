from pathlib import Path

from app.validation.post_generation_repair import _ensure_jsp_include_alias, _validate_jsp_include_consistency
from app.validation.project_auto_repair import _sync_schema_table_from_mapper, _ensure_schema_column_comments


def test_common_include_and_navi_aliases(tmp_path: Path):
    base = tmp_path / 'src/main/webapp/WEB-INF/views/common'
    base.mkdir(parents=True, exist_ok=True)
    (base / 'leftNav.jsp').write_text('<div>nav</div>\n', encoding='utf-8')
    layout = base / 'layout.jsp'
    layout.write_text(
        '<%@ include file="/WEB-INF/views/common/include.jsp" %>\n'
        '<%@ include file="/WEB-INF/views/common/navi.jsp" %>\n',
        encoding='utf-8',
    )
    assert _ensure_jsp_include_alias(tmp_path) is True
    issues = _validate_jsp_include_consistency(tmp_path, ['src/main/webapp/WEB-INF/views/common/layout.jsp'])
    assert not [i for i in issues if 'includes missing' in i.get('reason', '')]


def test_room_schema_mapper_sync_and_comments(tmp_path: Path):
    mapper = tmp_path / 'src/main/resources/egovframework/mapper/room/RoomMapper.xml'
    mapper.parent.mkdir(parents=True, exist_ok=True)
    mapper.write_text(
        '<mapper namespace="room">\n'
        '<select id="list" resultType="RoomVO">\n'
        'SELECT room_id, title, start_datetime, end_datetime, status_cd FROM room\n'
        '</select>\n'
        '</mapper>',
        encoding='utf-8',
    )
    schema = tmp_path / 'src/main/resources/schema.sql'
    schema.parent.mkdir(parents=True, exist_ok=True)
    schema.write_text(
        "CREATE TABLE room (\n"
        "    room_id VARCHAR(255)\n"
        ");\n"
        "COMMENT ON COLUMN room.title IS 'old';\n",
        encoding='utf-8',
    )
    issue = {'details': {'table': 'room', 'mapper_columns': ['room_id', 'title', 'start_datetime', 'end_datetime', 'status_cd']}}
    assert _sync_schema_table_from_mapper(mapper, issue, tmp_path) is True
    _ensure_schema_column_comments(
        mapper,
        {'details': {'table': 'room', 'missing_comments': ['title', 'start_datetime', 'end_datetime', 'status_cd']}},
        tmp_path,
    )
    text = schema.read_text(encoding='utf-8').lower()
    assert 'create table if not exists room' in text
    for col in ['title', 'start_datetime', 'end_datetime', 'status_cd']:
        assert col in text
    assert "comment '제목'" in text
    assert "comment '시작일시'" in text
    assert "comment '종료일시'" in text
    assert "comment '상태코드'" in text
    assert 'comment on column room.' not in text
