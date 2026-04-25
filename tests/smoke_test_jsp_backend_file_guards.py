from __future__ import annotations

import sys
import types
from types import SimpleNamespace

ollama_client = types.ModuleType("execution_core.ollama_client")
ollama_client.call_ollama = lambda prompt, config: ""
sys.modules["execution_core.ollama_client"] = ollama_client

logger_mod = types.ModuleType("execution_core.logger")
logger_mod.log = lambda message: None
sys.modules["execution_core.logger"] = logger_mod

builtin_mod = types.ModuleType("execution_core.builtin_crud")
builtin_mod.infer_schema_from_plan = lambda plan: SimpleNamespace(entity="Member", entity_var="member", feature_kind="crud")
builtin_mod.infer_entity_from_plan = lambda plan: "Member"
builtin_mod.builtin_file = lambda logical_path, effective_base, schema: None
builtin_mod.ddl = lambda schema: "CREATE TABLE member (member_id VARCHAR(20) PRIMARY KEY);"
sys.modules["execution_core.builtin_crud"] = builtin_mod

feature_rules = types.ModuleType("execution_core.feature_rules")
feature_rules.classify_feature_kind = lambda task: "crud"
feature_rules.is_auth_kind = lambda kind: False
feature_rules.is_read_only_kind = lambda kind: False
sys.modules["execution_core.feature_rules"] = feature_rules

from execution_core.generator import GenerationError, validate_content


def _expect_invalid(logical_path: str, content: str, expected: str) -> None:
    try:
        validate_content(logical_path, content)
    except GenerationError as exc:
        assert expected in str(exc), str(exc)
        return
    raise AssertionError(f"expected validation failure containing: {expected}")


def main() -> None:
    _expect_invalid(
        "java/config/MyBatisConfig.java",
        '''package egovframework.fulljsp.config;

@Configuration
@MapperScan(basePackages = "egovframework.fulljsp.*.mapper")
public class MyBatisConfig {
}
''',
        "invalid MyBatisConfig",
    )

    _expect_invalid(
        "java/service/MemberService.java",
        '''package egovframework.fulljsp.member.service;

public interface MemberService {
    List<MemberVO> selectMemberList(MemberVO memberVO);
}
''',
        "service missing java.util.List import",
    )

    _expect_invalid(
        "java/service/impl/MemberServiceImpl.java",
        '''package egovframework.fulljsp.member.service.impl;

import egovframework.fulljsp.member.service.MemberService;
import org.springframework.stereotype.Service;

@Service
public class MemberServiceImpl implements MemberService {
    private final MemberMapper memberMapper;
    public MemberServiceImpl(MemberMapper memberMapper) {
        this.memberMapper = memberMapper;
    }
}
''',
        "service impl missing mapper import",
    )

    _expect_invalid(
        "java/service/mapper/MemberMapper.java",
        '''package egovframework.fulljsp.member.service.mapper;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;

@Mapper
public interface MemberMapper {
    @Select("SELECT 1")
    int count();
}
''',
        "XML-only mode",
    )

    _expect_invalid(
        "java/controller/MemberController.java",
        '''package egovframework.fulljsp.member.web;

public class MemberController {
    public String save(@ModelAttribute Member member) {
        return "redirect:/member/memberList.do";
    }
}
''',
        "controller must bind VO types only",
    )

    _expect_invalid(
        "mapper/member/MemberMapper.xml",
        '''<beans>
  <bean id="memberMapper" />
</beans>
<mapper namespace="egovframework.fulljsp.member.service.mapper.MemberMapper"></mapper>
''',
        "legacy iBATIS/sqlMap XML detected",
    )

    _expect_invalid(
        "java/EgovBootApplication.java",
        '''package egovframework.example;

public class EgovBootApplication {
}
''',
        "scanBasePackages",
    )

    print("OK: jsp backend file guards reject malformed MyBatis/JSP outputs")


if __name__ == "__main__":
    main()
