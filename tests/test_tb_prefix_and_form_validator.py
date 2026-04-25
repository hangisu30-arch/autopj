from pathlib import Path
from types import SimpleNamespace

from execution_core.builtin_crud import schema_for
from app.validation.generated_project_validator import validate_generated_project


def test_schema_for_enforces_tb_prefix():
    schema = schema_for("Member", [("memberId", "member_id", "String")], table="member")
    assert schema.table == "tb_member"


def test_validator_flags_missing_tb_prefix_and_incomplete_form(tmp_path: Path):
    project_root = tmp_path / "proj"
    (project_root / "src/main/java/egovframework/test/member/service/vo").mkdir(parents=True, exist_ok=True)
    (project_root / "src/main/webapp/WEB-INF/views/member").mkdir(parents=True, exist_ok=True)
    (project_root / "src/main/resources/egovframework/mapper/member").mkdir(parents=True, exist_ok=True)

    (project_root / "src/main/java/egovframework/test/member/service/vo/MemberVO.java").write_text("""package egovframework.test.member.service.vo;

public class MemberVO {
    private String memberId;
    private String memberName;
    private String email;
}
""", encoding="utf-8")
    (project_root / "src/main/webapp/WEB-INF/views/member/memberForm.jsp").write_text("""<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<form method="post">
  <input type="text" name="memberId" />
</form>
""", encoding="utf-8")
    (project_root / "src/main/resources/schema.sql").parent.mkdir(parents=True, exist_ok=True)
    (project_root / "src/main/resources/schema.sql").write_text("""CREATE TABLE member (
  member_id VARCHAR(20),
  member_name VARCHAR(100),
  email VARCHAR(100)
);
""", encoding="utf-8")
    (project_root / "src/main/resources/egovframework/mapper/member/MemberMapper.xml").write_text("""<!DOCTYPE mapper PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN" "http://mybatis.org/dtd/mybatis-3-mapper.dtd">
<mapper namespace="egovframework.test.member.service.mapper.MemberMapper">
  <select id="selectMemberList" resultType="map">SELECT member_id, member_name, email FROM member</select>
</mapper>
""", encoding="utf-8")

    cfg = SimpleNamespace(frontend_key='jsp', database_key='mysql', database_type='mysql')
    result = validate_generated_project(project_root, cfg, include_runtime=False)
    codes = {issue["code"] for issue in result.get("issues", [])}
    assert "table_prefix_missing" in codes
    assert "form_fields_incomplete" in codes
