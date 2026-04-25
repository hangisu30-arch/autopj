# path: app/ui/prompt_templates.py
from __future__ import annotations

import re
from typing import Any, Dict, Optional

from app.ui.analysis_bridge import analysis_result_to_prompt_text
from app.ui.backend_bridge import backend_plan_to_text
from app.ui.jsp_bridge import jsp_plan_to_text
from app.ui.react_bridge import react_plan_to_text
from app.ui.vue_bridge import vue_plan_to_text
from app.ui.nexacro_bridge import nexacro_plan_to_text
from app.ui.validation_bridge import validation_report_to_text, auto_repair_plan_to_text
from app.ui.state import ProjectConfig
from app.io.design_style_rules import available_style_labels_text, build_design_style_prompt_block
from app.io.egov_reference_contract import build_egov_reference_prompt_block, CANONICAL_JSP_COMMON_CSS_PATH


def _detect_primary_entity(cfg: ProjectConfig, analysis_result: Optional[Dict[str, Any]] = None) -> str:
    if analysis_result:
        domains = analysis_result.get("domains") or []
        if isinstance(domains, list) and domains:
            first = domains[0] or {}
            detected = (first.get("entity_name") or first.get("name") or "").strip()
            if detected:
                return re.sub(r"[^A-Za-z0-9_]", "", detected) or "PrimaryEntity"

    text = " ".join([
        cfg.project_name or "",
        cfg.extra_requirements or "",
    ]).strip()
    tokens = re.findall(r"[A-Z][A-Za-z0-9_]+", text)
    blacklist = {
        "Crud", "Create", "Update", "Delete", "List", "Detail", "Form",
        "Spring", "Boot", "Jsp", "React", "Vue", "Nexacro", "MyBatis",
        "Mysql", "Oracle", "Postgresql", "Sqlite", "Json", "Api", "Ui",
        "Controller", "Service", "Mapper", "Vo",
    }
    for token in tokens:
        if token not in blacklist:
            return token
    return "PrimaryEntity"


def _entity_var(entity: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "", entity or "").strip() or "primaryEntity"
    if cleaned.isupper():
        return cleaned.lower()
    m = re.match(r"^([A-Z]{2,})([A-Z][a-z].*)$", cleaned)
    if m:
        return m.group(1).lower() + m.group(2)
    return cleaned[:1].lower() + cleaned[1:]


