from pathlib import Path

from app.io.execution_core_apply import apply_file_ops_with_execution_core
from app.ui.state import ProjectConfig


def test_main_project_broken_java_and_xml_are_rebuilt(tmp_path):
    project_root = tmp_path / "fulljsp"
    (project_root / "src/main/resources").mkdir(parents=True, exist_ok=True)
    (project_root / "pom.xml").write_text(
        "<project><modelVersion>4.0.0</modelVersion><groupId>x</groupId><artifactId>x</artifactId></project>",
        encoding="utf-8",
    )
    (project_root / "src/main/resources/application.properties").write_text("", encoding="utf-8")
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
            "path": "src/main/java/egovframework/fulljsp/config/MyBatisConfig.java",
            "content": """package egovframework.fulljsp.config;\n\n@Configuration\n@MapperScan(\"egovframework.fulljsp.**.mapper\")\npublic class MyBatisConfig {\n\n    @Bean\n    public SqlSessionFactoryBean sqlSessionFactoryBean() {\n        SqlSessionFactoryBean sqlSessionFactoryBean = new SqlSessionFactoryBean();\n        sqlSessionFactoryBean.setDataSource(dataSource());\n        sqlSessionFactoryBean.setMapperLocations(new PathMatcher().addPattern(\"classpath*:egovframework/mapper/**/*.xml\"));\n        return sqlSessionFactoryBean;\n    }\n}\n""",
        },
        {
            "path": "src/main/java/egovframework/fulljsp/member/service/MemberService.java",
            "content": """package egovframework.fulljsp.member.service;\n\nimport egovframework.fulljsp.member.mapper.MemberMapper;\n\npublic interface MemberService {\n    List<MemberVO> selectMemberList(MemberMapper param);\n    MemberVO selectMember(MemberMapper param);\n    int insertMember(MemberMapper param);\n    int updateMember(MemberMapper param);\n    int deleteMember(MemberMapper param);\n}\n""",
        },
        {
            "path": "src/main/java/egovframework/fulljsp/member/service/impl/MemberServiceImpl.java",
            "content": """package egovframework.fulljsp.member.service.impl;\n\n@Service\npublic class MemberServiceImpl {\n\n    @Resource\n    private MemberMapper memberMapper;\n\n    public List<MemberVO> selectMemberList() {\n        return memberMapper.selectMemberList();\n    }\n\n    public MemberVO selectMember(String memberId) {\n        return memberMapper.selectMember(memberId);\n    }\n\n    public int updateMember(MemberVO memberVO) {\n        return memberMapper.updateMember(memberVO);\n    }\n\n    public int deleteMember(String memberId) {\n        return memberMapper.deleteMember(memberId);\n    }\n}\n""",
        },
        {
            "path": "src/main/java/egovframework/fulljsp/member/service/mapper/MemberMapper.java",
            "content": """package egovframework.fulljsp.member.service.mapper;\n\nimport egovframework.fulljsp.member.service.vo.MemberVO;\nimport java.util.List;\n\n@Mapper\npublic interface MemberMapper {\n    List<MemberVO> selectMemberList(MemberVO memberVO);\n    MemberVO selectMember(MemberVO memberVO);\n    int insertMember(MemberVO memberVO);\n    int updateMember(MemberVO memberVO);\n    int deleteMember(MemberVO memberVO);\n}\n""",
        },
        {
            "path": "src/main/java/egovframework/fulljsp/member/service/vo/MemberVO.java",
            "content": """package egovframework.fulljsp.member.service.vo;\n\npublic class MemberVO {\n    private String memberId;\n    private String memberName;\n    private String email;\n    private String phone;\n\n    public String getMemberId() { return memberId; }\n    public void setMemberId(String memberId) { this.memberId = memberId; }\n    public String getMemberName() { return memberName; }\n    public void setMemberName(String memberName) { this.memberName = memberName; }\n    public String getEmail() { return email; }\n    public void setEmail(String email) { this.email = email; }\n    public String getPhone() { return phone; }\n    public void setPhone(String phone) { this.phone = phone; }\n}\n""",
        },
        {
            "path": "src/main/java/egovframework/fulljsp/member/web/MemberController.java",
            "content": """package egovframework.fulljsp.member.web;\n\nimport egovframework.fulljsp.member.service.MemberService;\nimport egovframework.fulljsp.member.vo.MemberVO;\nimport org.springframework.stereotype.Controller;\nimport org.springframework.ui.Model;\nimport org.springframework.web.bind.annotation.GetMapping;\nimport org.springframework.web.bind.annotation.ModelAttribute;\nimport org.springframework.web.bind.annotation.PostMapping;\nimport org.springframework.web.servlet.mvc.support.RedirectAttributes;\n\n@Controller\npublic class MemberController {\n\n    private final MemberService memberService;\n\n    public MemberController(MemberService memberService) {\n        this.memberService = memberService;\n    }\n\n    @GetMapping(\"/member/memberList.do\")\n    public String memberList(Model model) {\n        model.addAttribute(\"memberList\", memberService.getMemberList());\n        return \"member/memberList\";\n    }\n\n    @PostMapping(\"/member/memberSave.do\")\n    public String memberSave(@ModelAttribute MemberVO memberVO, RedirectAttributes redirectAttributes) {\n        memberService.saveMember(memberVO);\n        return \"redirect:/member/memberList.do\";\n    }\n}\n""",
        },
        {
            "path": "src/main/resources/egovframework/mapper/member/MemberMapper.xml",
            "content": """<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<beans xmlns=\"http://www.springframework.org/schema/beans\">\n    <sqlMap>\n        <select id=\"selectMemberList\">SELECT member_id, member_name, member_email, password FROM member</select>\n    </sqlMap>\n</beans>\n""",
        },
    ]

    cfg = ProjectConfig(project_name="fulljsp", frontend_key="jsp", database_key="sqlite")
    report = apply_file_ops_with_execution_core(broken_ops, project_root, cfg, overwrite=True)

    assert not report["errors"]

    config_path = project_root / "src/main/java/egovframework/fulljsp/config/MyBatisConfig.java"
    service_path = project_root / "src/main/java/egovframework/fulljsp/member/service/MemberService.java"
    impl_path = project_root / "src/main/java/egovframework/fulljsp/member/service/impl/MemberServiceImpl.java"
    mapper_java_path = project_root / "src/main/java/egovframework/fulljsp/member/service/mapper/MemberMapper.java"
    vo_path = project_root / "src/main/java/egovframework/fulljsp/member/service/vo/MemberVO.java"
    controller_path = project_root / "src/main/java/egovframework/fulljsp/member/web/MemberController.java"
    mapper_xml_path = project_root / "src/main/resources/egovframework/mapper/member/MemberMapper.xml"

    assert mapper_xml_path.exists()
    assert not (project_root / "src/main/resources/egovframework/mapper/fulljsp/member/MemberMapper.xml").exists()

    config = config_path.read_text(encoding="utf-8")
    assert "import javax.sql.DataSource;" in config
    assert "import org.springframework.context.ApplicationContext;" in config
    assert "@MapperScan(basePackages = \"egovframework.fulljsp\"" in config
    assert "SqlSessionFactoryBean" in config
    assert "setMapperLocations" in config
    assert 'applicationContext.getResources("classpath*:egovframework/mapper/**/*.xml")' in config
    assert "DriverManagerDataSource" not in config
    assert "spring.datasource.driver-class-name" not in config
    assert "MySQL-only" not in config
    assert "**.mapper" not in config
    assert "PathMatcher" not in config

    service = service_path.read_text(encoding="utf-8")
    assert "import java.util.List;" in service
    assert "import egovframework.fulljsp.member.service.vo.MemberVO;" in service
    assert "member.mapper.MemberMapper" not in service
    assert "selectMember(String memberId)" in service
    assert "deleteMember(String memberId)" in service

    impl = impl_path.read_text(encoding="utf-8")
    assert "implements MemberService" in impl
    assert "import egovframework.fulljsp.member.service.mapper.MemberMapper;" in impl
    assert "import egovframework.fulljsp.member.service.vo.MemberVO;" in impl
    assert "selectMember(String memberId)" in impl
    assert "insertMember(MemberVO vo)" in impl
    assert "updateMember(MemberVO vo)" in impl
    assert "deleteMember(String memberId)" in impl
    assert "@Resource" not in impl

    mapper_java = mapper_java_path.read_text(encoding="utf-8")
    assert "import org.apache.ibatis.annotations.Param;" in mapper_java
    assert "selectMember(@Param(\"memberId\") String memberId)" in mapper_java
    assert "deleteMember(@Param(\"memberId\") String memberId)" in mapper_java
    assert "selectMember(MemberVO memberVO)" not in mapper_java

    vo = vo_path.read_text(encoding="utf-8")
    assert "private String memberId;" in vo
    assert "private String memberName;" in vo
    assert "private String email;" in vo
    assert "private String phone;" in vo
    assert "memberEmail" not in vo
    assert "password" not in vo

    controller = controller_path.read_text(encoding="utf-8")
    lowered = controller.lower()
    assert "import egovframework.fulljsp.member.service.vo.membervo;" in lowered
    assert "member.vo.membervo" not in lowered
    assert '@getmapping("/list.do")' in lowered
    assert '@getmapping("/detail.do")' in lowered
    assert '@getmapping("/form.do")' in lowered
    assert '@postmapping("/save.do")' in lowered
    assert '@postmapping("/delete.do")' in lowered
    assert "getmemberlist" not in lowered
    assert "saveMember(memberVO)" not in controller

    mapper_xml = mapper_xml_path.read_text(encoding="utf-8")
    mapper_xml_lower = mapper_xml.lower()
    assert "<!doctype mapper" in mapper_xml_lower
    assert "<mapper namespace=\"egovframework.fulljsp.member.service.mapper.membermapper\">" in mapper_xml_lower
    assert "<beans" not in mapper_xml_lower
    assert "<sqlmap" not in mapper_xml_lower
    assert "memberemail" not in mapper_xml_lower
    assert "password" not in mapper_xml_lower
    assert '<resultMap id="MemberMap" type="egovframework.fulljsp.member.service.vo.MemberVO">' in mapper_xml
    assert 'property="memberName" column="member_name"' in mapper_xml
    assert 'property="email" column="email"' in mapper_xml
    assert 'property="phone" column="phone"' in mapper_xml
