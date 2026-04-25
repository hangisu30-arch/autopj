from pathlib import Path

from app.validation.backend_compile_repair import _ensure_dao_mapper_method_alignment
from app.validation.post_generation_repair import _sanitize_frontend_ui_file
from app.ui.generated_content_validator import validate_generated_content


def test_ensure_dao_mapper_method_alignment_adds_missing_mapper_methods(tmp_path: Path):
    dao = tmp_path / "src/main/java/egovframework/test/memberSchedule/service/impl/MemberScheduleDAO.java"
    mapper = tmp_path / "src/main/java/egovframework/test/memberSchedule/service/mapper/MemberScheduleMapper.java"
    dao.parent.mkdir(parents=True, exist_ok=True)
    mapper.parent.mkdir(parents=True, exist_ok=True)
    dao.write_text(
        "package egovframework.test.memberSchedule.service.impl;\n"
        "import java.util.LinkedHashMap;\nimport java.util.List;\nimport java.util.Map;\n"
        "import egovframework.test.memberSchedule.service.mapper.MemberScheduleMapper;\n"
        "import egovframework.test.memberSchedule.service.vo.MemberScheduleVO;\n"
        "public class MemberScheduleDAO {\n"
        "  private final MemberScheduleMapper memberScheduleMapper;\n"
        "  public MemberScheduleDAO(MemberScheduleMapper memberScheduleMapper){ this.memberScheduleMapper = memberScheduleMapper; }\n"
        "  public List<MemberScheduleVO> selectMemberScheduleList() throws Exception { return memberScheduleMapper.selectMemberScheduleList(new LinkedHashMap<>()); }\n"
        "  public List<MemberScheduleVO> selectMemberScheduleList(Map<String, Object> params) throws Exception { return memberScheduleMapper.selectMemberScheduleList(params == null ? new LinkedHashMap<>() : params); }\n"
        "  public MemberScheduleVO selectMemberSchedule(String scheduleId) throws Exception { return memberScheduleMapper.selectMemberSchedule(scheduleId); }\n"
        "}\n",
        encoding="utf-8",
    )
    mapper.write_text(
        "package egovframework.test.memberSchedule.service.mapper;\n"
        "import egovframework.test.memberSchedule.service.vo.MemberScheduleVO;\n"
        "public interface MemberScheduleMapper { }\n",
        encoding="utf-8",
    )
    changed = _ensure_dao_mapper_method_alignment(tmp_path, dao.relative_to(tmp_path).as_posix())
    body = mapper.read_text(encoding="utf-8")
    assert changed
    assert "selectMemberScheduleList(Map<String, Object> params);" in body
    assert "selectMemberSchedule(@Param(\"scheduleId\") String scheduleId);" in body


def test_manifestless_frontend_ui_sanitize_can_clear_generation_metadata(tmp_path: Path):
    jsp = tmp_path / "src/main/webapp/WEB-INF/views/memberSchedule/memberScheduleList.jsp"
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text('<div>${memberScheduleVO.scheduleTitle}</div>\n<input type="hidden" name="db" value="${memberScheduleVO.db}"/>\n<span>${memberScheduleVO.schemaName}</span>\n', encoding="utf-8")
    assert _sanitize_frontend_ui_file(jsp, 'non-auth UI must not expose generation metadata fields such as db/schemaName/tableName/packageName')
    body = jsp.read_text(encoding="utf-8")
    ok, _reason = validate_generated_content(jsp.as_posix(), body, frontend_key='jsp')
    assert ok
