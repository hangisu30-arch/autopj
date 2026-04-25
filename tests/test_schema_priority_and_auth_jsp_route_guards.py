from pathlib import Path

from app.validation.generated_project_validator import (
    _discover_primary_login_route as validator_discover_primary_login_route,
    _jsp_screen_role,
    _parse_schema_sql_tables,
)
from app.validation.project_auto_repair import (
    _auth_alias_kind_for_jsp_path,
    _discover_primary_login_route as repair_discover_primary_login_route,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


def test_schema_parser_prefers_canonical_schema_over_login_variant_for_same_table(tmp_path: Path):
    _write(
        tmp_path / 'src/main/resources/schema.sql',
        """
        CREATE TABLE IF NOT EXISTS tb_member (
            member_id VARCHAR(64) COMMENT '회원 ID',
            member_name VARCHAR(100) COMMENT '회원명',
            login_id VARCHAR(100) COMMENT '로그인 ID',
            password VARCHAR(100) COMMENT '비밀번호',
            email VARCHAR(200) COMMENT '이메일',
            phone VARCHAR(30) COMMENT '연락처',
            join_date DATETIME COMMENT '가입일시',
            use_yn CHAR(1) COMMENT '사용 여부'
        );
        """,
    )
    _write(
        tmp_path / 'src/main/resources/login-schema.sql',
        """
        CREATE TABLE IF NOT EXISTS tb_member (
            member_id VARCHAR(64),
            login_id VARCHAR(100)
        );
        """,
    )

    tables = _parse_schema_sql_tables(tmp_path)

    assert tables['tb_member']['path'] == 'src/main/resources/schema.sql'
    assert tables['tb_member']['columns'] == [
        'member_id', 'member_name', 'login_id', 'password', 'email', 'phone', 'join_date', 'use_yn'
    ]
    assert tables['tb_member']['comments']['member_name'] == '회원명'


def test_schema_parser_recognizes_comment_on_column_statements(tmp_path: Path):
    _write(
        tmp_path / 'src/main/resources/schema.sql',
        """
        CREATE TABLE IF NOT EXISTS tb_member (
            member_id VARCHAR(64),
            login_id VARCHAR(100)
        );
        COMMENT ON COLUMN tb_member.member_id IS '회원 ID';
        COMMENT ON COLUMN tb_member.login_id IS '로그인 ID';
        """,
    )

    tables = _parse_schema_sql_tables(tmp_path)

    assert tables['tb_member']['comments']['member_id'] == '회원 ID'
    assert tables['tb_member']['comments']['login_id'] == '로그인 ID'


def test_login_list_jsp_is_not_misclassified_as_login_screen():
    jsp = Path('src/main/webapp/WEB-INF/views/login/loginList.jsp')
    assert _jsp_screen_role(jsp, '<html><body><table></table></body></html>') == 'list'
    assert _auth_alias_kind_for_jsp_path(jsp) == ''


def test_primary_login_route_prefers_login_login_do(tmp_path: Path):
    _write(
        tmp_path / 'src/main/java/demo/login/web/LoginController.java',
        """
        package demo.login.web;

        import org.springframework.stereotype.Controller;
        import org.springframework.web.bind.annotation.GetMapping;
        import org.springframework.web.bind.annotation.RequestMapping;

        @Controller
        @RequestMapping("/login")
        public class LoginController {
            @GetMapping("/login.do")
            public String loginForm() { return "login/login"; }

            @GetMapping("/certLogin.do")
            public String certLogin() { return "login/certLogin"; }
        }
        """,
    )
    _write(
        tmp_path / 'src/main/java/demo/root/web/IndexController.java',
        """
        package demo.root.web;

        import org.springframework.stereotype.Controller;
        import org.springframework.web.bind.annotation.GetMapping;

        @Controller
        public class IndexController {
            @GetMapping("/login.do")
            public String shortcut() { return "redirect:/login/login.do"; }
        }
        """,
    )

    assert validator_discover_primary_login_route(tmp_path) == '/login/login.do'
    assert repair_discover_primary_login_route(tmp_path) == '/login/login.do'
