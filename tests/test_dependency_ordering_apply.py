from app.io.execution_core_apply import _sort_file_ops_for_dependency_order


def test_dependency_order_prioritizes_backend_core_types():
    file_ops = [
        {"path": "src/main/java/egovframework/demo/member/web/MemberController.java"},
        {"path": "src/main/java/egovframework/demo/member/service/MemberService.java"},
        {"path": "src/main/resources/egovframework/mapper/member/MemberMapper.xml"},
        {"path": "src/main/java/egovframework/demo/member/service/vo/MemberVO.java"},
        {"path": "src/main/java/egovframework/demo/member/service/mapper/MemberMapper.java"},
        {"path": "src/main/java/egovframework/demo/member/service/impl/MemberServiceImpl.java"},
        {"path": "src/main/webapp/WEB-INF/views/member/memberList.jsp"},
    ]

    ordered = _sort_file_ops_for_dependency_order(file_ops)
    paths = [item["path"] for item in ordered]

    assert paths[:6] == [
        "src/main/java/egovframework/demo/member/service/vo/MemberVO.java",
        "src/main/java/egovframework/demo/member/service/mapper/MemberMapper.java",
        "src/main/resources/egovframework/mapper/member/MemberMapper.xml",
        "src/main/java/egovframework/demo/member/service/MemberService.java",
        "src/main/java/egovframework/demo/member/service/impl/MemberServiceImpl.java",
        "src/main/java/egovframework/demo/member/web/MemberController.java",
    ]
