from pathlib import Path

from execution_core.builtin_crud import Schema, builtin_file
from app.validation.project_auto_repair import _repair_jsp_vo_property_mismatch


def _schema() -> Schema:
    return Schema(
        entity="MemberSchedule",
        entity_var="memberSchedule",
        table="member_schedule",
        id_prop="scheduleId",
        id_column="schedule_id",
        fields=[
            ("scheduleId", "schedule_id", "String"),
            ("scheduleTitle", "schedule_title", "String"),
            ("startDatetime", "start_datetime", "String"),
            ("endDatetime", "end_datetime", "String"),
        ],
        routes={},
        views={},
        feature_kind="SCHEDULE",
    )


def test_builtin_file_generates_non_auth_dao_delegate():
    content = builtin_file("java/service/impl/MemberScheduleDAO.java", "egovframework.test.memberSchedule", _schema())
    assert content
    assert "class MemberScheduleDAO" in content
    assert "MemberScheduleMapper memberScheduleMapper" in content
    assert "selectMemberScheduleList" in content
    assert "insertMemberSchedule" in content


def test_jsp_vo_property_mismatch_repair_removes_sensitive_metadata_and_placeholder_refs(tmp_path: Path):
    root = tmp_path
    jsp = root / "src/main/webapp/WEB-INF/views/memberSchedule/memberScheduleDetail.jsp"
    vo = root / "src/main/java/egovframework/test/memberSchedule/service/vo/MemberScheduleVO.java"
    jsp.parent.mkdir(parents=True, exist_ok=True)
    vo.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text(
        "<div>${item.password}</div>\n<div>${item.db}</div>\n<div>${item.repeat7}</div>\n<div>${item.section}</div>\n<div>${item.startDatetime}</div>\n",
        encoding="utf-8",
    )
    vo.write_text(
        "package egovframework.test.memberSchedule.service.vo;\npublic class MemberScheduleVO {\n    private String startDatetime;\n    public String getStartDatetime() { return startDatetime; }\n    public void setStartDatetime(String startDatetime) { this.startDatetime = startDatetime; }\n}\n",
        encoding="utf-8",
    )
    issue = {
        "details": {
            "vo_path": "src/main/java/egovframework/test/memberSchedule/service/vo/MemberScheduleVO.java",
            "available_props": ["startDatetime"],
            "mapper_props": ["startDatetime"],
            "missing_props": ["password", "db", "repeat7", "section"],
            "missing_props_by_var": {"item": ["password", "db", "repeat7", "section"]},
            "suggested_replacements": {},
        }
    }
    changed = _repair_jsp_vo_property_mismatch(jsp, issue, root)
    body = jsp.read_text(encoding="utf-8")
    assert changed
    assert "password" not in body
    assert "repeat7" not in body
    assert "section" not in body
    assert "${item.startDatetime}" in body
