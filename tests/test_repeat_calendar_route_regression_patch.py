from pathlib import Path

from app.ui.ui_sanitize_common import sanitize_frontend_ui_text
from app.io.execution_core_apply import _rewrite_form_jsp_from_schema, _rewrite_list_jsp_from_schema
from app.validation.project_auto_repair import _repair_malformed_jsp_structure, _repair_jsp_missing_route_reference
from execution_core.builtin_crud import schema_for


def test_sanitize_removes_repeat2_placeholder():
    body = "<div>${item.repeat2}</div>\n<div>${item.name}</div>\n"
    cleaned = sanitize_frontend_ui_text(
        'src/main/webapp/WEB-INF/views/member/memberList.jsp',
        body,
        'jsp references undefined VO properties: repeat2',
    )
    assert 'repeat2' not in cleaned
    assert 'name' in cleaned


def test_forbidden_member_calendar_is_deleted(tmp_path: Path):
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/member/memberCalendar.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text('<a href="/member/view.do">x</a>', encoding='utf-8')
    changed = _repair_malformed_jsp_structure(jsp, {'details': {}}, tmp_path)
    assert changed is True
    assert not jsp.exists()


def test_missing_route_repair_deletes_structural_views_calendar(tmp_path: Path):
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/views/viewsCalendar.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text('<a href="/views/view.do">x</a>', encoding='utf-8')
    changed = _repair_jsp_missing_route_reference(jsp, {'details': {'missing_routes': ['/views/view.do']}}, tmp_path)
    assert changed is True
    assert not jsp.exists()


def test_rewrite_form_skips_delete_when_route_missing(tmp_path: Path):
    root = tmp_path
    controller = root / 'src/main/java/egovframework/app/member/web/MemberController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        'package egovframework.app.member.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.GetMapping;\n'
        'import org.springframework.web.bind.annotation.PostMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        '@Controller\n'
        '@RequestMapping("/member")\n'
        'public class MemberController {\n'
        '    @GetMapping("/list.do")\n'
        '    public String list() {\n'
        '        return "member/memberList";\n'
        '    }\n'
        '    @PostMapping("/save.do")\n'
        '    public String save() {\n'
        '        return "redirect:/member/list.do";\n'
        '    }\n'
        '}\n',
        encoding='utf-8',
    )
    jsp = root / 'src/main/webapp/WEB-INF/views/member/memberForm.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text('old', encoding='utf-8')
    schema = schema_for('Member', inferred_fields=[('memberId', 'member_id', 'String'), ('name', 'name', 'String')], table='tb_member')
    schema.routes.update({'save': '/member/save.do', 'list': '/member/list.do', 'delete': '/member/delete.do'})
    _rewrite_form_jsp_from_schema(root, 'src/main/webapp/WEB-INF/views/member/memberForm.jsp', schema)
    body = jsp.read_text(encoding='utf-8')
    assert '/member/delete.do' not in body


def test_rewrite_list_skips_detail_when_route_missing(tmp_path: Path):
    root = tmp_path
    controller = root / 'src/main/java/egovframework/app/member/web/MemberController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        'package egovframework.app.member.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.GetMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        '@Controller\n'
        '@RequestMapping("/member")\n'
        'public class MemberController {\n'
        '    @GetMapping("/list.do")\n'
        '    public String list() {\n'
        '        return "member/memberList";\n'
        '    }\n'
        '}\n',
        encoding='utf-8',
    )
    jsp = root / 'src/main/webapp/WEB-INF/views/member/memberList.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text('old', encoding='utf-8')
    schema = schema_for('Member', inferred_fields=[('memberId', 'member_id', 'String'), ('name', 'name', 'String')], table='tb_member')
    schema.routes.update({'list': '/member/list.do', 'detail': '/member/view.do', 'form': '/member/form.do', 'delete': '/member/delete.do'})
    _rewrite_list_jsp_from_schema(root, 'src/main/webapp/WEB-INF/views/member/memberList.jsp', schema)
    body = jsp.read_text(encoding='utf-8')
    assert '/member/view.do' not in body
