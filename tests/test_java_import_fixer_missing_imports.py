from pathlib import Path

from app.ui.java_import_fixer import build_class_index, fix_imports_in_java_text


def test_fix_imports_adds_missing_project_and_standard_imports(tmp_path: Path):
    src = tmp_path / 'src/main/java'
    base = src / 'egovframework/demo/member'
    (base / 'service').mkdir(parents=True, exist_ok=True)
    (base / 'service/mapper').mkdir(parents=True, exist_ok=True)
    (base / 'service/vo').mkdir(parents=True, exist_ok=True)

    (base / 'service/MemberService.java').write_text(
        'package egovframework.demo.member.service;\n\npublic interface MemberService {}\n',
        encoding='utf-8',
    )
    (base / 'service/mapper/MemberMapper.java').write_text(
        'package egovframework.demo.member.service.mapper;\n\npublic interface MemberMapper {}\n',
        encoding='utf-8',
    )
    (base / 'service/vo/MemberVO.java').write_text(
        'package egovframework.demo.member.service.vo;\n\npublic class MemberVO {}\n',
        encoding='utf-8',
    )

    index = build_class_index(src)
    java = '''package egovframework.demo.member.service.impl;

@Service
public class MemberServiceImpl implements MemberService {
    private final MemberMapper memberMapper;

    public List<MemberVO> selectMembers() {
        return new ArrayList<>();
    }
}
'''
    fixed, changed = fix_imports_in_java_text(java, index)
    assert changed is True
    assert 'import java.util.List;' in fixed
    assert 'import java.util.ArrayList;' in fixed
    assert 'import org.springframework.stereotype.Service;' in fixed
    assert 'import egovframework.demo.member.service.MemberService;' in fixed
    assert 'import egovframework.demo.member.service.mapper.MemberMapper;' in fixed
    assert 'import egovframework.demo.member.service.vo.MemberVO;' in fixed
