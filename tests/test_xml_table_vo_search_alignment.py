from pathlib import Path

from app.engine.analysis.analysis_result import DomainAnalysis, FieldInfo
from app.engine.analysis.ir_builder import IRBuilder
from app.validation.generated_project_validator import validate_generated_project


class _Cfg:
    frontend_key = 'jsp'


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')


def test_ir_builder_marks_all_columns_searchable_when_search_exists():
    builder = IRBuilder()
    domain = DomainAnalysis(
        name='Room',
        entity_name='Room',
        feature_kind='crud',
        source_table='room',
        primary_key='roomId',
        primary_key_column='room_id',
        feature_types=['crud'],
        fields=[
            FieldInfo(name='roomId', column='room_id', java_type='String', db_type='varchar(50)', pk=True),
            FieldInfo(name='roomName', column='room_name', java_type='String', db_type='varchar(200)'),
            FieldInfo(name='useYn', column='use_yn', java_type='String', db_type='varchar(1)'),
            FieldInfo(name='regDt', column='reg_dt', java_type='String', db_type='datetime'),
        ],
    )
    updated = builder.apply(domain, frontend_mode='jsp')
    assert updated.contracts['search']['enabled'] is True
    assert updated.contracts['search']['fields'] == ['roomId', 'roomName', 'useYn', 'regDt']


def test_validator_detects_mapper_table_vo_mismatch_and_incomplete_search(tmp_path: Path):
    project = tmp_path
    _write(project / 'src/main/resources/schema.sql', """
DROP TABLE IF EXISTS room;
CREATE TABLE IF NOT EXISTS room (
  room_id varchar(50) PRIMARY KEY COMMENT '회의실ID',
  room_name varchar(200) COMMENT '회의실명',
  use_yn varchar(1) COMMENT '사용여부'
);
""".strip())
    _write(project / 'src/main/resources/egovframework/mapper/room/RoomMapper.xml', """
<mapper namespace="egovframework.test.room.service.mapper.RoomMapper">
  <resultMap id="roomMap" type="egovframework.test.room.service.vo.RoomVO">
    <id property="roomId" column="room_id"/>
    <result property="roomName" column="room_name"/>
    <result property="useYn" column="use_yn"/>
  </resultMap>
  <select id="selectRoomList" resultMap="roomMap">
    SELECT room_id, room_name, use_yn FROM room
  </select>
</mapper>
""".strip())
    _write(project / 'src/main/java/egovframework/test/room/service/vo/RoomVO.java', """
package egovframework.test.room.service.vo;
public class RoomVO {
    private String roomId;
    private String roomName;
    private String useYn;
    private String extraField;
}
""".strip())
    _write(project / 'src/main/webapp/WEB-INF/views/room/roomList.jsp', """
<form id="searchForm">
  <input type="text" name="roomId" />
  <input type="text" name="roomName" />
  <button type="submit">검색</button>
</form>
""".strip())

    report = validate_generated_project(project, _Cfg(), include_runtime=False)
    kinds = {issue.get('type') for issue in report.get('static_issues') or []}
    assert 'mapper_vo_column_mismatch' in kinds
    assert 'search_fields_incomplete' in kinds
