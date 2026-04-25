from pathlib import Path

from execution_core.builtin_crud import _extract_explicit_requirement_field_entries
from app.validation.generated_project_validator import _scan_mapper_table_vo_alignment


def test_explicit_contract_ignores_schema_sql_filename_and_metadata_columns():
    text = '''
테이블명: tb_member
테이블 코멘트: 회원 정보 관리 테이블

컬럼정의:
- schema.sql
- schema_name
- member_id / 회원 ID / varchar(64) / PK
- member_name / 회원명 / varchar(100) / 필수
- reg_dt / 등록일시 / datetime
'''
    entries = _extract_explicit_requirement_field_entries(text)
    cols = [str(item.get('col') or '').strip().lower() for item in entries]
    assert 'schema' not in cols
    assert 'schema_name' not in cols
    assert cols == ['member_id', 'member_name', 'reg_dt']


def test_validator_flags_schema_generation_metadata_columns(tmp_path: Path):
    mapper = tmp_path / 'src/main/resources/egovframework/mapper/member/MemberMapper.xml'
    mapper.parent.mkdir(parents=True, exist_ok=True)
    mapper.write_text(
        '''<?xml version="1.0" encoding="UTF-8"?>
<mapper namespace="egovframework.test.member.service.mapper.MemberMapper">
    <insert id="insertMember">
        INSERT INTO tb_member (member_name, reg_dt, use_yn)
        VALUES (#{memberName}, #{regDt}, #{useYn})
    </insert>
</mapper>
''',
        encoding='utf-8',
    )
    (tmp_path / 'src/main/java').mkdir(parents=True, exist_ok=True)
    schema = tmp_path / 'src/main/resources/schema.sql'
    schema.parent.mkdir(parents=True, exist_ok=True)
    schema.write_text(
        '''DROP TABLE IF EXISTS `tb_member`;
CREATE TABLE IF NOT EXISTS tb_member (
    schema_name VARCHAR(64) NOT NULL PRIMARY KEY COMMENT '.sql'
) COMMENT='회원 정보 관리 테이블';
''',
        encoding='utf-8',
    )

    issues = _scan_mapper_table_vo_alignment(tmp_path)
    metadata_issues = [item for item in issues if item.get('type') == 'schema_generation_metadata_column']
    assert metadata_issues, issues
    assert metadata_issues[0].get('details', {}).get('metadata_columns') == ['schema_name']
