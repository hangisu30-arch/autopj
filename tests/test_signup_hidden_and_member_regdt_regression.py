from pathlib import Path

from app.io.execution_core_apply import _rewrite_form_jsp_from_schema
from app.validation.generated_project_validator import _scan_malformed_jsp_structure
from app.validation.project_auto_repair import _rewrite_signup_jsp_to_safe_routes
from execution_core.builtin_crud import schema_for
from execution_core.feature_rules import FEATURE_KIND_CRUD


def test_signup_rewrite_does_not_emit_empty_hidden_value_placeholders(tmp_path: Path) -> None:
    signup_jsp = tmp_path / "src/main/webapp/WEB-INF/views/signup/signupForm.jsp"
    signup_jsp.parent.mkdir(parents=True, exist_ok=True)
    signup_jsp.write_text("<html><body>broken</body></html>", encoding="utf-8")

    controller = tmp_path / "src/main/java/egovframework/test/member/web/MemberController.java"
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        "package egovframework.test.member.web;\n"
        "import org.springframework.stereotype.Controller;\n"
        "import org.springframework.web.bind.annotation.GetMapping;\n"
        "import org.springframework.web.bind.annotation.PostMapping;\n"
        "import org.springframework.web.bind.annotation.RequestMapping;\n"
        "@Controller\n@RequestMapping(\"/member\")\n"
        "public class MemberController {\n"
        "  @GetMapping(\"/signup.do\") public String signup(){ return \"signup/signupForm\"; }\n"
        "  @PostMapping(\"/save.do\") public String save(){ return \"redirect:/login/login.do\"; }\n"
        "  @GetMapping(\"/checkLoginId.do\") public String check(){ return \"jsonView\"; }\n"
        "}\n",
        encoding="utf-8",
    )

    vo = tmp_path / "src/main/java/egovframework/test/member/service/vo/SignupVO.java"
    vo.parent.mkdir(parents=True, exist_ok=True)
    vo.write_text(
        "package egovframework.test.member.service.vo;\n"
        "public class SignupVO {\n"
        "  private String loginId;\n"
        "  private String password;\n"
        "  private String memberName;\n"
        "  private String roleCd;\n"
        "  private String useYn;\n"
        "  private String regDt;\n"
        "}\n",
        encoding="utf-8",
    )

    assert _rewrite_signup_jsp_to_safe_routes(signup_jsp, tmp_path) is True
    body = signup_jsp.read_text(encoding="utf-8")
    assert 'type="hidden" name="roleCd"/>' in body
    assert 'type="hidden" name="useYn"/>' in body
    assert 'type="hidden" name="regDt"/>' in body
    issues = _scan_malformed_jsp_structure(tmp_path)
    assert not any('empty hidden primary key binding placeholder' in (issue.get('message') or '') for issue in issues)


def test_member_form_rewrite_keeps_regdt_visible(tmp_path: Path) -> None:
    rel = 'src/main/webapp/WEB-INF/views/member/memberForm.jsp'
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('<html><body>broken</body></html>', encoding='utf-8')

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
        feature_kind=FEATURE_KIND_CRUD,
        strict_fields=True,
    )

    assert _rewrite_form_jsp_from_schema(tmp_path, rel, schema) is True
    body = path.read_text(encoding='utf-8')
    assert 'name="roleCd"' in body
    assert 'name="useYn"' in body
    assert 'name="regDt"' in body
