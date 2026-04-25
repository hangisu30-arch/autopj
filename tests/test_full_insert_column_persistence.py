from execution_core.builtin_crud import builtin_file, schema_for


def test_mapper_insert_covers_all_real_columns_and_service_prepares_defaults():
    schema = schema_for(
        "User",
        inferred_fields=[
            ("userId", "user_id", "String"),
            ("loginId", "login_id", "String"),
            ("userName", "user_name", "String"),
            ("roleCd", "role_cd", "String"),
            ("useYn", "use_yn", "String"),
            ("regDt", "reg_dt", "String"),
            ("updDt", "upd_dt", "String"),
        ],
        table="tb_user",
        strict_fields=True,
        field_nullable={
            "user_id": False,
            "login_id": False,
            "user_name": False,
            "role_cd": False,
            "use_yn": False,
            "reg_dt": False,
            "upd_dt": False,
        },
    )

    mapper = builtin_file("mapper/UserMapper.xml", "egovframework.test", schema)
    service_impl = builtin_file("java/service/impl/UserServiceImpl.java", "egovframework.test", schema)

    assert mapper is not None
    assert service_impl is not None
    assert "INSERT INTO tb_user (user_id, login_id, user_name, role_cd, use_yn, reg_dt, upd_dt)" in mapper
    assert "VALUES (#{userId}, #{loginId}, #{userName}, #{roleCd}, #{useYn}, STR_TO_DATE(NULLIF(REPLACE(#{regDt}, 'T', ' '), ''), '%Y-%m-%dT%H:%i'), STR_TO_DATE(NULLIF(REPLACE(#{updDt}, 'T', ' '), ''), '%Y-%m-%dT%H:%i'))" in mapper
    assert 'vo.setUserId(UUID.randomUUID().toString().replace("-", ""));' in service_impl
    assert 'vo.setRoleCd("USER");' in service_impl
    assert 'vo.setUseYn("Y");' in service_impl
    assert 'vo.setRegDt(new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss").format(new Date()));' in service_impl
    assert 'vo.setUpdDt(new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss").format(new Date()));' in service_impl


def test_update_merges_missing_non_editable_columns_before_persisting():
    schema = schema_for(
        "User",
        inferred_fields=[
            ("userId", "user_id", "String"),
            ("loginId", "login_id", "String"),
            ("userName", "user_name", "String"),
            ("roleCd", "role_cd", "String"),
            ("useYn", "use_yn", "String"),
            ("updDt", "upd_dt", "String"),
        ],
        table="tb_user",
        strict_fields=True,
    )

    service_impl = builtin_file("java/service/impl/UserServiceImpl.java", "egovframework.test", schema)
    assert service_impl is not None
    assert '_mergeMissingPersistenceFields(existing, vo);' in service_impl
    assert 'if (target.getRoleCd() == null || target.getRoleCd().trim().isEmpty()) {' in service_impl
    assert 'target.setRoleCd(source.getRoleCd());' in service_impl
    assert 'vo.setUpdDt(new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss").format(new Date()));' in service_impl
