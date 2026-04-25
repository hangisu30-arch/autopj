from pathlib import Path
import sys
import types

# Minimal stubs so importing app.validation submodules does not pull the full runtime stack.
for name, attrs in {
    'app.validation.global_validator': {'validate_generation_context': lambda *a, **k: {}},
    'app.validation.error_classifier': {'classify_validation_errors': lambda *a, **k: {}},
    'app.validation.repair_dispatcher': {
        'build_repair_plan': lambda *a, **k: {},
        'repair_plan_to_prompt_text': lambda *a, **k: '',
    },
    'app.validation.file_regenerator': {'build_targeted_regen_prompt': lambda *a, **k: ''},
    'app.validation.post_generation_repair': {'validate_and_repair_generated_files': lambda *a, **k: {}},
}.items():
    mod = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    sys.modules[name] = mod

exec_core = types.ModuleType('execution_core')
builtin_crud = types.ModuleType('execution_core.builtin_crud')
builtin_crud.builtin_file = lambda *a, **k: None
builtin_crud.infer_schema_from_file_ops = lambda *a, **k: {}
builtin_crud.schema_for = lambda *a, **k: {}
builtin_crud._db_reserved_keywords = lambda *a, **k: set()
builtin_crud._normalize_db_vendor = lambda *a, **k: ''
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
sys.modules['app.io'] = app_io
sys.modules['app.io.execution_core_apply'] = execution_core_apply

from app.validation.project_auto_repair import _repair_auth_nav_route_mismatch, _repair_delete_ui, _repair_search_fields_incomplete
from app.validation.generated_project_validator import _scan_common_auth_navigation, _scan_search_fields_cover_all_columns


def test_missing_delete_ui_from_controller_repairs_member_list_jsp(tmp_path: Path):
    root = tmp_path
    controller = root / 'src/main/java/egovframework/test/member/web/MemberController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        '@Controller\n@RequestMapping("/member")\n'
        'class MemberController { @PostMapping("/delete.do") String delete(){return "redirect:/member/list.do";} }',
        encoding='utf-8',
    )
    jsp = root / 'src/main/webapp/WEB-INF/views/member/memberList.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text('<table><tr><td>${item.memberId}</td></tr></table>', encoding='utf-8')

    assert _repair_delete_ui(
        controller,
        {'details': {'delete_route': '/member/delete.do', 'id_prop': 'memberId'}},
        root,
    ) is True
    body = jsp.read_text(encoding='utf-8')
    assert '/member/delete.do' in body
    assert 'memberId' in body
    assert '삭제' in body


def test_search_validator_accepts_temporal_range_inputs_and_repair_adds_them(tmp_path: Path):
    root = tmp_path
    vo = root / 'src/main/java/egovframework/test/member/service/vo/MemberVO.java'
    vo.parent.mkdir(parents=True, exist_ok=True)
    vo.write_text(
        'package x; public class MemberVO { private String regDt; private String memberName; }',
        encoding='utf-8',
    )
    jsp = root / 'src/main/webapp/WEB-INF/views/member/memberList.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text(
        '<form id="searchForm" method="get"><input type="text" name="memberName"/><button type="submit">검색</button></form>',
        encoding='utf-8',
    )

    assert _repair_search_fields_incomplete(jsp, {'details': {'missing_fields': ['regDt']}}, root) is True
    body = jsp.read_text(encoding='utf-8')
    assert 'name="regDtFrom"' in body
    assert 'name="regDtTo"' in body
    assert not _scan_search_fields_cover_all_columns(root)


def test_auth_nav_repair_appends_exact_adminmember_login_and_signup_routes(tmp_path: Path):
    root = tmp_path
    controller = root / 'src/main/java/egovframework/test/adminMember/web/AdminMemberController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        '@Controller\n@RequestMapping("/adminMember")\n'
        'class AdminMemberController { '
        '@GetMapping("/checkLoginId.do") String login(){return "";} '
        '@GetMapping("/register.do") String register(){return "";} }',
        encoding='utf-8',
    )
    header = root / 'src/main/webapp/WEB-INF/views/common/header.jsp'
    leftnav = root / 'src/main/webapp/WEB-INF/views/common/leftNav.jsp'
    header.parent.mkdir(parents=True, exist_ok=True)
    leftnav.parent.mkdir(parents=True, exist_ok=True)
    header.write_text('<ul><li><a href="<c:url value=\'/login/login.do\' />">로그인</a></li></ul>', encoding='utf-8')
    leftnav.write_text('<aside><ul><li><a href="<c:url value=\'/login/login.do\' />"><span>로그인</span></a></li></ul></aside>', encoding='utf-8')

    issue = {'details': {'login_route': '/adminMember/checkLoginId.do', 'signup_route': '/adminMember/register.do'}}
    assert _repair_auth_nav_route_mismatch(header, issue, root) is True
    assert _repair_auth_nav_route_mismatch(leftnav, issue, root) is True

    assert '/adminMember/checkLoginId.do' in header.read_text(encoding='utf-8')
    assert '/adminMember/register.do' in header.read_text(encoding='utf-8')
    assert '/adminMember/checkLoginId.do' in leftnav.read_text(encoding='utf-8')
    assert '/adminMember/register.do' in leftnav.read_text(encoding='utf-8')
    assert not _scan_common_auth_navigation(root)
