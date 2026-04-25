from __future__ import annotations

import sys
import tempfile
import types
from pathlib import Path
from types import SimpleNamespace

ollama_client = types.ModuleType("execution_core.ollama_client")
ollama_client.call_ollama = lambda prompt, config: ""
sys.modules["execution_core.ollama_client"] = ollama_client

logger_mod = types.ModuleType("execution_core.logger")
logger_mod.log = lambda message: None
sys.modules["execution_core.logger"] = logger_mod

builtin_mod = types.ModuleType("execution_core.builtin_crud")

def infer_schema_from_plan(plan):
    return SimpleNamespace(entity="Member", entity_var="member", feature_kind="crud")

def infer_entity_from_plan(plan):
    return "Member"

def builtin_file(logical_path, effective_base, schema):
    if logical_path == "java/service/vo/MemberVO.java":
        return f'''package {effective_base}.service.vo;

public class MemberVO {{
    private String memberId;

    public String getMemberId() {{
        return memberId;
    }}

    public void setMemberId(String memberId) {{
        this.memberId = memberId;
    }}
}}
'''
    if logical_path == "java/service/MemberService.java":
        return f'''package {effective_base}.service;

import java.util.List;

import {effective_base}.service.vo.MemberVO;

public interface MemberService {{
    List<MemberVO> selectMemberList(MemberVO memberVO);
}}
'''
    if logical_path == "java/service/impl/MemberServiceImpl.java":
        return f'''package {effective_base}.service.impl;

import java.util.List;

import org.springframework.stereotype.Service;

import {effective_base}.service.MemberService;
import {effective_base}.service.mapper.MemberMapper;
import {effective_base}.service.vo.MemberVO;

@Service
public class MemberServiceImpl implements MemberService {{
    private final MemberMapper memberMapper;

    public MemberServiceImpl(MemberMapper memberMapper) {{
        this.memberMapper = memberMapper;
    }}

    @Override
    public List<MemberVO> selectMemberList(MemberVO memberVO) {{
        return memberMapper.selectMemberList(memberVO);
    }}
}}
'''
    if logical_path == "java/service/mapper/MemberMapper.java":
        return f'''package {effective_base}.service.mapper;

import java.util.List;

import org.apache.ibatis.annotations.Mapper;

import {effective_base}.service.vo.MemberVO;

@Mapper
public interface MemberMapper {{
    List<MemberVO> selectMemberList(MemberVO memberVO);
}}
'''
    if logical_path == "mapper/member/MemberMapper.xml":
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE mapper PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN" "http://mybatis.org/dtd/mybatis-3-mapper.dtd">
<mapper namespace="{effective_base}.service.mapper.MemberMapper">
  <select id="selectMemberList" parameterType="{effective_base}.service.vo.MemberVO" resultType="{effective_base}.service.vo.MemberVO">
    SELECT 1
  </select>
</mapper>
'''
    if logical_path == "java/config/MyBatisConfig.java":
        return f'''package {effective_base}.config;

import javax.sql.DataSource;

import org.apache.ibatis.session.SqlSessionFactory;
import org.mybatis.spring.SqlSessionFactoryBean;
import org.mybatis.spring.annotation.MapperScan;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@MapperScan(basePackages = "{effective_base}.service.mapper")
public class MyBatisConfig {{
    @Bean
    public SqlSessionFactory sqlSessionFactory(DataSource dataSource, ApplicationContext applicationContext) throws Exception {{
        SqlSessionFactoryBean factoryBean = new SqlSessionFactoryBean();
        factoryBean.setDataSource(dataSource);
        factoryBean.setMapperLocations(applicationContext.getResources("classpath*:egovframework/mapper/**/*.xml"));
        return factoryBean.getObject();
    }}
}}
'''
    if logical_path == "java/controller/MemberController.java":
        return f'''package {effective_base}.web;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;

@Controller
@RequestMapping("/member")
public class MemberController {{
    @GetMapping("/memberList.do")
    public String memberList(Model model) {{
        return "member/memberList";
    }}

    @GetMapping("/memberDetail.do")
    public String memberDetail(Model model) {{
        return "member/memberDetail";
    }}

