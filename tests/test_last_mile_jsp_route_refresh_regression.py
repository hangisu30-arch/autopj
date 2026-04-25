from pathlib import Path
from types import SimpleNamespace

from app.validation import post_generation_repair as pgr


def _write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def test_last_mile_jsp_refresh_rewrites_index_and_membership_routes(tmp_path: Path, monkeypatch):
    root = tmp_path
    index_jsp = root / 'src/main/webapp/index.jsp'
    static_index = root / 'src/main/resources/static/index.html'
    controller = root / 'src/main/java/egovframework/test/adminMember/web/AdminMemberController.java'
    admin_list = root / 'src/main/webapp/WEB-INF/views/adminMember/adminMemberList.jsp'

    _write(index_jsp, '<%@ page contentType="text/html; charset=UTF-8" %>\n<% response.sendRedirect(request.getContextPath() + "/broken.do"); %>')
    _write(static_index, '<html><body>broken</body></html>')
    _write(
        controller,
        'package egovframework.test.adminMember.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.*;\n'
        'import org.springframework.ui.Model;\n'
        '@Controller\n@RequestMapping("/adminMember")\n'
        'public class AdminMemberController {\n'
        '  @GetMapping("/list.do") public String list(Model model){ return "adminMember/adminMemberList"; }\n'
        '  @GetMapping("/detail.do") public String detail(@RequestParam("id") String id, Model model){ return "adminMember/adminMemberDetail"; }\n'
        '}\n',
    )
    _write(admin_list, '<a href="<c:url value="/member/detail.do"/>">상세</a><a href="<c:url value="/member/form.do"/>">수정</a>')

    def fake_patch_generated_jsp_assets(project_root, generated_rel_paths, preferred_entity, schema_map, cfg):
        _write(index_jsp, '<%@ page contentType="text/html; charset=UTF-8" %>\n<% response.sendRedirect(request.getContextPath() + "/adminMember/list.do"); return; %>')
        _write(static_index, '<html><head><meta http-equiv="refresh" content="0;url=/adminMember/list.do"/></head></html>')
        return {'index_jsp': 'src/main/webapp/index.jsp', 'static_index_html': 'src/main/resources/static/index.html'}

    def fake_validate_generated_project(project_root, cfg, manifest=None, include_runtime=False):
        issues = []
        if '/adminMember/list.do' not in index_jsp.read_text(encoding='utf-8'):
            issues.append({'type': 'index_entrypoint_miswired', 'path': 'src/main/webapp/index.jsp', 'message': 'index bad', 'details': {}})
        body = admin_list.read_text(encoding='utf-8')
        if '/member/detail.do' in body or '/member/form.do' in body:
            issues.append({
                'type': 'jsp_missing_route_reference',
                'path': 'src/main/webapp/WEB-INF/views/adminMember/adminMemberList.jsp',
                'message': 'bad routes',
                'details': {'missing_routes': ['/member/detail.do', '/member/form.do'], 'discovered_routes': ['/adminMember/list.do', '/adminMember/detail.do', '/adminMember/form.do']},
            })
        if '@RequestParam("id")' in controller.read_text(encoding='utf-8'):
            issues.append({
                'type': 'route_param_mismatch',
                'path': 'src/main/java/egovframework/test/adminMember/web/AdminMemberController.java',
                'message': 'param mismatch',
                'details': {'domain': 'adminMember', 'route_params': {'/adminMember/detail.do': 'memberId'}, 'jsp_paths': ['src/main/webapp/WEB-INF/views/adminMember/adminMemberList.jsp']},
            })
        return {'static_issue_count': len(issues), 'static_issues': issues}

    def fake_apply_generated_project_auto_repair(project_root, validation_state):
        _write(admin_list, '<a href="<c:url value="/adminMember/detail.do"/>">상세</a><a href="<c:url value="/adminMember/form.do"/>">수정</a>')
        _write(
            controller,
            controller.read_text(encoding='utf-8').replace('@RequestParam("id")', '@RequestParam("memberId")')
        )
        return {'changed_count': 2, 'changed': [{'path': 'src/main/webapp/WEB-INF/views/adminMember/adminMemberList.jsp'}, {'path': 'src/main/java/egovframework/test/adminMember/web/AdminMemberController.java'}], 'skipped': []}

    monkeypatch.setattr(pgr, '_patch_generated_jsp_assets', fake_patch_generated_jsp_assets)
    monkeypatch.setattr(pgr, 'validate_generated_project', fake_validate_generated_project)
    monkeypatch.setattr(pgr, 'apply_generated_project_auto_repair', fake_apply_generated_project_auto_repair)
    monkeypatch.setattr(pgr, '_preferred_crud_entity', lambda file_ops: 'AdminMember')
    monkeypatch.setattr(pgr, '_schema_map_from_file_ops', lambda file_ops: {})
    monkeypatch.setattr(pgr, '_reconcile_manifest_paths', lambda root, manifest: manifest)
    monkeypatch.setattr(pgr, '_reconcile_rel_paths', lambda root, rel_paths: rel_paths)
    monkeypatch.setattr(pgr, '_prune_stale_auth_rel_paths', lambda root, rel_paths: rel_paths)

    manifest, rel_paths, validation_state, reports = pgr._refresh_last_mile_jsp_assets_and_routes(
        root,
        SimpleNamespace(frontend_key='jsp'),
        [],
        [
            'src/main/webapp/index.jsp',
            'src/main/resources/static/index.html',
            'src/main/webapp/WEB-INF/views/adminMember/adminMemberList.jsp',
            'src/main/java/egovframework/test/adminMember/web/AdminMemberController.java',
        ],
        {},
        {'static_issue_count': 1, 'static_issues': []},
        max_passes=2,
    )

    assert reports
    assert validation_state.get('static_issue_count') == 0
    assert '/adminMember/list.do' in index_jsp.read_text(encoding='utf-8')
    assert '/adminMember/detail.do' in admin_list.read_text(encoding='utf-8')
    assert '@RequestParam("memberId")' in controller.read_text(encoding='utf-8')
