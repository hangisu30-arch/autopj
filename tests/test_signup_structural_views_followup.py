from pathlib import Path

from app.validation.project_auto_repair import _repair_form_fields_incomplete, _repair_jsp_structural_views_artifact


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_repair_form_fields_incomplete_signup_adds_hidden_missing_props(tmp_path: Path):
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/common/header.jsp', '<div>header</div>')
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/common/leftNav.jsp', '<div>left</div>')
    _write(
        tmp_path / 'src/main/java/egovframework/test/member/web/MemberController.java',
        'package egovframework.test.member.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.PostMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        '@Controller\n@RequestMapping("/member")\n'
        'public class MemberController {\n'
        '  @PostMapping("/save.do") public String save(){ return "redirect:/login/login.do"; }\n'
        '}\n',
    )
    signup = tmp_path / 'src/main/webapp/WEB-INF/views/member/signup.jsp'
    _write(signup, '<form><input name="password"/></form>')
    issue = {'details': {'missing_fields': ['id', 'memberId', 'status'], 'vo_props': ['id', 'memberId', 'status', 'password']}}
    assert _repair_form_fields_incomplete(signup, issue, tmp_path) is True
    body = signup.read_text(encoding='utf-8')
    assert 'name="id"' in body
    assert 'name="memberId"' in body
    assert 'name="status"' in body


def test_repair_form_fields_incomplete_rewrites_signup_detail_like_view(tmp_path: Path):
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/common/header.jsp', '<div>header</div>')
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/common/leftNav.jsp', '<div>left</div>')
    _write(
        tmp_path / 'src/main/java/egovframework/test/member/web/MemberController.java',
        'package egovframework.test.member.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.PostMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        '@Controller\n@RequestMapping("/member")\n'
        'public class MemberController {\n'
        '  @PostMapping("/save.do") public String save(){ return "redirect:/login/login.do"; }\n'
        '}\n',
    )
    signup = tmp_path / 'src/main/webapp/WEB-INF/views/signup/signupDetail.jsp'
    _write(signup, '<html><body>broken</body></html>')
    issue = {'details': {'missing_fields': ['memberId', 'status'], 'vo_props': ['memberId', 'status', 'password']}}
    assert _repair_form_fields_incomplete(signup, issue, tmp_path) is True
    body = signup.read_text(encoding='utf-8')
    assert '회원가입' in body
    assert 'name="memberId"' in body
    assert 'name="status"' in body


def test_repair_structural_views_artifact_deletes_file(tmp_path: Path):
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/views/viewsForm.jsp'
    _write(jsp, 'broken')
    assert _repair_jsp_structural_views_artifact(jsp, {}, tmp_path) is True
    assert not jsp.exists()
