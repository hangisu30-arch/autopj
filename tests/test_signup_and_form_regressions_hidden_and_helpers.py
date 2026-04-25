from pathlib import Path

from app.io.execution_core_apply import _rewrite_form_jsp_from_schema
from app.validation.generated_project_validator import _scan_malformed_jsp_structure
from app.validation.project_auto_repair import _repair_malformed_jsp_structure, _rewrite_signup_jsp_to_safe_routes
from execution_core.builtin_crud import schema_for


def test_signup_hidden_managed_fields_do_not_use_empty_value_attr(tmp_path: Path) -> None:
    signup_jsp = tmp_path / "src/main/webapp/WEB-INF/views/signup/signupForm.jsp"
    signup_jsp.parent.mkdir(parents=True, exist_ok=True)
    signup_jsp.write_text("<html><body>broken</body></html>", encoding="utf-8")

    controller = tmp_path / "src/main/java/egovframework/test/member/web/MemberController.java"
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        'package egovframework.test.member.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.*;\n'
        '@Controller @RequestMapping("/member")\n'
        'public class MemberController {\n'
        '  @GetMapping("/signup.do") public String signup(){ return "signup/signupForm"; }\n'
        '  @PostMapping("/save.do") public String save(){ return "redirect:/login/login.do"; }\n'
        '}\n',
        encoding="utf-8",
    )

    vo = tmp_path / "src/main/java/egovframework/test/member/service/vo/SignupVO.java"
    vo.parent.mkdir(parents=True, exist_ok=True)
    vo.write_text(
        'package egovframework.test.member.service.vo;\n'
        'public class SignupVO {\n'
        '  private String memberId;\n'
        '  private String loginId;\n'
        '  private String password;\n'
        '  private String roleCd;\n'
        '  private String useYn;\n'
        '  private String regDt;\n'
        '}\n',
        encoding="utf-8",
    )

    assert _rewrite_signup_jsp_to_safe_routes(signup_jsp, tmp_path) is True
    body = signup_jsp.read_text(encoding="utf-8")
    assert 'name="roleCd"' in body
    assert 'name="useYn"' in body
    assert 'name="regDt"' in body
    assert 'value=""' not in body
    issues = _scan_malformed_jsp_structure(tmp_path)
    assert not any(i["path"].endswith("signup/signupForm.jsp") and "empty hidden primary key binding placeholder" in i["message"] for i in issues)


def test_form_rewrite_includes_runtime_helper_fields_when_validator_requires_full_column_coverage(tmp_path: Path) -> None:
    rel = 'src/main/webapp/WEB-INF/views/member/memberForm.jsp'
    jsp = tmp_path / rel
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text('<html><body><form></form></body></html>', encoding='utf-8')

    schema = schema_for(
        'Member',
        inferred_fields=[
            ('memberId', 'member_id', 'String'),
            ('memberName', 'member_name', 'String'),
            ('roleCd', 'role_cd', 'String'),
            ('useYn', 'use_yn', 'String'),
            ('regDt', 'reg_dt', 'String'),
        ],
        table='tb_member',
        strict_fields=True,
    )

    assert _rewrite_form_jsp_from_schema(tmp_path, rel, schema) is True
    body = jsp.read_text(encoding='utf-8')
    assert 'name="memberId"' in body
    assert 'name="memberName"' in body
    assert 'name="roleCd"' in body
    assert 'name="useYn"' in body
    assert 'name="regDt"' in body


def test_empty_hidden_id_placeholder_is_repaired_with_item_binding(tmp_path: Path) -> None:
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/member/memberForm.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text('<form><input type="hidden" name="memberId" value=""/></form>', encoding='utf-8')
    issue = {"message": "jsp contains empty hidden primary key binding placeholder"}
    assert _repair_malformed_jsp_structure(jsp, issue, tmp_path) is True
    body = jsp.read_text(encoding='utf-8')
    assert "${item.memberId}" in body
