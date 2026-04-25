from pathlib import Path

from app.ui.ui_sanitize_common import sanitize_frontend_ui_text
from app.validation.generated_project_validator import validate_generated_project
from app.validation.project_auto_repair import apply_generated_project_auto_repair


class _Cfg:
    frontend_key = "jsp"
    database_key = "mysql"


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_sanitize_removes_metadata_without_leaving_orphan_tags() -> None:
    body = (
        '<body>\n'
        '<div class="page-card">\n'
        '  <div>${schemaName}</div>\n'
        '</div>\n'
        '</div>\n'
        '</body>\n'
    )
    sanitized = sanitize_frontend_ui_text('src/main/webapp/WEB-INF/views/member/memberDetail.jsp', body, 'non-auth UI must not expose generation metadata fields such as db/schemaName/tableName/packageName')
    assert '${schemaName}' not in sanitized
    assert sanitized.count('</div>') == 1


def test_validator_flags_midstream_orphan_closing_tags(tmp_path: Path) -> None:
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/member/memberDetail.jsp', '<html><body><div>ok</div></div></c:if></body></html>')
    report = validate_generated_project(tmp_path, _Cfg(), include_runtime=False)
    messages = [item.get('message') or item.get('reason') or '' for item in report.get('static_issues') or []]
    assert any('orphan closing div tag' in message or 'orphan closing c:if tag' in message for message in messages)


def test_auto_repair_rebuilds_member_form_when_only_closing_form_exists(tmp_path: Path) -> None:
    _write(
        tmp_path / 'src/main/java/egovframework/test/member/web/MemberController.java',
        'package egovframework.test.member.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.GetMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        '@Controller\n@RequestMapping("/member")\n'
        'public class MemberController {\n'
        '  @GetMapping("/list.do") public String list(){ return "member/memberList"; }\n'
        '  @GetMapping("/form.do") public String form(){ return "member/memberForm"; }\n'
        '  @GetMapping("/detail.do") public String detail(){ return "member/memberDetail"; }\n'
        '}\n',
    )
    _write(
        tmp_path / 'src/main/java/egovframework/test/member/service/vo/MemberVO.java',
        'package egovframework.test.member.service.vo;\n'
        'public class MemberVO {\n'
        '  private String memberId;\n'
        '  private String email;\n'
        '  public String getMemberId(){ return memberId; }\n'
        '  public String getEmail(){ return email; }\n'
        '}\n',
    )
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/common/header.jsp', '<div>header</div>')
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/common/leftNav.jsp', '<div>nav</div>')
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/member/memberForm.jsp', '<html><body></form></body></html>')

    validation_report = {
        'issues': [
            {'type': 'malformed_jsp_structure', 'path': 'src/main/webapp/WEB-INF/views/member/memberForm.jsp', 'repairable': True},
        ]
    }
    repaired = apply_generated_project_auto_repair(tmp_path, validation_report)
    assert repaired['changed_count'] == 1
    body = (tmp_path / 'src/main/webapp/WEB-INF/views/member/memberForm.jsp').read_text(encoding='utf-8')
    assert '<form ' in body
    assert body.count('<form') == body.count('</form>') == 1
    assert 'name="memberId"' in body
    assert 'name="email"' in body
