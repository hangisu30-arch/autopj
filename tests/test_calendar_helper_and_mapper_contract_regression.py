from pathlib import Path

from app.validation.generated_project_validator import _parse_mapper_contract, _scan_jsp_vo_property_mismatch
from app.validation.project_auto_repair import _sanitize_ui_metadata_and_sensitive_refs


def test_parse_mapper_contract_merges_resultmap_columns(tmp_path: Path):
    mapper = tmp_path / 'MemberScheduleMapper.xml'
    mapper.write_text(
        '''<mapper namespace="egovframework.test.memberSchedule.service.impl.MemberScheduleMapper">
<select id="selectMemberScheduleList" resultMap="memberScheduleResult">
  SELECT schedule_id, member_no FROM member_schedule
</select>
<resultMap id="memberScheduleResult" type="egovframework.test.memberSchedule.service.vo.MemberScheduleVO">
  <id property="scheduleId" column="schedule_id"/>
  <result property="startDatetime" column="start_datetime"/>
  <result property="endDatetime" column="end_datetime"/>
  <result property="allDayYn" column="all_day_yn"/>
  <result property="statusCd" column="status_cd"/>
  <result property="priorityCd" column="priority_cd"/>
  <result property="locationText" column="location_text"/>
</resultMap>
</mapper>''',
        encoding='utf-8',
    )
    contract = _parse_mapper_contract(mapper)
    assert contract['table'] == 'member_schedule'
    for col in ['start_datetime', 'end_datetime', 'all_day_yn', 'status_cd', 'priority_cd', 'location_text']:
        assert col in contract['columns']


def test_calendar_helper_fields_are_not_treated_as_vo_mismatch(tmp_path: Path):
    root = tmp_path
    jsp = root / 'src/main/webapp/WEB-INF/views/memberSchedule/memberScheduleCalendar.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text(
        '''<c:forEach var="cell" items="${calendarCells}">
<c:out value="${cell.date}"/>
<c:out value="${cell.day}"/>
<c:out value="${cell.eventCount}"/>
</c:forEach>
<c:forEach var="row" items="${selectedDateSchedules}">
<c:out value="${row.startDatetime}"/>
</c:forEach>''',
        encoding='utf-8',
    )
    vo = root / 'src/main/java/egovframework/test/memberSchedule/service/vo/MemberScheduleVO.java'
    vo.parent.mkdir(parents=True, exist_ok=True)
    vo.write_text(
        '''package egovframework.test.memberSchedule.service.vo;
public class MemberScheduleVO {
    private String startDatetime;
    public String getStartDatetime() { return startDatetime; }
    public void setStartDatetime(String startDatetime) { this.startDatetime = startDatetime; }
}''',
        encoding='utf-8',
    )
    mapper = root / 'src/main/resources/egovframework/mapper/memberSchedule/MemberScheduleMapper.xml'
    mapper.parent.mkdir(parents=True, exist_ok=True)
    mapper.write_text(
        '''<mapper namespace="egovframework.test.memberSchedule.service.impl.MemberScheduleMapper">
<resultMap id="memberScheduleResult" type="egovframework.test.memberSchedule.service.vo.MemberScheduleVO">
  <result property="startDatetime" column="start_datetime"/>
</resultMap>
<select id="selectMemberScheduleList" resultMap="memberScheduleResult">
SELECT schedule_id, start_datetime FROM member_schedule
</select>
</mapper>''',
        encoding='utf-8',
    )
    issues = _scan_jsp_vo_property_mismatch(root)
    messages = [i['message'] for i in issues]
    assert not any('date, day, eventCount' in m for m in messages)
    assert not any('date' in m and 'eventCount' in m for m in messages)


def test_metadata_refs_are_stripped_from_ui_lines():
    body = '<td><c:out value="${memberScheduleVO.schemaName}"/></td>\n<input name="db" value="${memberScheduleVO.db}"/>\n'
    updated = _sanitize_ui_metadata_and_sensitive_refs(body, ['schemaName', 'db'])
    assert 'schemaName' not in updated
    assert 'name="db"' not in updated