    @PostMapping("/save.do")
    public String save() {{
        return "redirect:/member/memberList.do";
    }}
}}
'''
    if logical_path == "jsp/memberList.jsp":
        return '<%@ page contentType="text/html; charset=UTF-8" %>\n<html><body>list</body></html>\n'
    if logical_path == "jsp/memberDetail.jsp":
        return '<%@ page contentType="text/html; charset=UTF-8" %>\n<html><body>detail</body></html>\n'
    if logical_path == "jsp/memberForm.jsp":
        return '<%@ page contentType="text/html; charset=UTF-8" %>\n<html><body>form</body></html>\n'
    if logical_path == "index.jsp":
        return '<%@ page contentType="text/html; charset=UTF-8" %>\n<html><body>index</body></html>\n'
    return None

def ddl(schema):
    return "CREATE TABLE member (member_id VARCHAR(20) PRIMARY KEY);"

builtin_mod.infer_schema_from_plan = infer_schema_from_plan
builtin_mod.infer_entity_from_plan = infer_entity_from_plan
builtin_mod.builtin_file = builtin_file
builtin_mod.ddl = ddl
sys.modules["execution_core.builtin_crud"] = builtin_mod

feature_rules = types.ModuleType("execution_core.feature_rules")
feature_rules.classify_feature_kind = lambda task: "crud"
feature_rules.is_auth_kind = lambda kind: False
feature_rules.is_read_only_kind = lambda kind: False
sys.modules["execution_core.feature_rules"] = feature_rules

from execution_core import generator


def _long_controller() -> str:
    methods = []
    for idx in range(1, 8):
        methods.append(f'''
    @GetMapping("/m{idx}.do")
    public String m{idx}(Model model) throws Exception {{
        model.addAttribute("v{idx}", "x");
        return "member/memberList";
    }}
''')
    return f'''package egovframework.demo.member.web;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;

@Controller
@RequestMapping("/member")
public class MemberController {{
{''.join(methods)}
}}
'''


def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        class FakeProfile:
            def __init__(self, project_root: Path):
                self.context = SimpleNamespace(
                    overwrite=True,
                    dry_run=False,
                    base_package="egovframework.demo",
                    config={},
                    frontend="jsp",
                )
                self.project_root = project_root

            def resolve_path_for_base(self, logical_path: str, effective_base: str) -> Path:
                if logical_path.startswith("java/controller/"):
                    return self.project_root / "src/main/java" / Path(effective_base.replace(".", "/")) / "web" / logical_path.split("/")[-1]
                if logical_path.startswith("java/service/vo/"):
                    return self.project_root / "src/main/java" / Path(effective_base.replace(".", "/")) / "service/vo" / logical_path.split("/")[-1]
                if logical_path.startswith("java/service/mapper/"):
                    return self.project_root / "src/main/java" / Path(effective_base.replace(".", "/")) / "service/mapper" / logical_path.split("/")[-1]
                if logical_path.startswith("java/service/impl/"):
                    return self.project_root / "src/main/java" / Path(effective_base.replace(".", "/")) / "service/impl" / logical_path.split("/")[-1]
                if logical_path.startswith("java/service/"):
                    return self.project_root / "src/main/java" / Path(effective_base.replace(".", "/")) / "service" / logical_path.split("/")[-1]
                if logical_path.startswith("java/config/"):
                    return self.project_root / "src/main/java" / Path(effective_base.replace(".", "/")) / "config" / logical_path.split("/")[-1]
                if logical_path.startswith("mapper/"):
                    return self.project_root / "src/main/resources/egovframework/mapper" / Path(logical_path[len("mapper/"):])
                if logical_path.startswith("jsp/"):
                    return self.project_root / "src/main/webapp/WEB-INF/views" / Path(logical_path[len("jsp/"):])
                if logical_path == "index.jsp":
                    return self.project_root / "src/main/webapp/index.jsp"
                return self.project_root / logical_path

            def post_process(self, real_path: Path, content: str) -> str:
                return content

            def build_prompt(self, task: dict) -> str:
                return "ignored"

        profile = FakeProfile(root)
        plan = {
            "frontend": "jsp",
            "tasks": [{"path": "java/controller/MemberController.java", "purpose": "member controller"}],
            "db_ops": [{"sql": "CREATE TABLE member (member_id VARCHAR(20) PRIMARY KEY, member_name VARCHAR(100), email VARCHAR(100));"}],
        }

        original_call = generator.call_ollama
        try:
            generator.call_ollama = lambda prompt, config: _long_controller()
            result = generator.generate_files(plan, profile)
        finally:
            generator.call_ollama = original_call

        assert result["failed"] == [], result
        controller_path = root / "src/main/java/egovframework/demo/web/MemberController.java"
        content = controller_path.read_text(encoding="utf-8")
        assert len(content) < 4500, len(content)
        assert content.count("@GetMapping(") <= 3
        assert '@PostMapping("/save.do")' in content
        print("OK: jsp controller guard fallback applied")


if __name__ == "__main__":
    main()
