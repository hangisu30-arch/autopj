from app.io.execution_core_apply import _normalize_out_path


def test_normalize_out_path_rewrites_tb_prefixed_admin_java_and_jsp_names_to_logical_entity():
    java_rel = _normalize_out_path(
        'java/controller/TbMemberAdminController.java',
        base_package='egovframework.test',
        preferred_entity='TbMemberAdmin',
        extra_text='테이블명: TB_MEMBER',
    )
    jsp_rel = _normalize_out_path(
        'jsp/tbMemberAdmin/tbMemberAdminList.jsp',
        base_package='egovframework.test',
        preferred_entity='TbMemberAdmin',
        extra_text='테이블명: TB_MEMBER',
    )
    assert java_rel.endswith('/memberAdmin/web/MemberAdminController.java')
    assert jsp_rel == 'src/main/webapp/WEB-INF/views/memberAdmin/memberAdminList.jsp'
