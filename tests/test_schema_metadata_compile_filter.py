from pathlib import Path

from app.validation.generated_project_validator import _sanitize_alignment_columns as validator_sanitize
from app.validation.project_auto_repair import _sanitize_alignment_columns as repair_sanitize, _sync_schema_table_from_mapper


def test_alignment_sanitizers_drop_compile_metadata_column():
    mapper = ['user_id', 'compile', 'login_id']
    schema = ['user_id', 'login_id']
    vo = ['user_id', 'login_id']

    assert validator_sanitize(mapper, schema, vo) == ['user_id', 'login_id']
    assert repair_sanitize(mapper, schema, vo) == ['user_id', 'login_id']


def test_sync_schema_table_from_mapper_excludes_compile_metadata_column(tmp_path: Path):
    mapper = tmp_path / 'src/main/resources/egovframework/mapper/user/UserMapper.xml'
    mapper.parent.mkdir(parents=True, exist_ok=True)
    mapper.write_text(
        '''<!DOCTYPE mapper
  PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN"
  "http://mybatis.org/dtd/mybatis-3-mapper.dtd">
<mapper namespace="egovframework.test.user.service.mapper.UserMapper">
  <insert id="insertUser" parameterType="egovframework.test.user.service.vo.UserVO">
    INSERT INTO tb_user (
      user_id,
      compile,
      login_id
    ) VALUES (
      #{userId},
      #{compile},
      #{loginId}
    )
  </insert>
</mapper>
''',
        encoding='utf-8',
    )
    schema = tmp_path / 'src/main/resources/schema.sql'
    schema.parent.mkdir(parents=True, exist_ok=True)
    schema.write_text(
        "CREATE TABLE IF NOT EXISTS tb_user (\n"
        "    user_id VARCHAR(255) COMMENT '사용자 ID',\n"
        "    compile VARCHAR(255) COMMENT 'compile 컬럼',\n"
        "    login_id VARCHAR(255) COMMENT '로그인 ID'\n"
        ");\n",
        encoding='utf-8',
    )

    issue = {'details': {'table': 'tb_user', 'mapper_columns': ['user_id', 'compile', 'login_id']}}
    assert _sync_schema_table_from_mapper(mapper, issue, tmp_path)

    body = schema.read_text(encoding='utf-8').lower()
    assert 'compile varchar' not in body
    assert 'user_id varchar' in body
    assert 'login_id varchar' in body
