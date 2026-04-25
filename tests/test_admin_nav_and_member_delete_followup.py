from pathlib import Path
import sys
import types

# lightweight stubs for patch-only zip structure
exec_core = types.ModuleType('execution_core')
builtin_crud = types.ModuleType('execution_core.builtin_crud')
builtin_crud.builtin_file = lambda *a, **k: None
builtin_crud.infer_schema_from_file_ops = lambda *a, **k: {}
builtin_crud.schema_for = lambda *a, **k: {}
feature_rules = types.ModuleType('execution_core.feature_rules')
feature_rules.FEATURE_KIND_AUTH = 'auth'
feature_rules.FEATURE_KIND_CRUD = 'crud'
feature_rules.FEATURE_KIND_SCHEDULE = 'schedule'
exec_core.builtin_crud = builtin_crud
exec_core.feature_rules = feature_rules
sys.modules['execution_core'] = exec_core
sys.modules['execution_core.builtin_crud'] = builtin_crud
sys.modules['execution_core.feature_rules'] = feature_rules

app_io = types.ModuleType('app.io')
execution_core_apply = types.ModuleType('app.io.execution_core_apply')
execution_core_apply._rewrite_detail_jsp_from_schema = lambda *a, **k: ''
execution_core_apply._rewrite_form_jsp_from_schema = lambda *a, **k: ''
execution_core_apply._rewrite_list_jsp_from_schema = lambda *a, **k: ''
app_io.execution_core_apply = execution_core_apply
sys.modules['app.io'] = app_io
sys.modules['app.io.execution_core_apply'] = execution_core_apply

from app.validation.project_auto_repair import _repair_auth_nav_route_mismatch, _repair_delete_ui, _repair_search_fields_incomplete


def test_auth_nav_route_repair_rewrites_admin_helpers(tmp_path: Path):
    project_root = tmp_path / 'project'
    nav = project_root / 'src/main/webapp/WEB-INF/views/common/header.jsp'
    nav.parent.mkdir(parents=True, exist_ok=True)
    nav.write_text("""
<ul>
  <li><a href="<c:url value='/member/checkLoginId.do' />">로그인</a></li>
  <li><a href="<c:url value='/member/register.do' />">회원가입</a></li>
</ul>
""", encoding='utf-8')
    issue = {'details': {'login_route': '/admin/checkLoginId.do', 'signup_route': '/admin/register.do'}}
    assert _repair_auth_nav_route_mismatch(nav, issue, project_root)
    body = nav.read_text(encoding='utf-8')
    assert "/admin/checkLoginId.do" in body
    assert "/admin/register.do" in body
    assert "/member/checkLoginId.do" not in body


def test_delete_ui_repair_adds_delete_form_to_member_list(tmp_path: Path):
    project_root = tmp_path / 'project'
    controller = project_root / 'src/main/java/egovframework/test/member/web/MemberController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text('class MemberController {}', encoding='utf-8')
    jsp = project_root / 'src/main/webapp/WEB-INF/views/member/memberList.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text('<table><tr><td>${item.memberId}</td></tr></table>', encoding='utf-8')
    issue = {'details': {'delete_route': '/member/delete.do', 'id_prop': 'memberId'}}
    assert _repair_delete_ui(controller, issue, project_root)
    body = jsp.read_text(encoding='utf-8')
    assert '/member/delete.do' in body
    assert 'memberId' in body
    assert '삭제' in body


def test_search_fields_incomplete_adds_regdt_input(tmp_path: Path):
    jsp = tmp_path / 'memberList.jsp'
    jsp.write_text('<table></table>', encoding='utf-8')
    issue = {'details': {'missing_fields': ['regDt']}}
    assert _repair_search_fields_incomplete(jsp, issue, tmp_path)
    body = jsp.read_text(encoding='utf-8')
    assert 'name="regDt"' in body
