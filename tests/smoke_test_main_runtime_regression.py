from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.io.execution_core_apply import apply_file_ops_with_execution_core
from app.ui.state import ProjectConfig


def _sample_ops() -> list[dict[str, str]]:
    return [
        {
            "path": "src/main/java/egovframework/example/EgovBootApplication.java",
            "content": '''package egovframework.example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EgovBootApplication {
    public static void main(String[] args) {
        SpringApplication.run(EgovBootApplication.class, args);
    }
}
''',
        },
        {
            "path": "src/main/java/egovframework/fulljsp/EgovBootApplication.java",
            "content": '''package egovframework.fulljsp;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

@SpringBootApplication(scanBasePackages = {"egovframework.fulljsp"})
@EnableWebMvc
public class EgovBootApplication {
    public static void main(String[] args) {
        SpringApplication.run(EgovBootApplication.class, args);
    }
}
''',
        },
        {
            "path": "src/main/java/egovframework/fulljsp/config/MyBatisConfig.java",
            "content": '''package egovframework.fulljsp.config;

@Configuration
@MapperScan("egovframework.fulljsp.**.mapper")
public class MyBatisConfig {

    @Bean
    public SqlSessionFactoryBean sqlSessionFactoryBean() {
        SqlSessionFactoryBean sqlSessionFactoryBean = new SqlSessionFactoryBean();
        sqlSessionFactoryBean.setDataSource(dataSource());
        sqlSessionFactoryBean.setMapperLocations(new PathMatcher().addPattern("classpath*:egovframework/mapper/**/*.xml"));
        return sqlSessionFactoryBean;
    }
}
''',
        },
        {
            "path": "src/main/java/egovframework/fulljsp/member/service/MemberService.java",
            "content": '''package egovframework.fulljsp.member.service;

import egovframework.fulljsp.member.mapper.MemberMapper;

public interface MemberService {
    List<MemberVO> selectMemberList(MemberMapper param);
}
''',
        },
        {
            "path": "src/main/java/egovframework/fulljsp/member/service/impl/MemberServiceImpl.java",
            "content": '''package egovframework.fulljsp.member.service.impl;

import egovframework.fulljsp.member.service.MemberService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

@Service
public class MemberServiceImpl implements MemberService {
    private final MemberMapper memberMapper;
    @Autowired
    public MemberServiceImpl(MemberMapper memberMapper) {
        this.memberMapper = memberMapper;
    }
}
''',
        },
        {
            "path": "src/main/java/egovframework/fulljsp/member/service/mapper/MemberMapper.java",
            "content": '''package egovframework.fulljsp.member.service.mapper;

import egovframework.fulljsp.member.service.vo.MemberVO;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface MemberMapper {
    List<MemberVO> selectMemberList(MemberVO vo);
    MemberVO selectMember(MemberVO vo);
}
''',
        },
        {
            "path": "src/main/java/egovframework/fulljsp/member/service/vo/MemberVO.java",
            "content": '''package egovframework.fulljsp.member.service.vo;

public class MemberVO {
    private String memberId;
    private String memberName;
    private String email;
}
''',
        },
        {
            "path": "src/main/java/egovframework/fulljsp/member/web/MemberController.java",
            "content": '''package egovframework.fulljsp.member.web;

import egovframework.fulljsp.member.service.MemberService;
import egovframework.fulljsp.member.vo.MemberVO;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;

@Controller
public class MemberController {
    @GetMapping("/member/memberList.do")
    public String memberList(Model model) {
        return "member/memberList";
    }

    @PostMapping("/member/saveMember.do")
    public String saveMember(@ModelAttribute MemberVO memberVO) {
        return "redirect:/member/memberList.do";
    }
}
''',
        },
        {
            "path": "src/main/resources/application.properties",
            "content": '''server.port=8080
spring.mvc.view.prefix=/WEB-INF/views/
spring.mvc.view.suffix=.jsp
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.url=jdbc:h2:mem:egov-auto-db;MODE=MySQL;DB_CLOSE_DELAY=-1
spring.datasource.username=root
spring.datasource.password=1111
mybatis.mapper-locations=classpath*:egovframework/mapper/**/*.xml
mybatis.type-aliases-package=egovframework.fulljsp
''',
        },
        {
            "path": "src/main/resources/egovframework/mapper/member/MemberMapper.xml",
            "content": '''<beans xmlns="http://www.springframework.org/schema/beans">
    <bean id="memberMapper" class="egovframework.fulljsp.member.service.mapper.MemberMapper"/>
    <sqlMap>
        <select id="selectMemberList">SELECT * FROM MEMBER</select>
    </sqlMap>
</beans>
''',
        },
        {
            "path": "src/main/webapp/WEB-INF/views/member/memberList.jsp",
            "content": '''<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<!DOCTYPE html>
<html><body>
<a href="memberDetail.jsp?memberId=${member.memberId}">detail</a>
<a href="memberRegistration.jsp">register</a>
</body></html>
''',
        },
        {
            "path": "src/main/webapp/WEB-INF/views/member/memberDetail.jsp",
            "content": '''<%@ page language="java" contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<jsp:useBean id="member" type="egovframework.com.egovframework.com.util.MemberVO" scope="request"/>
<!DOCTYPE html>
<html><body>
<a href="memberList.jsp">List</a>
</body></html>
''',
        },
        {
            "path": "src/main/webapp/WEB-INF/views/member/memberForm.jsp",
            "content": '''<%@ page language="java" contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<jsp:useBean id="memberVO" class="com.example.MemberVO" scope="request"></jsp:useBean>
<form action="/member/saveMember.do" method="post"></form>
''',
        },
    ]


