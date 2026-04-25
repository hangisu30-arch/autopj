from app.io.execution_core_apply import _schema_map_from_file_ops
from app.ui.state import ProjectConfig
from app.validation.post_generation_repair import _build_manifest

REQ = '''DB 규칙:
- 테이블명은 schedule 로 사용한다
- 일정 테이블이 없으면 신규 생성한다
- 최소 컬럼은 아래를 사용한다
  - schedule_id
  - title
  - content
  - start_datetime
  - end_datetime
  - all_day_yn
  - status_cd
  - priority_cd
  - location
  - writer_id
  - use_yn
  - reg_dt
  - upd_dt
'''


def test_schema_map_from_file_ops_prefers_extra_requirements_contract_for_schema_sql():
    file_ops = [
        {
            'path': 'src/main/java/egovframework/demo/schedule/service/vo/ScheduleVO.java',
            'content': '''package egovframework.demo.schedule.service.vo;

public class ScheduleVO {
    private String scheduleId;
    private String title;
    private String startDate;
    private String endDate;
    private String status;
    private String importance;
}
''',
        },
        {
            'path': 'src/main/resources/egovframework/mapper/schedule/ScheduleMapper.xml',
            'content': '''<mapper namespace="egovframework.demo.schedule.service.mapper.ScheduleMapper">
<select id="selectScheduleList" resultType="egovframework.demo.schedule.service.vo.ScheduleVO">
SELECT schedule_id, title, start_date, end_date, status, importance
FROM schedule
</select>
</mapper>
''',
        },
    ]

    schema_map = _schema_map_from_file_ops(file_ops, REQ)
    schedule = schema_map['Schedule']
    assert schedule.authority == 'explicit'
    assert schedule.table == 'schedule'
    assert [col for _prop, col, _jt in schedule.fields] == [
        'schedule_id', 'title', 'content', 'start_datetime', 'end_datetime', 'all_day_yn',
        'status_cd', 'priority_cd', 'location', 'writer_id', 'use_yn', 'reg_dt', 'upd_dt'
    ]


def test_generation_manifest_embeds_extra_requirements_into_file_specs(tmp_path):
    cfg = ProjectConfig(project_name='demo', frontend_key='jsp', extra_requirements=REQ)
    file_ops = [
        {
            'path': 'src/main/java/egovframework/demo/schedule/service/vo/ScheduleVO.java',
            'content': 'public class ScheduleVO { private String startDate; }',
            'purpose': 'generated',
        }
    ]

    manifest = _build_manifest(file_ops, tmp_path, cfg, use_execution_core=False)
    spec = manifest['src/main/java/egovframework/demo/schedule/service/vo/ScheduleVO.java']['spec']
    assert '테이블명은 schedule 로 사용한다' in spec
    assert 'private String startDate;' in spec
