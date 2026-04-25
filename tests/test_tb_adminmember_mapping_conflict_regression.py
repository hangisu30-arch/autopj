from pathlib import Path

from app.validation.project_auto_repair import _repair_ambiguous_request_mapping


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def test_ambiguous_membership_mapping_prefers_canonical_non_tb_controller(tmp_path: Path):
    canonical = tmp_path / 'src/main/java/egovframework/test/adminMember/web/AdminMemberController.java'
    legacy = tmp_path / 'src/main/java/egovframework/test/tbAdminMember/web/TbAdminMemberController.java'
    _write(canonical, 'package egovframework.test.adminMember.web;\npublic class AdminMemberController {}\n')
    _write(legacy, 'package egovframework.test.tbAdminMember.web;\npublic class TbAdminMemberController {}\n')

    issue = {
        'message': 'Spring request mapping conflict detected',
        'details': {
            'message': 'Spring request mapping conflict detected',
            'route': '/adminMember/list.do',
            'routes': ['/adminMember/list.do'],
            'conflicting_path': 'src/main/java/egovframework/test/adminMember/web/AdminMemberController.java',
        },
    }

    assert _repair_ambiguous_request_mapping(legacy, issue, tmp_path) is True
    assert canonical.exists()
    assert not legacy.exists()
