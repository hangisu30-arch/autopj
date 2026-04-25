from execution_core.builtin_crud import infer_schema_from_file_ops, ddl, builtin_file, canonicalize_db_ops


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
  <select id='selectSchedule' parameterType='string' resultMap='ScheduleMap'>
    SELECT schedule_id, title, content, start_datetime, end_datetime, all_day_yn, status_cd, priority_cd, location, writer_id, use_yn, reg_dt, upd_dt
      FROM schedule
     WHERE schedule_id = #{scheduleId}
  </select>
  <insert id='insertSchedule' parameterType='egovframework.test.schedule.service.vo.ScheduleVO'>
    INSERT INTO schedule (schedule_id, title, content, start_datetime, end_datetime, all_day_yn, status_cd, priority_cd, location, writer_id, use_yn, reg_dt, upd_dt)
    VALUES (#{scheduleId}, #{title}, #{content}, STR_TO_DATE(REPLACE(#{startDatetime}, 'T', ' '), '%Y-%m-%d %H:%i:%s'), STR_TO_DATE(REPLACE(#{endDatetime}, 'T', ' '), '%Y-%m-%d %H:%i:%s'), #{allDayYn}, #{statusCd}, #{priorityCd}, #{location}, #{writerId}, #{useYn}, STR_TO_DATE(REPLACE(#{regDt}, 'T', ' '), '%Y-%m-%d %H:%i:%s'), STR_TO_DATE(REPLACE(#{updDt}, 'T', ' '), '%Y-%m-%d %H:%i:%s'))
  </insert>
</mapper>
"""


def _file_ops():
    return [
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


def test_mapper_xml_becomes_authoritative_for_schema_when_schema_sql_is_wrong():
    schema = infer_schema_from_file_ops(_file_ops(), entity='Item')
    assert schema.entity == 'Schedule'
    assert schema.table == 'schedule'
    assert schema.id_prop == 'scheduleId'
    assert schema.id_column == 'schedule_id'
    field_map = {prop: col for prop, col, _ in schema.fields}
    assert 'id' not in field_map
    assert field_map['scheduleId'] == 'schedule_id'
    assert field_map['title'] == 'title'
    assert field_map['startDatetime'] == 'start_datetime'


def test_mapper_xml_authority_rewrites_db_ops_to_schedule_contract():
    schema = infer_schema_from_file_ops(_file_ops(), entity='Item')
    ops = canonicalize_db_ops([{'sql': 'CREATE TABLE IF NOT EXISTS id (id VARCHAR(64) PRIMARY KEY);'}], schema)
    sql = ops[0]['sql']
    assert 'CREATE TABLE IF NOT EXISTS schedule' in sql
    assert 'schedule_id VARCHAR(64) NOT NULL PRIMARY KEY' in sql
    assert 'start_datetime DATETIME' in sql
    assert 'CREATE TABLE IF NOT EXISTS id' not in sql


def test_mapper_xml_authority_keeps_schedule_ui_routes_not_item_routes():
    schema = infer_schema_from_file_ops(_file_ops(), entity='Item')
    jsp = builtin_file('jsp/schedule/ScheduleCalendar.jsp', 'egovframework.test', schema)
    assert 'Schedule 달력' in jsp
    assert jsp.count('/schedule/edit.do') >= 2
    assert '/item/edit.do' not in jsp


def test_mapper_xml_authority_prefers_schedule_id_over_leaked_generic_id():
    schema = infer_schema_from_file_ops([
        {
            'path': 'src/main/resources/egovframework/mapper/schedule/ScheduleMapper.xml',
            'content': MAPPER_XML + '\n<!-- leaked generic select id -->\n<select id="selectId">SELECT id FROM schedule</select>',
        }
    ], entity='Item')
    assert schema.id_column == 'schedule_id'
    sql = ddl(schema)
    assert 'schedule_id VARCHAR(64) NOT NULL PRIMARY KEY' in sql
    assert ' id VARCHAR(64) NOT NULL PRIMARY KEY' not in sql