def _frontend_task_block(cfg: ProjectConfig, analysis_result: Optional[Dict[str, Any]] = None) -> str:
    fk = (cfg.frontend_key or "").strip().lower()
    entity = _detect_primary_entity(cfg, analysis_result)
    ev = _entity_var(entity)

    if fk == "jsp":
        return f"""[FRONTEND RULE - JSP]
- Spring MVC (@Controller) + JSP(JSTL) 기반으로 구현한다.
- JSP는 반드시 /src/main/webapp/WEB-INF/views/ 아래에 생성한다.
- View 반환과 JSP 파일명은 동일한 규칙으로 생성한다.
- 경로/파일명/리턴값은 하드코딩하지 말고, 핵심 엔티티명을 기준으로 일관되게 계산한다.
- 예시 규칙:
  - entity class: {entity}
  - entity var: {ev}
  - list view: "{ev}/{ev}List"
  - form view: "{ev}/{ev}Form"
  - detail view: "{ev}/{ev}Detail"
  - list jsp: src/main/webapp/WEB-INF/views/{ev}/{ev}List.jsp
  - form jsp: src/main/webapp/WEB-INF/views/{ev}/{ev}Form.jsp
  - detail jsp: src/main/webapp/WEB-INF/views/{ev}/{ev}Detail.jsp
- 공통 CSS가 필요하면 생성하고 JSP에서 로드한다.
- JSP 공통 CSS는 src/main/webapp/css/common.css 를 canonical file로 사용하고, 모든 JSP가 그 파일을 로드한다.
- JSP MVC Controller는 얇게 유지한다. 기본 CRUD에서는 list/detail/form/save/delete 외의 handler를 생성하지 않는다.
- Controller에는 비즈니스 로직, SQL 조립, 장문 검증 로직, helper method, 큰 주석을 넣지 않는다.
- JSP Controller 목표 크기: 4500 chars 이하, 120 lines 이하, mapping handler 5개 이하.
- Controller의 @ModelAttribute / form binding 타입은 반드시 <Entity>VO 로 통일한다. 정의되지 않은 <Entity> 타입 사용 금지.
- Mapper interface 는 XML-only MyBatis 모드로 생성한다. @Mapper 는 허용하지만 @Select/@Insert/@Update/@Delete/@Results 같은 SQL annotation 은 금지한다.
- Mapper XML은 순수 MyBatis <mapper> XML만 생성한다. <beans>, HibernateTemplate, SqlMap, Spring bean 조각 혼입 금지.
- Service/ServiceImpl/Mapper/Controller/Mapper XML 메서드 시그니처와 id 타입은 전부 일치해야 한다.
- Service/ServiceImpl 에서 List<VO> 또는 VO 타입을 사용하면 import java.util.List 및 VO/Mapper import 를 반드시 생성한다.
- MyBatisConfig 는 @Configuration, @MapperScan, DataSource, SqlSessionFactoryBean, setMapperLocations 를 포함한 컴파일 가능한 코드여야 한다.
- EgovBootApplication 패키지가 생성 패키지와 다르면 scanBasePackages 로 생성 패키지를 포함한다.
""".strip()

    if fk == "react":
        return f"""[FRONTEND RULE - REACT]
- React 선택 시 JSP 파일 생성 금지. /src/main/webapp/WEB-INF/views/** 생성 금지.
- 백엔드는 Spring Boot REST API(@RestController)로 구현한다.
- 단, 클래스명은 JSP와 동일하게 <Entity>Controller 를 사용한다. 예: LoginController, MemberController.\n- <Entity>RestController / <Entity>ApiController 같은 이름 금지.\n- 단, 클래스명은 JSP와 동일하게 <Entity>Controller 를 사용한다. 예: LoginController, MemberController.\n- <Entity>RestController / <Entity>ApiController 같은 이름 금지.\n- React 프론트 logical root는 React 앱 루트 기준으로 작성한다. 즉 path는 frontend/react 접두사 없이 src/... 또는 public/... 형식으로 계획한다.
- React 앱이 즉시 실행 가능하도록 package.json, vite.config.js, index.html, jsconfig.json, .env.development, .env.production, src/main.jsx, src/App.jsx 등 Vite 기본 스캐폴드도 함께 고려한다.
- 구조는 전자정부 React 템플릿 철학을 따르되, EgovXXX 접두사는 강제하지 않는다.
- 컴포넌트는 .jsx, config/constants/utils/hooks/api는 .js 로 작성한다.
- .js 와 .jsx 중복 파일을 만들지 않는다.
- 모든 라우트는 src/routes/index.jsx 에서 중앙 관리하고, 경로 상수는 src/constants/routes.js 에서 관리한다.
- 페이지 내부에서 fetch/axios를 직접 난립시키지 말고 src/api/client.js 및 src/api/services/{{domain}}.js 로 분리한다.
- 로그인/auth 기능은 일반 CRUD처럼 list/detail/form/save/delete 세트를 생성하지 않는다.
- 사용자 요청이 없으면 임의 메뉴/샘플 페이지/과도한 UI 변경을 추가하지 않는다.
- 예시 규칙:
  - entity class: {entity}
  - entity var: {ev}
  - api prefix: /api/{ev}
  - react page paths: src/pages/{ev}/{entity}ListPage.jsx, src/pages/{ev}/{entity}FormPage.jsx, src/pages/{ev}/{entity}DetailPage.jsx
  - auth login path: src/pages/login/LoginPage.jsx
  - api service path: src/api/services/{ev}.js
- shared common css path: src/css/common.css
  - api client path: src/api/client.js
  - routes constant path: src/constants/routes.js
  - route registry path: src/routes/index.jsx
- 반환은 JSON이다. (JSP View 사용 금지)
- 프론트는 React Functional Component 기반으로 구현한다.
- import 경로는 실제 파일 구조와 정확히 일치해야 한다.
- 선택된 디자인 스타일에 맞춰 CSS를 적용하되, 사용자가 명시하지 않은 UI 전면 변경은 금지한다. 사용 가능한 스타일: {{available_styles}}.
""".strip()

    if fk == "vue":
        return f"""[FRONTEND RULE - VUE]
- Vue 선택 시 JSP 파일 생성 금지. /src/main/webapp/WEB-INF/views/** 생성 금지.
- 백엔드는 Spring Boot REST API(@RestController)로 구현한다.
- Vue 프론트 root는 frontend/vue 기준으로 작성한다.
- Vue 앱이 즉시 실행 가능하도록 package.json, vite.config.js, index.html, src/main.js, src/App.vue, src/router/index.js 를 함께 고려한다.
- frontend/vue/index.html 는 반드시 <script type="module" src="/src/main.js"></script> 를 사용해야 한다. 일반 script 금지.
- 모든 라우트는 frontend/vue/src/router/index.js 에서 중앙 관리하고, 경로 상수는 frontend/vue/src/constants/routes.js 에서 관리한다.
- 페이지 내부에서 fetch/axios를 직접 난립시키지 말고 frontend/vue/src/api/client.js 및 frontend/vue/src/api/{ev}Api.js 로 분리한다.
- 로그인/auth 기능은 일반 CRUD처럼 list/detail/form/save/delete 세트를 생성하지 않는다.
- 예시 규칙:
  - entity class: {entity}
  - entity var: {ev}
  - api prefix: /api/{ev}
  - vue view paths: frontend/vue/src/views/{ev}/{entity}List.vue, frontend/vue/src/views/{ev}/{entity}Form.vue, frontend/vue/src/views/{ev}/{entity}Detail.vue
  - auth login path: frontend/vue/src/views/login/LoginView.vue
  - api service path: frontend/vue/src/api/{ev}Api.js
  - api client path: frontend/vue/src/api/client.js
  - route registry path: frontend/vue/src/router/index.js
- shared common css path: frontend/vue/src/css/common.css
- 반환은 JSON이다. (JSP View 사용 금지)
- 프론트는 Vue 3 SFC 기반으로 구현한다. Pinia는 기본 강제하지 않는다.
- 선택된 디자인 스타일에 맞춰 CSS를 적용하되, 사용자가 명시하지 않은 UI 전면 변경은 금지한다. 사용 가능한 스타일: {{available_styles}}.
""".strip()

    if fk == "nexacro":
        return f"""[FRONTEND RULE - NEXACRO]
- 백엔드는 Nexacro uiadapter17/N 기반 컨트롤러로 구현한다.
- @Controller 기반으로 작성하고, NexacroMapDTO/DataSet 통신 규칙을 따른다.
- DataSet 명칭/컬럼/변수명은 핵심 엔티티 스키마에서 계산한다.
- 예시 규칙:
  - entity class: {entity}
  - entity var: {ev}
  - controller: {entity}NexacroController
  - nexacro form paths: frontend/nexacro/{ev}/{entity}List.xfdl, frontend/nexacro/{ev}/{entity}Form.xfdl, frontend/nexacro/{ev}/{entity}Detail.xfdl
  - nexacro script path: frontend/nexacro/{ev}/{entity}Service.xjs
- JSP 파일 생성 금지. 특정 엔티티명 문자열을 하드코딩하지 말 것.
""".strip()

    return """[FRONTEND RULE - UNKNOWN]
- 프론트엔드 키를 인식하지 못했다. 기본은 REST API(@RestController)로 구성하고,
  백엔드 클래스명은 여전히 <Entity>Controller 로 유지하며, 프론트는 생성하지 않는다.
""".strip()