def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        cfg = ProjectConfig(
            project_name="fulljsp",
            backend_key="egov_spring",
            frontend_key="jsp",
            database_key="mysql",
            db_name="sampledb",
            db_login_id="tester",
            db_password="secret",
        )
        report = apply_file_ops_with_execution_core(_sample_ops(), project_root, cfg, overwrite=True)
        assert not report["errors"], report["errors"]

        app_props = (project_root / "src/main/resources/application.properties").read_text(encoding="utf-8")
        assert "com.mysql.cj.jdbc.Driver" in app_props
        assert "jdbc:h2:mem" not in app_props

        mybatis = (project_root / "src/main/java/egovframework/fulljsp/config/MyBatisConfig.java").read_text(encoding="utf-8")
        assert "@Configuration" in mybatis
        assert "setMapperLocations" in mybatis
        assert "**.mapper" not in mybatis

        mapper_xml = (project_root / "src/main/resources/egovframework/mapper/member/MemberMapper.xml").read_text(encoding="utf-8")
        assert "<beans" not in mapper_xml.lower()
        assert "<sqlmap" not in mapper_xml.lower()
        assert "<!DOCTYPE mapper" in mapper_xml
        assert "password" not in mapper_xml

        member_vo = (project_root / "src/main/java/egovframework/fulljsp/member/service/vo/MemberVO.java").read_text(encoding="utf-8")
        assert "private String email;" in member_vo
        assert "password" not in member_vo

        list_jsp = (project_root / "src/main/webapp/WEB-INF/views/member/memberList.jsp").read_text(encoding="utf-8")
        assert ".jsp" not in list_jsp
        assert "/member/detail.do" in list_jsp

        boot_files = sorted((project_root / "src/main/java").rglob("EgovBootApplication.java"))
        assert len(boot_files) == 1, [p.as_posix() for p in boot_files]
        assert boot_files[0].as_posix().endswith("egovframework/fulljsp/EgovBootApplication.java")

        print("OK: main regression inputs are repaired into deterministic JSP runtime outputs")


if __name__ == "__main__":
    main()
