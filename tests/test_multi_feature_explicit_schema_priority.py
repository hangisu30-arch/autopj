from execution_core.builtin_crud import infer_schema_from_file_ops
from app.io.execution_core_apply import _schema_map_from_file_ops, _repair_content_by_path

COMBINED_REQ = """
로그인 기능을 추가해줘.
DB 규칙:
- 테이블명은 login_user 로 사용한다
- 최소 컬럼은 아래를 사용한다
  - user_id
  - login_id
  - password
  - user_nm
  - use_yn

일정관리 기능도 추가해줘.
DB 규칙:
- 테이블명은 schedule 로 사용한다
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
"""

WRONG_SCHEDULE_MAPPER = """<!DOCTYPE mapper
  PUBLIC '-//mybatis.org//DTD Mapper 3.0//EN'
  'http://mybatis.org/dtd/mybatis-3-mapper.dtd'>
<mapper namespace='egovframework.test.schedule.service.mapper.ScheduleMapper'>
  <resultMap id='ScheduleMap' type='egovframework.test.schedule.service.vo.ScheduleVO'>
    <id property='scheduleId' column='schedule_id'/>
    <result property='year' column='year'/>
    <result property='month' column='month'/>
    <result property='action' column='action'/>
    <result property='scheduleName' column='schedule_name'/>
    <result property='scheduleNo' column='schedule_no'/>
    <result property='title' column='title'/>
    <result property='content' column='content'/>
  </resultMap>
  <select id='selectScheduleList' parameterType='map' resultMap='ScheduleMap'>
    SELECT year, month, action, schedule_id, schedule_name, writer_id, schedule_no, title, content,
           DATE_FORMAT(start_datetime, '%Y-%m-%d %H:%i:%s') AS start_datetime,
           DATE_FORMAT(end_datetime, '%Y-%m-%d %H:%i:%s') AS end_datetime,
           all_day_yn, status_cd, priority_cd, location, use_yn,
           DATE_FORMAT(reg_dt, '%Y-%m-%d %H:%i:%s') AS reg_dt,
           DATE_FORMAT(upd_dt, '%Y-%m-%d %H:%i:%s') AS upd_dt
      FROM schedule
  </select>
</mapper>
"""


def test_infer_schema_uses_targeted_explicit_contract_when_multiple_modules_exist():
    ops = [
        {'path': 'requirements.txt', 'content': COMBINED_REQ},
        {'path': 'src/main/java/egovframework/test/schedule/web/ScheduleController.java', 'content': 'class ScheduleController {}'},
    ]
    schema = infer_schema_from_file_ops(ops, entity='Schedule')
    assert schema.authority == 'explicit'
    assert schema.table == 'schedule'
    assert [col for _prop, col, _jt in schema.fields] == [
        'schedule_id', 'title', 'content', 'start_datetime', 'end_datetime',
        'all_day_yn', 'status_cd', 'priority_cd', 'location', 'writer_id',
        'use_yn', 'reg_dt', 'upd_dt'
    ]


def test_apply_schema_map_uses_extra_requirements_to_rebuild_wrong_schedule_mapper():
    file_ops = [
        {'path': 'src/main/java/egovframework/test/login/web/LoginController.java', 'purpose': 'login controller', 'content': 'public class LoginController {}'},
        {'path': 'src/main/java/egovframework/test/schedule/web/ScheduleController.java', 'purpose': 'schedule calendar controller', 'content': 'public class ScheduleController {}'},
        {'path': 'src/main/resources/egovframework/mapper/schedule/ScheduleMapper.xml', 'purpose': 'schedule mapper', 'content': WRONG_SCHEDULE_MAPPER},
    ]
    schema_map = _schema_map_from_file_ops(file_ops, extra_requirements=COMBINED_REQ)
    schedule_schema = schema_map['Schedule']
    assert schedule_schema.authority == 'explicit'
    assert schedule_schema.table == 'schedule'
    cols = [col for _prop, col, _jt in schedule_schema.fields]
    assert cols == [
        'schedule_id', 'title', 'content', 'start_datetime', 'end_datetime',
        'all_day_yn', 'status_cd', 'priority_cd', 'location', 'writer_id',
        'use_yn', 'reg_dt', 'upd_dt'
    ]

    rebuilt = _repair_content_by_path(
        'src/main/resources/egovframework/mapper/schedule/ScheduleMapper.xml',
        WRONG_SCHEDULE_MAPPER,
        'egovframework.test',
        preferred_entity='Schedule',
        schema_map=schema_map,
    )
    assert 'year,' not in rebuilt
    assert 'month,' not in rebuilt
    assert 'action,' not in rebuilt
    assert 'schedule_name' not in rebuilt
    assert 'schedule_no' not in rebuilt
    assert 'schedule_id, title, content' in rebuilt.replace('\n', ' ')
    assert 'start_datetime' in rebuilt
    assert 'priority_cd' in rebuilt


def test_apply_schema_map_keeps_explicit_non_login_schema_even_without_generated_ops():
    file_ops = [
        {'path': 'src/main/java/egovframework/test/login/web/LoginController.java', 'purpose': 'login controller', 'content': 'public class LoginController {}'},
    ]
    schema_map = _schema_map_from_file_ops(file_ops, extra_requirements=COMBINED_REQ)
    assert 'Login' in schema_map
    assert 'Schedule' in schema_map
    schedule_schema = schema_map['Schedule']
    assert schedule_schema.authority == 'explicit'
    assert schedule_schema.table == 'schedule'
    assert [col for _prop, col, _jt in schedule_schema.fields] == [
        'schedule_id', 'title', 'content', 'start_datetime', 'end_datetime',
        'all_day_yn', 'status_cd', 'priority_cd', 'location', 'writer_id',
        'use_yn', 'reg_dt', 'upd_dt'
    ]
