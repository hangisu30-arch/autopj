from pathlib import Path

from app.io.execution_core_apply import _patch_generated_jsp_assets


class DummySchema:
    def __init__(self, entity_var: str, feature_kind: str, routes: dict[str, str]):
        self.entity_var = entity_var
        self.feature_kind = feature_kind
        self.routes = routes


def test_jsp_design_assets_merge_existing_common_css(tmp_path: Path):
    css_path = tmp_path / 'src/main/webapp/css/common.css'
    css_path.parent.mkdir(parents=True, exist_ok=True)
    css_path.write_text('.legacy-rule { color: red; }\n', encoding='utf-8')

    view = tmp_path / 'src/main/webapp/WEB-INF/views/member/memberList.jsp'
    view.parent.mkdir(parents=True, exist_ok=True)
    view.write_text(
        '<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>\n'
        '<html><head><meta charset="UTF-8"/></head><body><h2>Member List</h2></body></html>\n',
        encoding='utf-8',
    )

    report = _patch_generated_jsp_assets(
        tmp_path,
        ['src/main/webapp/WEB-INF/views/member/memberList.jsp'],
        'Member',
        {'Member': DummySchema('member', 'CRUD', {'list': '/member/list.do'})},
    )

    merged_css = css_path.read_text(encoding='utf-8')
    patched_view = view.read_text(encoding='utf-8')
    assert '.legacy-rule { color: red; }' in merged_css
    assert 'AUTOPJ THEME START' in merged_css
    header_body = (tmp_path / report['header_jsp']).read_text(encoding='utf-8')
    assert report['css_web_url'] in header_body
    assert 'common/header.jsp' in patched_view


def test_jsp_design_assets_index_prefers_auth_route_when_present(tmp_path: Path):
    login_view = tmp_path / 'src/main/webapp/WEB-INF/views/login/login.jsp'
    login_view.parent.mkdir(parents=True, exist_ok=True)
    login_view.write_text(
        '<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>\n'
        '<html><head><meta charset="UTF-8"/></head><body><h2>Login</h2></body></html>\n',
        encoding='utf-8',
    )

    _patch_generated_jsp_assets(
        tmp_path,
        ['src/main/webapp/WEB-INF/views/login/login.jsp'],
        'Login',
        {
            'Member': DummySchema('member', 'CRUD', {'list': '/member/list.do'}),
            'Login': DummySchema('login', 'AUTH', {'login': '/login/login.do', 'process': '/login/process.do'}),
        },
    )

    index_body = (tmp_path / 'src/main/webapp/index.jsp').read_text(encoding='utf-8')
    assert '/login/login.do' in index_body
