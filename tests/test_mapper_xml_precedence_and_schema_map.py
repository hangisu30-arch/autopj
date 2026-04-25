from execution_core.builtin_crud import infer_schema_from_file_ops, ddl
from app.io.execution_core_apply import _schema_map_from_file_ops

REQ = """DB 규칙:
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

MAPPER_XML = """<!DOCTYPE mapper
  PUBLIC '-//mybatis.org//DTD Mapper 3.0//EN'
  'http://mybatis.org/dtd/mybatis-3-mapper.dtd'>
<mapper namespace='egovframework.test.schedule.service.mapper.ScheduleMapper'>
  <resultMap id='ScheduleMap' type='egovframework.test.schedule.service.vo.ScheduleVO'>
    <id property='scheduleId' column='schedule_id'/>
    <result property='title' column='title'/>
    <result property='content' column='content'/>
    <result property='startDatetime' column='start_datetime'/>
    <result property='endDatetime' column='end_datetime'/>
    <result property='allDayYn' column='all_day_yn'/>
    <result property='statusCd' column='status_cd'/>
    <result property='priorityCd' column='priority_cd'/>
    <result property='location' column='location'/>
    <result property='writerId' column='writer_id'/>
    <result property='useYn' column='use_yn'/>
    <result property='regDt' column='reg_dt'/>
    <result property='updDt' column='upd_dt'/>
  </resultMap>
  <select id='selectScheduleList' parameterType='map' resultMap='ScheduleMap'>
    SELECT schedule_id, title, content,
           DATE_FORMAT(start_datetime, '%Y-%m-%d %H:%i:%s') AS start_datetime,
           DATE_FORMAT(end_datetime, '%Y-%m-%d %H:%i:%s') AS end_datetime,
           all_day_yn, status_cd, priority_cd, location, writer_id, use_yn,
           DATE_FORMAT(reg_dt, '%Y-%m-%d %H:%i:%s') AS reg_dt,
           DATE_FORMAT(upd_dt, '%Y-%m-%d %H:%i:%s') AS upd_dt
      FROM schedule
  </select>
</mapper>
"""


def _ops_with_wrong_analysis():
    return [
        {
            'path': 'requirements.txt',
            'content': REQ,
        },
        {
            'path': 'analysis.json',
            'domains': [
                {
                    'name': 'schedule',
                    'source_table': 'id',
                    'fields': [
                        {'name': 'id', 'column': 'id', 'java_type': 'String'},
                        {'name': 'name', 'column': 'name', 'java_type': 'String'},
                    ],
                }
            ],
        },
        {
            'path': 'src/main/resources/schema.sql',
            'content': 'CREATE TABLE IF NOT EXISTS id (id VARCHAR(64) PRIMARY KEY, name VARCHAR(255));',
        },
        {
            'path': 'src/main/resources/egovframework/mapper/schedule/ScheduleMapper.xml',
            'content': MAPPER_XML,
        },
        {
            'path': 'src/main/webapp/WEB-INF/views/item/itemCalendar.jsp',
            'content': '<a href="<c:url value="/item/edit.do"/>">등록</a>',
        },
    ]


def test_mapper_xml_precedes_wrong_analysis_for_schema_contract():
    schema = infer_schema_from_file_ops(_ops_with_wrong_analysis(), entity='Item')
    assert schema.authority == 'explicit'
    assert schema.entity == 'Schedule'
    assert schema.table == 'schedule'
    assert schema.id_column == 'schedule_id'
    cols = [col for _prop, col, _jt in schema.fields]
    assert cols == [
        'schedule_id', 'title', 'content', 'start_datetime', 'end_datetime',
        'all_day_yn', 'status_cd', 'priority_cd', 'location', 'writer_id',
        'use_yn', 'reg_dt', 'upd_dt'
    ]
    sql = ddl(schema)
    assert 'CREATE TABLE IF NOT EXISTS schedule' in sql
    assert 'CREATE TABLE IF NOT EXISTS id' not in sql
    assert 'schedule_id VARCHAR(64) NOT NULL PRIMARY KEY' in sql


def test_schema_map_keeps_explicit_or_mapper_contract_without_business_template_override():
    schema_map = _schema_map_from_file_ops(_ops_with_wrong_analysis())
    schedule_schema = schema_map['Schedule']
    assert schedule_schema.table == 'schedule'
    assert schedule_schema.id_column == 'schedule_id'
    assert schedule_schema.authority in {'explicit', 'mapper'}
    cols = [col for _prop, col, _jt in schedule_schema.fields]
    assert cols[:5] == ['schedule_id', 'title', 'content', 'start_datetime', 'end_datetime']
    assert 'id' not in cols
