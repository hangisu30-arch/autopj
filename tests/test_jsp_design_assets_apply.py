from pathlib import Path

from app.io.execution_core_apply import _patch_generated_jsp_assets


def test_jsp_design_assets_create_common_css_and_index(tmp_path: Path):
    view = tmp_path / 'src/main/webapp/WEB-INF/views/member/memberList.jsp'
    view.parent.mkdir(parents=True, exist_ok=True)
    view.write_text(
        '<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>\n'
        '<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>\n'
        '<html><head><meta charset="UTF-8"/></head><body><h2>Member List</h2></body></html>\n',
        encoding='utf-8',
    )

    class Schema:
        entity_var = 'member'
        feature_kind = 'CRUD'
        routes = {'list': '/member/list.do'}

    report = _patch_generated_jsp_assets(tmp_path, ['src/main/webapp/WEB-INF/views/member/memberList.jsp'], 'Member', {'Member': Schema()})
    common_css = tmp_path / report['common_css']
    index_jsp = tmp_path / report['index_jsp']
    leftnav_jsp = tmp_path / report['leftnav_jsp']
    header_jsp = tmp_path / report['header_jsp']
    patched = view.read_text(encoding='utf-8')

    assert common_css.exists()
    assert 'AUTOPJ THEME START' in common_css.read_text(encoding='utf-8')
    assert index_jsp.exists()
    assert leftnav_jsp.exists()
    assert header_jsp.exists()
    assert '/member/list.do' in index_jsp.read_text(encoding='utf-8')
    assert 'autopj-leftnav' in leftnav_jsp.read_text(encoding='utf-8')
    assert 'autopj-header__nav' in header_jsp.read_text(encoding='utf-8')
    assert 'common/leftNav.jsp' in patched
    assert 'autopj-generated' in patched
    assert report['css_web_url'] in patched