def _backend_task_block(cfg: ProjectConfig) -> str:
    return """[BACKEND RULE - EGOV SPRING]
- 전자정부 표준 프레임워크(eGovFrame 4.x) 스타일을 따른다.
- 레이어 구조: service/vo, service/mapper, resources/egovframework/mapper, service, service.impl, web
- ServiceImpl은 일반 Spring @Service 구현체로 생성 (EgovAbstractServiceImpl 금지)
- Mapper interface 물리 경로는 service/mapper, VO 물리 경로는 service/vo
- MyBatis Mapper XML namespace는 Mapper Interface의 FQCN과 일치
- 기능을 먼저 분류한다. (AUTH / CRUD / READONLY / SEARCH / DASHBOARD / FILE / WORKFLOW / APPROVAL / REPORT / EXTERNAL_API 등)
- AUTH 기능(login, logout, auth, signin 등)에는 list/detail/form/save/delete/insert/update/delete 메서드와 화면을 생성하지 않는다. 단 로그인 입력 화면(login form)은 허용된다.
- AUTH 기능은 누락 없는 auth bundle 로 계획한다. 최소 구성: VO, Mapper Interface, Mapper XML(authenticate query), Service, ServiceImpl, Controller, 로그인 화면(선택된 프론트 기준). 일부만 생성하는 것은 금지한다.
- READONLY 기능에는 save/update/delete를 생성하지 않는다.
- CRUD id는 CRUD 기능일 때만 selectXxxList/selectXxx/insertXxx/updateXxx/deleteXxx 패턴을 사용한다.
- 경로/파일명/패키지/뷰명은 모두 핵심 엔티티명과 기능 유형으로부터 규칙적으로 계산한다.
- 백엔드 클래스명은 프론트 종류와 무관하게 항상 동일해야 한다. 예: MemberController / LoginController / BoardController.\n- LoginRestController, MemberRestController, BoardApiController 같은 프론트 종속 이름은 금지한다.\n- 특정 엔티티명이나 화면명을 하드코딩하지 말 것.
- JSP MVC Controller는 요청 매핑, VO 바인딩, Service 호출, Model 설정, view/redirect 반환만 담당한다.
- Controller 내부 SQL, 과도한 분기, helper method 남발, 장문 주석은 금지한다.
- Mapper interface 는 XML-only MyBatis 모드로 유지한다. @Mapper 는 사용 가능하지만 SQL annotation 은 금지한다.
- Mapper XML 은 순수 MyBatis mapper XML만 허용한다. <beans>, SqlMap, HibernateTemplate, Spring bean 설정 조각은 금지한다.
- MyBatisConfig 는 @Configuration, @MapperScan, DataSource, SqlSessionFactoryBean, setMapperLocations 를 포함해야 한다.
- Service/ServiceImpl/Mapper/Controller/Mapper XML 의 메서드명, 파라미터 타입, id 타입은 서로 정확히 일치해야 한다.
- Controller의 form/save 바인딩은 반드시 <Entity>VO 를 사용한다.
""".strip()


