from pathlib import Path

from app.validation.generated_project_validator import _parse_schema_sql_tables, validate_generated_project
from app.validation.project_auto_repair import _cleanup_orphan_jsp_closing_tags, _rewrite_signup_jsp_to_safe_routes
from app.io.execution_core_apply import _is_hidden_form_helper_field
from app.ui.state import ProjectConfig


def test_schema_parser_prefers_primary_schema_and_merges_comment_on_column(tmp_path: Path):
    (tmp_path / 'src/main/resources/db').mkdir(parents=True, exist_ok=True)
    (tmp_path / 'src/main/resources/schema.sql').write_text(
        "CREATE TABLE IF NOT EXISTS tb_member (\n"
        "  member_id VARCHAR(20) COMMENT '회원ID',\n"
        "  member_nm VARCHAR(100)\n"
        ");\n"
        "COMMENT ON COLUMN tb_member.member_nm IS '회원명';\n",
        encoding='utf-8',
    )
    (tmp_path / 'src/main/resources/login-schema.sql').write_text(
        "CREATE TABLE IF NOT EXISTS tb_member (login_id VARCHAR(20));\n",
        encoding='utf-8',
    )
    info = _parse_schema_sql_tables(tmp_path)['tb_member']
    assert info['columns'] == ['member_id', 'member_nm']
    assert info['comments']['member_nm'] == '회원명'
    assert info['path'] == 'src/main/resources/schema.sql'


def test_cleanup_balances_open_only_form_and_c_if():
    raw = '<form><div><c:if test="${not empty item}"><span>x</span>'
    fixed = _cleanup_orphan_jsp_closing_tags(raw)
    assert '</c:if>' in fixed
    assert '</div>' in fixed
    assert '</form>' in fixed


def test_signup_rewrite_does_not_emit_empty_hidden_value(tmp_path: Path):
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/signup/signupForm.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text('<html></html>', encoding='utf-8')
    controller = tmp_path / 'src/main/java/egovframework/app/member/web/MemberController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        'package egovframework.app.member.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.*;\n'
        '@Controller @RequestMapping("/member") public class MemberController {\n'
        ' @PostMapping("/save.do") public String save(){ return "redirect:/login/login.do"; }\n'
        ' @GetMapping("/checkLoginId.do") public @ResponseBody String check(@RequestParam String loginId){ return "true"; }\n'
        '}\n',
        encoding='utf-8',
    )
    vo = tmp_path / 'src/main/java/egovframework/app/member/service/MemberVO.java'
    vo.parent.mkdir(parents=True, exist_ok=True)
    vo.write_text(
        'package egovframework.app.member.service; public class MemberVO {\n'
        ' private String loginId; private String password; private String regDt;\n'
        ' public String getLoginId(){return loginId;} public void setLoginId(String v){loginId=v;}\n'
        ' public String getPassword(){return password;} public void setPassword(String v){password=v;}\n'
        ' public String getRegDt(){return regDt;} public void setRegDt(String v){regDt=v;}\n'
        '}\n',
        encoding='utf-8',
    )
    assert _rewrite_signup_jsp_to_safe_routes(jsp, tmp_path)
    body = jsp.read_text(encoding='utf-8')
    assert 'value=""' not in body
    assert '<input type="hidden" name="regDt"/>' in body


def test_business_audit_columns_are_not_hidden_helpers():
    for prop, col in [('roleCd', 'role_cd'), ('useYn', 'use_yn'), ('regDt', 'reg_dt'), ('createdAt', 'created_at'), ('updatedAt', 'updated_at'), ('createdBy', 'created_by')]:
        assert _is_hidden_form_helper_field(prop, col) is False


def test_forbidden_member_calendar_is_reported(tmp_path: Path):
    calendar = tmp_path / 'src/main/webapp/WEB-INF/views/member/memberCalendar.jsp'
    calendar.parent.mkdir(parents=True, exist_ok=True)
    calendar.write_text('<html></html>', encoding='utf-8')
    result = validate_generated_project(tmp_path, ProjectConfig(frontend_key='jsp'), include_runtime=False)
    messages = [item.get('message') or item.get('details', {}).get('message') or '' for item in result.get('issues') or []]
    assert any('calendar artifact must not be generated' in msg for msg in messages)
