from pathlib import Path

from execution_core.builtin_crud import Schema, builtin_file
from execution_core.feature_rules import FEATURE_KIND_READONLY
from app.validation.backend_compile_repair import _ensure_dao_mapper_method_alignment
from app.validation.post_generation_repair import _sanitize_frontend_ui_file


def _schema():
    return Schema(
        entity="MemberSchedule",
        entity_var="memberSchedule",
        table="member_schedule",
        id_prop="scheduleId",
        id_column="schedule_id",
        fields=[("scheduleId", "schedule_id", "String"), ("scheduleTitle", "schedule_title", "String")],
        routes={},
        views={},
        feature_kind=FEATURE_KIND_READONLY,
    )


def test_read_only_mapper_builtin_contains_map_overload():
    spec = "read-only member schedule table member_schedule columns schedule_id, schedule_title"
    mapper = builtin_file("java/service/mapper/MemberScheduleMapper.java", "egovframework.test.memberSchedule", _schema())
    assert "List<MemberScheduleVO> selectMemberScheduleList();" in mapper
    assert "List<MemberScheduleVO> selectMemberScheduleList(Map<String, Object> params);" in mapper


def test_dao_mapper_alignment_adds_missing_overload_even_when_name_exists(tmp_path: Path):
    dao = tmp_path / "src/main/java/egovframework/test/memberSchedule/service/impl/MemberScheduleDAO.java"
    mapper = tmp_path / "src/main/java/egovframework/test/memberSchedule/service/mapper/MemberScheduleMapper.java"
    dao.parent.mkdir(parents=True, exist_ok=True)
    mapper.parent.mkdir(parents=True, exist_ok=True)
    dao.write_text(
        "package egovframework.test.memberSchedule.service.impl;\n"
        "import java.util.Map;\n"
        "import egovframework.test.memberSchedule.service.mapper.MemberScheduleMapper;\n"
        "import egovframework.test.memberSchedule.service.vo.MemberScheduleVO;\n"
        "public class MemberScheduleDAO {\n"
        "  private final MemberScheduleMapper memberScheduleMapper;\n"
        "  public MemberScheduleDAO(MemberScheduleMapper memberScheduleMapper){ this.memberScheduleMapper = memberScheduleMapper; }\n"
        "  public java.util.List<MemberScheduleVO> selectMemberScheduleList(Map<String,Object> params) throws Exception { return memberScheduleMapper.selectMemberScheduleList(params); }\n"
        "}\n", encoding="utf-8")
    mapper.write_text(
        "package egovframework.test.memberSchedule.service.mapper;\n"
        "import java.util.List;\n"
        "import org.apache.ibatis.annotations.Mapper;\n"
        "import egovframework.test.memberSchedule.service.vo.MemberScheduleVO;\n"
        "@Mapper public interface MemberScheduleMapper {\n"
        "  List<MemberScheduleVO> selectMemberScheduleList();\n"
        "}\n", encoding="utf-8")
    changes = _ensure_dao_mapper_method_alignment(tmp_path, str(dao.relative_to(tmp_path)).replace('\\','/'))
    body = mapper.read_text(encoding='utf-8')
    assert changes
    assert 'selectMemberScheduleList(@Param("params") Map<String,Object> params);' in body or 'selectMemberScheduleList(Map<String, Object> params);' in body


def test_sanitize_frontend_ui_file_removes_metadata_headers_and_placeholders(tmp_path: Path):
    jsp = tmp_path / "src/main/webapp/WEB-INF/views/memberSchedule/memberScheduleList.jsp"
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text("<table><tr><th>db</th><th>schemaName</th></tr><tr><td>${memberSchedule.repeat7}</td><td>${memberSchedule.section}</td></tr></table>", encoding="utf-8")
    changed = _sanitize_frontend_ui_file(jsp, 'non-auth UI must not expose generation metadata fields such as db/schemaName/tableName/packageName')
    body = jsp.read_text(encoding='utf-8')
    assert changed
    assert 'schemaName' not in body and 'db' not in body