def build_gemini_json_fileops_prompt(
    cfg: ProjectConfig,
    analysis_result: Optional[Dict[str, Any]] = None,
    backend_plan: Optional[Dict[str, Any]] = None,
    jsp_plan: Optional[Dict[str, Any]] = None,
    react_plan: Optional[Dict[str, Any]] = None,
    vue_plan: Optional[Dict[str, Any]] = None,
    nexacro_plan: Optional[Dict[str, Any]] = None,
    validation_report: Optional[Dict[str, Any]] = None,
    repair_plan: Optional[Dict[str, Any]] = None,
    current_project_snapshot: str = "",
    existing_project_snapshot: str = "",
) -> str:
    entity = _detect_primary_entity(cfg, analysis_result)
    ev = _entity_var(entity)

    header = f"""[ROLE]
너는 전자정부 표준 프레임워크(eGovFrame 4.x) 아키텍트이자 플래너다.
역할은 Ollama가 파일을 구현할 수 있도록 파일별 지시(spec)를 만드는 것이다.

[OUTPUT FORMAT - STRICT]
반드시 JSON 배열만 출력한다.
마크다운 금지. 설명 금지. 코드펜스 금지.

Schema:
[
  {{"path":"relative/path","purpose":"one line purpose","content":"SPEC ONLY (NO CODE)"}},
  ...
]

[CRITICAL - NO CODE]
- content에는 완성 코드를 절대 포함하지 말 것.
- 코드로 오인될 패턴은 금지한다.
- content는 지시/요구사항만 bullet list 형태로 작성한다.
- 각 item의 content 길이는 900자 이내.

[TEMPLATE FILES - EXCLUDE]
- pom.xml은 템플릿으로 생성된다. Gemini 출력에 포함하지 말 것.
- src/main/resources/application.properties(또는 yml)은 템플릿으로 생성된다. Gemini 출력에 포함하지 말 것.

[ENTITY DISCOVERY]
- 핵심 엔티티는 사용자의 요구사항에서 추론한다.
- 현재 추론된 대표 엔티티: {entity}
- entity class: {entity}
- entity var: {ev}
- 이 값들은 예시일 뿐이며, 요구사항에 더 적합한 핵심 엔티티가 있으면 그 기준으로 통일한다.
- 특정 이름을 하드코딩하지 말 것.
""".strip()

    available_styles = available_style_labels_text()

    injected = [
        "[PROJECT SETTINGS - AUTO INJECTED]",
        f"- project_name: {cfg.project_name or '(empty)'}",
        f"- backend: {cfg.backend_label} (key={cfg.backend_key})",
        f"- frontend: {cfg.frontend_label} (key={cfg.frontend_key})",
        f"- code_engine: {cfg.code_engine_label} (key={cfg.code_engine_key})",
        f"- design_style: {cfg.design_style_label} (key={cfg.design_style_key})",
        f"- design_url: {cfg.design_url or '(none)'}",
        f"- database: {cfg.database_label} (key={cfg.database_key})",
        f"- db_name: {cfg.db_name or '(default project_name)'}",
        f"- output_dir: {cfg.output_dir or '(none)'}",
        f"- modify_existing_mode: {bool(getattr(cfg, 'modify_existing_mode', False))}",
        f"- target_files: {getattr(cfg, 'target_files_text', '') or '(auto)'}",
        "",
        "[USER EXTRA REQUIREMENTS]",
        cfg.extra_requirements.strip() if cfg.extra_requirements else "(없음)",
        "",
    ]

    backend_block = _backend_task_block(cfg)
    frontend_block = _frontend_task_block(cfg, analysis_result=analysis_result).replace('{available_styles}', available_styles)
    design_style_block = build_design_style_prompt_block(cfg.design_style_key)
    egov_reference_block = build_egov_reference_prompt_block()
    analysis_block = analysis_result_to_prompt_text(analysis_result)
    backend_plan_block = backend_plan_to_text(backend_plan)
    jsp_plan_block = jsp_plan_to_text(jsp_plan)
    react_plan_block = react_plan_to_text(react_plan)
    vue_plan_block = vue_plan_to_text(vue_plan)
    nexacro_plan_block = nexacro_plan_to_text(nexacro_plan)
    validation_block = validation_report_to_text(validation_report)
    repair_block = auto_repair_plan_to_text(repair_plan)

    modify_block = ''
    if bool(getattr(cfg, 'modify_existing_mode', False)):
        modify_block = f"""
[MODIFY EXISTING PROJECT MODE]
- 이것은 신규 생성이 아니라 기존 생성물을 수정하는 작업이다.
- 현재 존재하는 파일 내용을 우선 기준으로 삼고, 관련 없는 구조/레이아웃/공통 include/class/css 규칙은 유지한다.
- 선택된 파일이 있으면 그 파일만 수정 대상으로 삼고, 필요한 경우에만 최소 개수의 관련 파일을 추가한다.
- 출력 JSON 배열에는 실제로 변경할 파일만 포함한다.
- 기존 JSP가 common.jsp, leftNav.jsp, /css/common.css, app-layout, app-main, page-card, table-wrap, data-table, search_box, board_list 구조를 이미 가지고 있으면 유지한다.
- JSP 공통 CSS canonical path는 {CANONICAL_JSP_COMMON_CSS_PATH} 이다. 입력 경로가 resources/css/common.css 여도 동일 파일로 취급한다.
- 기존 CSS 수정은 전체 재작성 대신 기존 규칙을 보존하면서 필요한 규칙만 추가하는 방식으로 계획한다.
- CSS는 기존 공통 CSS를 우선 기준으로 하고, 신규 규칙만 추가/병합한다.
- 기존 Java/XML/JSP/React/Vue 파일을 통째로 갈아엎지 말고 수정 의도에 직접 필요한 파일만 JSON 배열에 포함한다.
[EXISTING PROJECT SNAPSHOT]
{(current_project_snapshot or existing_project_snapshot).strip() if (current_project_snapshot or existing_project_snapshot) else '(snapshot unavailable)'}
""".strip()

    task = f"""[TASK]
위 설정과 요구사항으로 필요한 모든 파일의 스펙을 작성하라.
- 먼저 기능 유형을 분류한 뒤 그 유형에 필요한 파일만 생성한다.
- 가능한 기능 유형 예: AUTH, CRUD, READONLY, SEARCH, DASHBOARD, FILE, BATCH, APPROVAL, CODE, TREE, MASTER_DETAIL, EXTERNAL_API, REPORT, ADMIN, MYPAGE, WORKFLOW, SCHEDULE, NOTIFICATION, SYSTEM.
- VO/Mapper/Service/ServiceImpl/Controller/화면(선택 프론트)은 기능 유형에 따라 필요한 경우에만 포함한다.
- AUTH 기능은 로그인 화면, 로그인 처리, 로그아웃 등 인증 흐름만 생성하고 CRUD 메서드/화면은 생성하지 않는다.
- AUTH 기능의 파일 집합은 반드시 완전해야 한다. 예: LoginController가 있으면 LoginVO, LoginService, LoginServiceImpl, LoginMapper, LoginMapper.xml, login.jsp(또는 선택 프론트의 login view)를 함께 계획한다.
- READONLY 기능은 목록/상세/조회만 생성하고 save/update/delete는 생성하지 않는다.
- 테이블명, 컬럼명, URL, JSP 파일명, view 반환값은 모두 핵심 엔티티와 스키마로부터 계산한다.
- index 역할의 진입 파일이 필요하면 생성하되, 특정 기능 경로를 하드코딩하지 말고 생성된 대표 화면 기준으로 연결한다.

[PACKAGE RULE]
- 모든 Java package는 반드시 egovframework.<project_name>. 로 시작한다.
- sample placeholder인 example 패키지를 사용하지 말 것.
- 패키지의 기능 세그먼트는 요구사항의 의미를 반영한 이름을 사용한다. 예: 로그인=login, 회원관리=member, 게시판=board.
- package 예시: egovframework.<project_name>.login.web, egovframework.<project_name>.member.service, egovframework.<project_name>.member.service.mapper
- ui, screen, page, app 같은 일반명사를 기능 패키지명으로 사용하지 말 것.

[CONSISTENCY RULE]
- 같은 엔티티에 대해 파일명/클래스명/Mapper/XML/JSP/URL이 모두 일관되어야 한다.
- Service / ServiceImpl / Mapper Interface / Mapper XML / Controller 의 메서드명, 파라미터 타입, 반환 타입, id 타입을 서로 다르게 만들지 말 것.
- Mapper Interface 는 XML-only 모드로 생성하고 SQL annotation 을 섞지 말 것. SQL 은 Mapper XML에만 둔다.
- Mapper XML 은 반드시 MyBatis mapper DOCTYPE 과 <mapper namespace="..."> 를 사용하고, Spring <beans> 조각을 섞지 말 것.
- MyBatisConfig 는 컴파일 가능한 Spring Boot 코드로 생성하고 wildcard mapper scan(예: *.mapper) 사용 금지.
- Login/Auth 기능은 사용자가 명시적으로 요청한 경우에만 생성한다.
- 로그인/인증 기능은 generic CRUD로 만들지 말 것. 예: list.do, detail.do, save.do, delete.do 금지.
- DB 스키마에 없는 컬럼/테이블/VO 필드를 추측해서 만들지 말 것.
- 임의의 엔티티명이나 화면명을 추가하지 말 것.

[IMPORTANT]
- 출력은 반드시 JSON 배열만.
- 각 항목 content는 코드가 아닌 스펙만. (900자 이내)
- pom.xml, application.properties는 출력하지 말 것.
""".strip()

    if bool(getattr(cfg, 'modify_existing_mode', False)):
        task = task.replace('[TASK]', '[TASK - MODIFY EXISTING]', 1)

    return "\n\n".join([
        header,
        "\n".join(injected).strip(),
        analysis_block,
        backend_plan_block,
        jsp_plan_block,
        react_plan_block,
        vue_plan_block,
        nexacro_plan_block,
        validation_block,
        repair_block,
        modify_block,
        design_style_block,
        egov_reference_block,
        backend_block,
        frontend_block,
        task,
    ]).strip()
