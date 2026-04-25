from pathlib import Path

from app.io.execution_core_apply import apply_file_ops_with_execution_core
from app.ui.state import ProjectConfig


def test_react_rest_controller_is_rebuilt_with_correct_imports_and_package(tmp_path):
    project_root = tmp_path / "reacttest"
    (project_root / "src/main/resources").mkdir(parents=True, exist_ok=True)
    (project_root / "pom.xml").write_text(
        "<project><modelVersion>4.0.0</modelVersion><groupId>x</groupId><artifactId>x</artifactId></project>",
        encoding="utf-8",
    )
    (project_root / "src/main/resources/application.properties").write_text(
        "spring.datasource.url=jdbc:h2:file:./reacttest\n", encoding="utf-8"
    )
    (project_root / "src/main/java/egovframework/example").mkdir(parents=True, exist_ok=True)
    (project_root / "src/main/java/egovframework/example/EgovBootApplication.java").write_text(
        "package egovframework.example;\n\n"
        "import org.springframework.boot.SpringApplication;\n"
        "import org.springframework.boot.autoconfigure.SpringBootApplication;\n\n"
        "@SpringBootApplication\n"
        "public class EgovBootApplication {\n"
        "    public static void main(String[] args) {\n"
        "        SpringApplication.run(EgovBootApplication.class, args);\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )

    broken_ops = [
        {
            "path": "src/main/java/egovframework/reacttest/member/service/MemberService.java",
            "content": "package egovframework.reacttest.member.service;\n\npublic interface MemberService {}\n",
        },
        {
            "path": "src/main/java/egovframework/reacttest/member/service/impl/MemberServiceImpl.java",
            "content": "package egovframework.reacttest.member.service.impl;\n\npublic class MemberServiceImpl {}\n",
        },
        {
            "path": "src/main/java/egovframework/reacttest/member/service/mapper/MemberMapper.java",
            "content": "package egovframework.reacttest.member.service.mapper;\n\npublic interface MemberMapper {}\n",
        },
        {
            "path": "src/main/java/egovframework/reacttest/member/service/vo/MemberVO.java",
            "content": "package egovframework.reacttest.member.service.vo;\n\npublic class MemberVO {\n"
                       "    private String memberId;\n"
                       "    private String memberName;\n"
                       "    private String email;\n"
                       "    public String getMemberId() { return memberId; }\n"
                       "    public void setMemberId(String memberId) { this.memberId = memberId; }\n"
                       "    public String getMemberName() { return memberName; }\n"
                       "    public void setMemberName(String memberName) { this.memberName = memberName; }\n"
                       "    public String getEmail() { return email; }\n"
                       "    public void setEmail(String email) { this.email = email; }\n"
                       "}\n",
        },
        {
            "path": "src/main/java/egovframework/reacttest/memberRest/web/MemberRestController.java",
            "content": "package egovframework.reacttest.memberRest.web;\n\n"
                       "import egovframework.reacttest.memberRest.service.MemberRestService;\n"
                       "import egovframework.reacttest.memberRest.service.vo.MemberRestVO;\n"
                       "import org.springframework.stereotype.Controller;\n"
                       "public class MemberRestController {}\n",
        },
        {
            "path": "src/main/resources/egovframework/mapper/member/MemberMapper.xml",
            "content": "<mapper namespace=\"egovframework.reacttest.member.service.mapper.MemberMapper\"></mapper>",
        },
    ]

    cfg = ProjectConfig(project_name="reacttest", frontend_key="react", database_key="h2")
    report = apply_file_ops_with_execution_core(broken_ops, project_root, cfg, overwrite=True)
    assert not report["errors"]

    controller_path = project_root / "src/main/java/egovframework/reacttest/member/web/MemberRestController.java"
    assert controller_path.exists()
    controller = controller_path.read_text(encoding="utf-8")
    lowered = controller.lower()
    assert "package egovframework.reacttest.member.web;" in controller
    assert "import egovframework.reacttest.member.service.memberservice;" in lowered
    assert "import egovframework.reacttest.member.service.vo.membervo;" in lowered
    assert "memberrest.service" not in lowered
    assert "@crossorigin" in lowered
    assert "@restcontroller" in lowered
    assert '@requestmapping("/api/member")' in lowered
    assert 'list<membervo> list()' in lowered
    assert 'membervo detail(@pathvariable("memberid") string memberid)' in lowered
    assert '@postmapping' in lowered
    assert '@putmapping("/{memberid}")' in lowered
    assert '@deletemapping("/{memberid}")' in lowered
    assert 'return "memberrest/memberrestlist"' not in controller

    env_dev = (project_root / "frontend/react/.env.development").read_text(encoding="utf-8")
    assert env_dev.strip() == "VITE_API_BASE_URL="

    props = (project_root / "src/main/resources/application.properties").read_text(encoding="utf-8")
    assert "AUTO_SERVER=TRUE" not in props
    assert "DB_CLOSE_ON_EXIT=FALSE" in props
    assert "spring.datasource.hikari.maximum-pool-size=1" in props
