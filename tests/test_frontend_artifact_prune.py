from pathlib import Path

from app.validation.post_generation_repair import _prune_unnecessary_frontend_artifacts


def _write(path: Path, body: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_prune_unreferenced_jsp_views_removes_entry_and_alias_views(tmp_path: Path) -> None:
    _write(
        tmp_path / 'src/main/java/egovframework/test/tbMember/web/TbMemberController.java',
        'package egovframework.test.tbMember.web;\n'
        'public class TbMemberController {\n'
        '  public String list(){ return "tbMember/tbMemberList"; }\n'
        '  public String form(){ return "tbMember/tbMemberForm"; }\n'
        '}\n',
    )
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/tbMember/tbMemberList.jsp', 'ok')
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/tbMember/tbMemberForm.jsp', 'ok')
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/member/memberList.jsp', 'duplicate alias')
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/member/memberDetail.jsp', 'duplicate alias')
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/index/indexList.jsp', 'entry only')
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/common/header.jsp', 'common')
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/login/login.jsp', 'login')

    manifest = {
        'src/main/webapp/WEB-INF/views/tbMember/tbMemberList.jsp': {},
        'src/main/webapp/WEB-INF/views/tbMember/tbMemberForm.jsp': {},
        'src/main/webapp/WEB-INF/views/login/login.jsp': {},
    }

    report = _prune_unnecessary_frontend_artifacts(tmp_path, manifest, 'jsp')

    removed = set(report['removed'])
    assert 'src/main/webapp/WEB-INF/views/member/memberList.jsp' in removed
    assert 'src/main/webapp/WEB-INF/views/member/memberDetail.jsp' in removed
    assert 'src/main/webapp/WEB-INF/views/index/indexList.jsp' in removed
    assert (tmp_path / 'src/main/webapp/WEB-INF/views/tbMember/tbMemberList.jsp').exists()
    assert (tmp_path / 'src/main/webapp/WEB-INF/views/tbMember/tbMemberForm.jsp').exists()
    assert (tmp_path / 'src/main/webapp/WEB-INF/views/common/header.jsp').exists()
    assert (tmp_path / 'src/main/webapp/WEB-INF/views/login/login.jsp').exists()


def test_prune_unreferenced_react_pages_keeps_manifest_and_route_references(tmp_path: Path) -> None:
    _write(
        tmp_path / 'src/App.jsx',
        "import TbMemberListPage from './pages/tbMember/TbMemberListPage';\n"
        'export default function App(){ return <TbMemberListPage />; }\n',
    )
    _write(tmp_path / 'src/pages/tbMember/TbMemberListPage.jsx', 'export default function TbMemberListPage(){ return null; }')
    _write(tmp_path / 'src/pages/member/MemberListPage.jsx', 'export default function MemberListPage(){ return null; }')
    _write(tmp_path / 'src/pages/index/IndexListPage.jsx', 'export default function IndexListPage(){ return null; }')

    manifest = {
        'src/pages/tbMember/TbMemberListPage.jsx': {},
    }

    report = _prune_unnecessary_frontend_artifacts(tmp_path, manifest, 'react')

    removed = set(report['removed'])
    assert 'src/pages/member/MemberListPage.jsx' in removed
    assert 'src/pages/index/IndexListPage.jsx' in removed
    assert (tmp_path / 'src/pages/tbMember/TbMemberListPage.jsx').exists()
