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


def _detect_primary_entity(cfg: ProjectConfig, analysis_result: Optional[Dict[str, Any]] = None) -> str:
    if analysis_result:
        domains = analysis_result.get("domains") or []
        if isinstance(domains, list) and domains:
            first = domains[0] or {}
            detected = (first.get("entity_name") or first.get("name") or "").strip()
            if detected:
                return re.sub(r"[^A-Za-z0-9_]", "", detected) or "PrimaryEntity"

    effective_requirements = cfg.effective_extra_requirements() if hasattr(cfg, "effective_extra_requirements") else (cfg.extra_requirements or "")
    text = " ".join([
        cfg.project_name or "",
        effective_requirements,
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


def _design_style_guidance(cfg: ProjectConfig) -> str:
    style_key = (cfg.design_style_key or "simple").strip().lower()
    style_label = (cfg.design_style_label or "심플").strip()
    design_url = (cfg.design_url or "").strip()

    common_rules = [
        f"[DESIGN GUIDANCE - {style_label}]",
        "- 화면 문구는 짧고 기능 중심으로 유지한다. 긴 설명문, 과한 안내문, 장식성 문구는 넣지 않는다.",
        "- 기본 화면은 필요한 제목, 검색영역, 콘텐츠영역만 우선 배치한다. 불필요한 서브타이틀/요약문/empty-state 설명은 최소화한다.",
        "- 검색 영역은 꼭 필요한 조건만 노출하고 중복 레이블/설명문을 줄인다.",
        "- 목록은 핵심 컬럼과 핵심 액션 위주로 구성하고, 반복되는 배지/보조 설명/장식 문구는 넣지 않는다.",
        "- 상세/폼 화면은 짧은 제목과 필수 입력영역 중심으로 구성한다. 필드별 도움말과 장문 안내는 사용자가 요청한 경우에만 넣는다.",
        "- 입력 폼은 가능한 경우 2열 이상의 정리된 grid/card 구조로 배치하고, textarea/날짜/시간/숫자/선택형 입력을 일반 text 한 줄 나열로 만들지 않는다.",
        "- DataType 이 date, datetime, timestamp, time 계열이면 반드시 달력/일시 선택 컴포넌트(input type=date, datetime-local 또는 동등한 date picker)를 사용하고 plain text 입력으로 두지 않는다.",
        "- 상단 메뉴와 좌측 메뉴는 현재 화면 경로를 기준으로 active 상태를 계산해, 클릭된 메뉴만 다른 색/배경/강조 스타일로 보여야 한다.",
        "- 반응형을 기본 적용하고, 1280px/1024px/768px 전후에서 컬럼 수와 패딩을 자연스럽게 줄인다.",
        "- 새 style 태그를 남발하지 말고 공통 CSS 파일에 병합한다. JSP는 common.css 또는 기존 공통 CSS를 우선 재사용한다.",
        "- 공통 스타일은 재사용하되 텍스트 길이를 늘리는 subtitle, helper text, breadcrumb, empty-state 설명은 기본값으로 강제하지 않는다.",
        "- summary chip, section subtitle, empty-state 문구, hover 안내 문구는 명시 요청이 있을 때만 추가한다.",
    ]

    style_specific = {
        "simple": [
            "- 심플 스타일은 여백과 정렬을 우선하되, 밋밋하지 않게 연한 보더, 소프트 그림자, 작은 배지와 섹션 구분선을 사용한다.",
            "- 단색 배경 하나로 끝내지 말고 검색 패널과 콘텐츠 패널의 톤 차이를 둔다.",
        ],
        "modern": [
            "- 모던 스타일은 카드형 레이아웃, 12~16px radius, 부드러운 shadow, 굵은 제목, 선명한 primary color를 사용한다.",
            "- KPI 카드, 필터 chips, 아이콘성 포인트 영역을 허용한다.",
        ],
        "contemporary": [
            "- 현대 스타일은 넓은 여백, 또렷한 타이포, 밝은 배경 위의 layered card, section subtitle을 포함한다.",
            "- 단순 표보다 카드/패널/분할영역으로 정보 구조를 보여준다.",
        ],
        "portal": [
            "- 포털형은 eGovFrame certlogin/main_portal 계열 톤을 참고해 블루 계열 포인트, 좌측 메뉴, 상단 타이틀, 검색 박스, 정보 카드 구성을 사용한다.",
            "- main_portal.css/com.css처럼 포털형 업무 화면 느낌을 주되 동일 복제는 금지하고 현대적으로 정리한다.",
        ],
        "enterprise_portal": [
            "- 업무포털 고급형은 breadcrumb, 상단 요약 카드, 필터 박스, 본문 카드, 상태 badge, 우측 액션 영역을 갖춘다.",
            "- 관리자 화면처럼 정보가 풍부해야 하며, 한 화면 안에 title/subtitle/summary/filter/content hierarchy가 보여야 한다.",
        ],
        "rich_cards": [
            "- 풍부한 카드형은 카드 내부에 title, meta, description, badge, action link, empty hint를 같이 배치한다.",
            "- 목록은 단순 row 나열 대신 card list/grid + 보조정보 2~3줄 구조를 우선한다.",
        ],
        "dashboard": [
            "- 대시보드형은 상단 KPI 카드, 기간 필터, 차트/요약 영역, 하단 상세 목록의 3단 구조를 기본으로 한다.",
            "- 카드별 배경 톤 차이와 강한 section heading을 사용한다.",
        ],
        "soft_dark": [
            "- 다크 포인트는 전체 다크모드가 아니라 밝은 배경 위에 진한 네이비/차콜 패널과 선명한 primary accent를 섞는다.",
            "- CTA 버튼, 상단 바, 상태 badge에 대비감을 주되 본문 가독성은 유지한다.",
        ],
    }.get(style_key, [])

    if design_url:
        style_specific.append(f"- 사용자가 제공한 디자인 참고 URL({design_url})의 레이아웃 톤, 카드 밀도, 타이포 구조를 참고하되 브랜드 자산을 복제하지 않는다.")

    return "\n".join(common_rules + style_specific)


def _frontend_task_block(cfg: ProjectConfig, analysis_result: Optional[Dict[str, Any]] = None) -> str:
    fk = (cfg.frontend_key or "").strip().lower()
    entity = _detect_primary_entity(cfg, analysis_result)
    ev = _entity_var(entity)
    design_block = _design_style_guidance(cfg)

    if fk == "jsp":
        return f"""[FRONTEND RULE - JSP]
- JSP 선택 분기: Controller + JSP + MyBatis + 서버 렌더링
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
- JSP는 common.css, layout.css 등 기존 공통 자산을 우선 재사용하고 필요한 규칙만 병합한다.
- 모든 JSP 화면은 정보가 한 줄씩만 나열된 밋밋한 구조를 피하고, page header/section card/summary/filter/content hierarchy 가 보이도록 정리한다.
- 입력 폼은 1열 나열 대신 grid/card 기반 섹션형 레이아웃으로 만들고, date/datetime/timestamp/time 필드는 반드시 달력 또는 일시 선택 컴포넌트를 사용한다.
- 상단 메뉴와 좌측 메뉴는 현재 URL 기준 active 상태를 계산해 선택된 메뉴만 다른 색으로 강조한다.
- 여러 업무 도메인(room/reservation 등)이 함께 생성되면 상단/좌측 공통 메뉴에서 모든 업무 도메인으로 이동 가능해야 한다.
- JSP 메인/목록/폼/상세 화면의 정적 안내 문구는 최소화한다. subtitle, helper text, empty-state 설명은 필요할 때만 추가한다.
- 포털형 또는 업무형 스타일이면 eGovFrame certlogin/com.css/main_portal.css 계열의 구조감을 참고하되 동일 복제는 금지한다.
- JSP MVC Controller는 얇게 유지한다. 기본 CRUD에서는 list/detail/form/save/delete 외의 handler를 생성하지 않는다.
- Controller에는 비즈니스 로직, SQL 조립, 장문 검증 로직, helper method, 큰 주석을 넣지 않는다.
- Controller/JSP/JS 어디에서도 generic id / getId() / item.id / row.id 를 관성적으로 사용하지 않는다. 반드시 VO와 DB 스키마의 실제 PK 필드명(예: reservationId, memberId, noticeId)을 그대로 사용한다.
- calendar 화면의 날짜 그룹핑/상태 집계/우선순위 집계는 실제 VO에 존재하는 필드로만 계산한다. 날짜는 실제 temporal 필드(startDatetime, endDatetime, reservationDate 등)를 사용하고, status/priority 필드가 없으면 해당 집계를 만들지 않는다.
- 저장/수정/삭제 결과가 목록과 캘린더 이벤트에 즉시 반영되도록 상세/폼/캘린더 흐름을 설계한다.
- 로그인/회원/사용자 관리용 테이블을 재활용할 때 credential-bearing account create/edit form 은 password/login_password/passwd/pwd 입력을 포함할 수 있다. 단 JSP list/detail/search UI 에서는 인증 민감 값을 노출하거나 바인딩하지 않는다.
- db, schemaName, database, tableName, packageName, frontendType, backendType 같은 생성 메타데이터 필드는 어떤 업무 UI 바인딩에도 노출하지 않는다.
- calendar SSR helper model(calendarCells, selectedDateSchedules 등)은 업무 VO와 별도 view-model 계약으로 취급하고, cell.date/day/eventCount/events 같은 helper 필드를 VO 필드로 오인하지 않는다.
- UI 바인딩은 최종 VO/DTO/API 계약 필드만 사용한다. mapper 기반 필드가 필요하면 계약을 보강하고, 임의 메타필드나 별칭 필드를 만들어서 우회하지 않는다.
- 하나의 도메인은 snake_case/camelCase 경로를 혼용하지 않고 canonical 도메인 네임 하나로 패키지/라우트/view/page 를 통일한다.
- calendar 기능은 요구사항에 calendar/캘린더/달력 화면이 명시된 경우에만 생성한다. schedule/temporal 컬럼만으로 calendar route/page/api 를 만들지 않는다.
- calendar 기능은 main route, controller return, main view/page, mapper contract 가 동일 canonical 도메인 기준으로 맞아야 한다.
- 요구사항에 사용자/관리자 분리와 본인 데이터/전체 데이터 구분이 있으면, 특정 도메인명을 하드코딩하지 말고 owner 필드 + role 필드 + 세션 정보로 사용자 화면과 관리자 화면을 분리한다.
- 관리자 기능이 필요하면 공통 메뉴에 관리자 진입점을 추가하되, 관리자 권한(role 필드/세션 기준)일 때만 메뉴를 렌더링한다. 일반 사용자 화면에서는 관리자 메뉴와 관리자 화면 링크를 노출하지 않는다.
- 관리자 화면/관리 API/관리 라우트는 관리자 권한 사용자만 접근 가능해야 하며, 화면 숨김과 서버측 접근 차단을 함께 구현한다.
- 사용자가 명시한 컬럼명과 comment 는 반드시 실제 DB 물리 테이블에 반영하고, CRUD/UI/API/Mapper/VO 는 반영된 컬럼 계약을 기준으로 생성한다.
- JSP Controller 목표 크기: 4500 chars 이하, 120 lines 이하, mapping handler 5개 이하.
- Controller의 @ModelAttribute / form binding 타입은 반드시 <Entity>VO 로 통일한다. 정의되지 않은 <Entity> 타입 사용 금지.
- Mapper interface 는 XML-only MyBatis 모드로 생성한다. @Mapper 는 허용하지만 @Select/@Insert/@Update/@Delete/@Results 같은 SQL annotation 은 금지한다.
- Mapper XML은 순수 MyBatis <mapper> XML만 생성한다. <beans>, HibernateTemplate, SqlMap, Spring bean 조각 혼입 금지.
- Service/ServiceImpl/Mapper/Controller/Mapper XML 메서드 시그니처와 id 타입은 전부 일치해야 한다.
- Service/ServiceImpl 에서 List<VO> 또는 VO 타입을 사용하면 import java.util.List 및 VO/Mapper import 를 반드시 생성한다.
- MyBatisConfig 는 @Configuration, @MapperScan, DataSource, SqlSessionFactoryBean, setMapperLocations 를 포함한 컴파일 가능한 코드여야 한다.
- EgovBootApplication 패키지가 생성 패키지와 다르면 scanBasePackages 로 생성 패키지를 포함한다.
- 아래 디자인 지침을 반드시 반영한다.
{design_block}
""".strip()

    if fk == "react":
        return f"""[FRONTEND RULE - REACT]
- React 선택 분기: Spring Boot REST API + React 프론트 + axios/fetch + router
- React 선택 시 JSP 파일 생성 금지. /src/main/webapp/WEB-INF/views/** 생성 금지.
- 백엔드는 Spring Boot REST API(@RestController)로 구현한다.
- React 프론트 logical root는 React 앱 루트 기준으로 작성한다. 즉 path는 frontend/react 접두사 없이 src/... 또는 public/... 형식으로 계획한다.
- React 앱이 즉시 실행 가능하도록 package.json, vite.config.js, index.html, jsconfig.json, .env.development, .env.production, src/main.jsx, src/App.jsx 등 Vite 기본 스캐폴드도 함께 고려한다.
- 구조는 전자정부 React 템플릿 철학을 따르되, EgovXXX 접두사는 강제하지 않는다.
- 컴포넌트는 .jsx, config/constants/utils/hooks/api는 .js 로 작성한다.
- .js 와 .jsx 중복 파일을 만들지 않는다.
- 모든 라우트는 src/routes/index.jsx 에서 중앙 관리하고, 경로 상수는 src/constants/routes.js 에서 관리한다.
- 페이지 내부에서 fetch/axios를 직접 난립시키지 말고 src/api/client.js 및 src/api/services/{{domain}}.js 로 분리한다.
- 로그인/auth 기능은 일반 CRUD처럼 list/detail/form/save/delete 세트를 생성하지 않는다.
- 사용자 요청이 없으면 임의 메뉴/샘플 페이지/과도한 UI 변경을 추가하지 않는다.
- auth/login/signup 화면이 아니더라도 account/user/member create/edit form 이고 login_id + password/login_password 계약을 가지면 React form 상태에 인증 민감 필드를 포함할 수 있다. 단 리스트/상세/검색에서는 렌더링하지 않는다.
- db, schemaName, database, tableName, packageName, frontendType, backendType 같은 생성 메타데이터 필드는 React state/props/UI 바인딩에 포함하지 않는다.
- React UI 바인딩은 최종 DTO/API 계약 필드만 사용한다. mapper 기반 필드가 필요하면 계약을 보강하고, 임의 메타필드나 별칭 필드를 만들어서 우회하지 않는다.
- 요구사항에 사용자/관리자 분리와 본인 데이터/전체 데이터 구분이 있으면, 도메인명을 하드코딩하지 말고 owner 필드 + role 필드 + 세션/토큰 정보를 기준으로 self/admin route 또는 guarded section 을 분리한다.
- 관리자 기능이 필요하면 공통 메뉴/네비게이션에 관리자 진입점을 추가하되, 관리자 권한일 때만 렌더링한다. 일반 사용자 화면에서는 관리자 메뉴와 관리자 링크를 노출하지 않는다.
- 관리자 화면/관리 API/관리 라우트는 관리자 권한 사용자만 접근 가능해야 하며, 프론트 가드와 서버측 접근 차단을 함께 구현한다.
- 사용자가 명시한 컬럼명과 comment 는 반드시 실제 DB 물리 테이블에 반영하고, CRUD/UI/API/Mapper/VO 는 반영된 컬럼 계약을 기준으로 생성한다.
- 예시 규칙:
  - entity class: {entity}
  - entity var: {ev}
  - api prefix: /api/{ev}
  - react page paths: src/pages/{ev}/{entity}ListPage.jsx, src/pages/{ev}/{entity}FormPage.jsx, src/pages/{ev}/{entity}DetailPage.jsx
  - auth login path: src/pages/login/LoginPage.jsx
  - api service path: src/api/services/{ev}.js
  - api client path: src/api/client.js
  - routes constant path: src/constants/routes.js
  - route registry path: src/routes/index.jsx
- 반환은 JSON이다. (JSP View 사용 금지)
- 프론트는 React Functional Component 기반으로 구현한다.
- import 경로는 실제 파일 구조와 정확히 일치해야 한다.
- 디자인 스타일에 맞춰 CSS를 적용하되, 사용자가 명시하지 않은 UI 전면 변경은 금지한다.
- React 화면은 불필요한 설명 문구 없이 간결하게 구성한다. 긴 subtitle, helper text, empty-state 설명, 장식성 배지는 기본 포함하지 않는다.
- 아래 디자인 지침을 반드시 반영한다.
{design_block}
""".strip()

    if fk == "vue":
        return f"""[FRONTEND RULE - VUE]
- Vue 선택 분기: Spring Boot REST API + Vue 프론트 + router + axios
- Vue 선택 시 JSP 파일 생성 금지. /src/main/webapp/WEB-INF/views/** 생성 금지.
- 백엔드는 Spring Boot REST API(@RestController)로 구현한다.
- Vue 프론트 root는 frontend/vue 기준으로 작성한다.
- Vue 앱이 즉시 실행 가능하도록 package.json, vite.config.js, index.html, src/main.js, src/App.vue, src/router/index.js 를 함께 고려한다.
- frontend/vue/index.html 는 반드시 <script type="module" src="/src/main.js"></script> 를 사용해야 한다. 일반 script 금지.
- 모든 라우트는 frontend/vue/src/router/index.js 에서 중앙 관리하고, 경로 상수는 frontend/vue/src/constants/routes.js 에서 관리한다.
- 페이지 내부에서 fetch/axios를 직접 난립시키지 말고 frontend/vue/src/api/client.js 및 frontend/vue/src/api/{ev}Api.js 로 분리한다.
- 로그인/auth 기능은 일반 CRUD처럼 list/detail/form/save/delete 세트를 생성하지 않는다.
- auth/login/signup 화면이 아니더라도 account/user/member create/edit view 이고 login_id + password/login_password 계약을 가지면 Vue form state 에 인증 민감 필드를 포함할 수 있다. 단 list/detail/search 에서는 렌더링하지 않는다.
- db, schemaName, database, tableName, packageName, frontendType, backendType 같은 생성 메타데이터 필드는 Vue reactive state/UI 바인딩에 포함하지 않는다.
- Vue UI 바인딩은 최종 DTO/API 계약 필드만 사용한다. mapper 기반 필드가 필요하면 계약을 보강하고, 임의 메타필드나 별칭 필드를 만들어서 우회하지 않는다.
- 요구사항에 사용자/관리자 분리와 본인 데이터/전체 데이터 구분이 있으면, 도메인명을 하드코딩하지 말고 owner 필드 + role 필드 + 세션/토큰 정보를 기준으로 self/admin route 또는 guarded section 을 분리한다.
- 관리자 기능이 필요하면 공통 메뉴/네비게이션에 관리자 진입점을 추가하되, 관리자 권한일 때만 렌더링한다. 일반 사용자 화면에서는 관리자 메뉴와 관리자 링크를 노출하지 않는다.
- 관리자 화면/관리 API/관리 라우트는 관리자 권한 사용자만 접근 가능해야 하며, 프론트 가드와 서버측 접근 차단을 함께 구현한다.
- 사용자가 명시한 컬럼명과 comment 는 반드시 실제 DB 물리 테이블에 반영하고, CRUD/UI/API/Mapper/VO 는 반영된 컬럼 계약을 기준으로 생성한다.
- 예시 규칙:
  - entity class: {entity}
  - entity var: {ev}
  - api prefix: /api/{ev}
  - vue view paths: frontend/vue/src/views/{ev}/{entity}List.vue, frontend/vue/src/views/{ev}/{entity}Form.vue, frontend/vue/src/views/{ev}/{entity}Detail.vue
  - auth login path: frontend/vue/src/views/login/LoginView.vue
  - api service path: frontend/vue/src/api/{ev}Api.js
  - api client path: frontend/vue/src/api/client.js
  - route registry path: frontend/vue/src/router/index.js
- 반환은 JSON이다. (JSP View 사용 금지)
- 프론트는 Vue 3 SFC 기반으로 구현한다. Pinia는 기본 강제하지 않는다.
- 디자인 스타일에 맞춰 CSS를 적용하되, 사용자가 명시하지 않은 UI 전면 변경은 금지한다.
- Vue 화면은 불필요한 설명 문구 없이 간결하게 구성한다. 긴 subtitle, helper text, empty-state 설명, 장식성 배지는 기본 포함하지 않는다.
- 아래 디자인 지침을 반드시 반영한다.
{design_block}
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
- Nexacro 화면은 기능 중심으로 간결하게 구성한다. 긴 안내문, helper text, empty layout text, 과한 장식성 컴포넌트는 넣지 않는다.
""".strip()

    return """[FRONTEND RULE - UNKNOWN]
- 프론트엔드 키를 인식하지 못했다. 기본은 REST API(@RestController)로 구성하고,
  프론트는 생성하지 않는다.
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
- READONLY 기능에는 save/update/delete를 생성하지 않는다.
- CRUD id는 CRUD 기능일 때만 selectXxxList/selectXxx/insertXxx/updateXxx/deleteXxx 패턴을 사용한다.
- 경로/파일명/패키지/뷰명은 모두 핵심 엔티티명과 기능 유형으로부터 규칙적으로 계산한다.
- 특정 엔티티명이나 화면명을 하드코딩하지 말 것.
- JSP MVC Controller는 요청 매핑, VO 바인딩, Service 호출, Model 설정, view/redirect 반환만 담당한다.
- Controller 내부 SQL, 과도한 분기, helper method 남발, 장문 주석은 금지한다.
- Mapper interface 는 XML-only MyBatis 모드로 유지한다. @Mapper 는 사용 가능하지만 SQL annotation 은 금지한다.
- Mapper XML 은 순수 MyBatis mapper XML만 허용한다. <beans>, SqlMap, HibernateTemplate, Spring bean 설정 조각은 금지한다.
- MyBatisConfig 는 @Configuration, @MapperScan, DataSource, SqlSessionFactoryBean, setMapperLocations 를 포함해야 한다.
- Service/ServiceImpl/Mapper/Controller/Mapper XML 의 메서드명, 파라미터 타입, id 타입은 서로 정확히 일치해야 한다.
- Controller의 form/save 바인딩은 반드시 <Entity>VO 를 사용한다.
- 로그인/회원 테이블을 다른 업무 도메인에서 재활용하더라도 password/login_password/passwd/pwd 같은 인증 민감 컬럼은 auth/login/signup/reset-password 또는 account create/edit 요청 바인딩 외의 CRUD 응답, JSP Model, React/Vue API payload 에 실어 보내지 않는다.
- db, schemaName, database, tableName, packageName, frontendType, backendType 같은 생성 메타데이터 필드는 DTO/API/model/frontend contract 로 노출하지 않는다.
- mapper 기반 필드가 필요하면 DTO/API 계약 자체를 보강하고, 임의 메타필드나 별칭 필드를 생성해서 UI를 맞추지 않는다.
- 사용자/관리자 분리 요구가 있으면 테이블/컬럼/경로/컴포넌트명을 하드코딩하지 말고 owner 필드, role 필드, 세션 또는 토큰 컨텍스트를 기준으로 접근 범위를 계산한다.
- 관리자 기능이 필요하면 공통 메뉴에 관리자 진입점을 추가하되, 관리자 권한 사용자에게만 노출한다. 일반 사용자 화면에서는 관리자 메뉴와 관리자 라우트를 노출하지 않는다.
- 관리자 API/관리 화면은 관리자 권한 사용자만 접근 가능해야 하며, 프론트 숨김만 하지 말고 백엔드 권한체크도 함께 구현한다.
- 사용자가 명시한 컬럼명과 comment 는 반드시 실제 DB 물리 테이블에 반영하고, CRUD/UI/API/Mapper/VO 는 반영된 컬럼 계약을 기준으로 생성한다.
- 테이블에 대한 COMMENT 구문은 절대로 외부에 단독으로 작성하지 말고, 반드시 `CREATE TABLE` 문장의 닫는 괄호 `)` 바로 뒤에 이어서 작성하세요. (예: `... ) COMMENT='회원테이블';`)
- 초기 데이터를 삽입하는 `INSERT INTO` 문의 컬럼명과 데이터 개수는 반드시 직전에 정의한 `CREATE TABLE`의 컬럼명과 100% 정확하게 일치해야 합니다. 테이블에 없는 컬럼(예: phone 등)을 INSERT 문에 임의로 추가하지 마세요.
- 단일 소스의 진실(Single Source of Truth): 프로젝트에 생성된 모든 MyBatis Mapper XML (예: AdminMemberMapper, JoinMapper 등)에서 호출하는 `tb_` 로 시작하는 모든 테이블은 반드시 `schema.sql` 파일 내에 `CREATE TABLE` 문으로 작성되어야 합니다.
- Mapper에는 존재하지만 schema.sql에 테이블이 누락되면 서버가 즉시 다운되므로, 절대로 테이블 생성을 생략하거나 누락하지 마세요.
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
- mvnw, mvnw.cmd, .mvn/wrapper/maven-wrapper.properties 는 템플릿으로 생성된다. Gemini 출력에 포함하지 말 것.
- src/main/resources/application.properties(또는 yml)은 템플릿으로 생성된다. Gemini 출력에 포함하지 말 것.

[ENTITY DISCOVERY]
- 핵심 엔티티는 사용자의 요구사항에서 추론한다.
- 현재 추론된 대표 엔티티: {entity}
- entity class: {entity}
- entity var: {ev}
- 이 값들은 예시일 뿐이며, 요구사항에 더 적합한 핵심 엔티티가 있으면 그 기준으로 통일한다.
- 특정 이름을 하드코딩하지 말 것.
""".strip()

    design_block = _design_style_guidance(cfg)

    mode_key = (getattr(cfg, "operation_mode", "create") or "create").strip().lower()
    is_modify = mode_key == "modify"
    work_mode_block = [
        "[WORK MODE ENFORCEMENT]",
        f"- operation_mode: {'modify_existing_project' if is_modify else 'create_new_project'}",
        f"- operation_mode_label: {cfg.operation_mode_label() if hasattr(cfg, 'operation_mode_label') else ('기존 프로젝트 수정' if is_modify else '신규 생성')}",
    ]
    if is_modify:
        work_mode_block.extend([
            "- 반드시 기존 프로젝트를 분석한 뒤 관련 파일만 수정한다.",
            "- 신규 전체 재생성 금지. 기존 메뉴/URL/DB/테이블/공통 자산을 최대한 유지한다.",
            "- 수정 대상과 직접 관련 없는 파일 생성/교체/삭제를 최소화한다.",
            "- 기존 Controller/Service/Mapper/XML/JSP/schema.sql/data.sql/menu/layout 을 우선 재사용하고 부족한 부분만 보완한다.",
        ])
    else:
        work_mode_block.extend([
            "- 신규 생성 모드이므로 요구사항에 필요한 파일을 계획적으로 생성한다.",
        ])

    injected = [
        "[PROJECT SETTINGS - AUTO INJECTED]",
        f"- project_name: {cfg.project_name or '(empty)'}",
        f"- backend: {cfg.backend_label} (key={cfg.backend_key})",
        f"- frontend: {cfg.frontend_label} (key={cfg.frontend_key})",
        f"- code_engine: {cfg.code_engine_label} (key={cfg.code_engine_key})",
        f"- design_style: {cfg.design_style_label} (key={cfg.design_style_key})",
        f"- design_url: {cfg.design_url or '(none)'}",
        "- design_richness: high",
        f"- database: {cfg.database_label} (key={cfg.database_key})",
        f"- db_name: {cfg.db_name or '(default project_name)'}",
        f"- output_dir: {cfg.output_dir or '(none)'}",
        "",
        "[USER EXTRA REQUIREMENTS]",
        (cfg.effective_extra_requirements().strip() if hasattr(cfg, "effective_extra_requirements") else (cfg.extra_requirements.strip() if cfg.extra_requirements else "(없음)")) or "(없음)",
        "",
        design_block,
        "",
        *work_mode_block,
        "",
    ]

    backend_block = _backend_task_block(cfg)
    frontend_block = _frontend_task_block(cfg, analysis_result=analysis_result)
    analysis_block = analysis_result_to_prompt_text(analysis_result)
    backend_plan_block = backend_plan_to_text(backend_plan)
    jsp_plan_block = jsp_plan_to_text(jsp_plan)
    react_plan_block = react_plan_to_text(react_plan)
    vue_plan_block = vue_plan_to_text(vue_plan)
    nexacro_plan_block = nexacro_plan_to_text(nexacro_plan)
    validation_block = validation_report_to_text(validation_report)
    repair_block = auto_repair_plan_to_text(repair_plan)

    task = f"""[TASK]
위 설정과 요구사항으로 필요한 모든 파일의 스펙을 작성하라.
- 먼저 기능 유형을 분류한 뒤 그 유형에 필요한 파일만 생성한다.
- 작업 모드가 기존 프로젝트 수정이면 기존 산출물/경로/공통 자산을 최대한 재사용하고 관련 파일만 수정하는 스펙을 우선 작성한다.
- 가능한 기능 유형 예: AUTH, CRUD, READONLY, SEARCH, DASHBOARD, FILE, BATCH, APPROVAL, CODE, TREE, MASTER_DETAIL, EXTERNAL_API, REPORT, ADMIN, MYPAGE, WORKFLOW, SCHEDULE, NOTIFICATION, SYSTEM.
- VO/Mapper/Service/ServiceImpl/Controller/화면(선택 프론트)은 기능 유형에 따라 필요한 경우에만 포함한다.
- AUTH 기능은 로그인 화면, 로그인 처리, 로그아웃 등 인증 흐름만 생성하고 CRUD 메서드/화면은 생성하지 않는다.
- READONLY 기능은 목록/상세/조회만 생성하고 save/update/delete는 생성하지 않는다.
- 테이블명, 컬럼명, URL, JSP 파일명, view 반환값은 모두 핵심 엔티티와 스키마로부터 계산한다.
- 반드시 업무 중심 순서를 따른다: 업무 엔티티/업무 규칙 결정 -> 업무용 테이블/컬럼 결정 -> 그 컬럼 기준 SQL 작성 -> 그 SQL 기준 백엔드와 프론트 생성.
- 분석 결과에 domain fields 가 있으면 그것이 업무용 컬럼의 source of truth 이다. Mapper SQL, VO 필드, form input name, resultMap, select/insert/update/delete 문은 그 컬럼만 사용한다.
- 폼 입력 제어 타입도 스키마/IR 의 DataType 기반으로 계산한다. date/datetime/timestamp/time 은 달력 또는 일시 선택 컴포넌트를 사용하고, boolean 은 checkbox/select, 긴 본문은 textarea 를 우선 사용한다.
- 화면 라벨, 버튼, 메뉴, 섹션 제목은 가능하면 한글로 작성한다. Create/Edit/Delete/Save/Cancel/Prev Month/Next Month/Navigation 같은 영문 공용 문구를 그대로 노출하지 말고 등록/수정/삭제/저장/취소/이전 달/다음 달/바로가기처럼 업무 사용자가 이해하기 쉬운 한글 표현을 우선 사용한다.
- 메뉴 active 상태, 초기 진입 index 경로, 공통 레이아웃/공통 CSS 연결은 생성된 대표 화면과 실제 라우트 기준으로 계산한다.
- index 역할의 진입 파일이 필요하면 생성하되, 특정 기능 경로를 하드코딩하지 말고 생성된 대표 화면 기준으로 연결한다.
- index/home/main 은 업무 CRUD 도메인으로 생성하지 않는다. IndexController 는 entry-only redirect/forward controller 여야 하며 IndexVO/IndexService/IndexMapper/index table 을 생성하거나 참조하지 말 것.
- JSP/React/Vue/Nexacro 공통 규칙: index/home/main/landing/root 는 진입 화면 역할만 가진다. 파일명에 Form/View 가 포함되어도 업무 입력 폼으로 취급하지 말고, 대표 화면 이동/대시보드/안내 셸로 취급한다. entry 화면에 CRUD save/delete/list URL, 업무 DTO 바인딩, 필수 입력 검증, form tag 강제를 넣지 말 것.

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
- compile/build/runtime/startup/endpoint_smoke 같은 생성/검증 메타데이터 이름은 업무 테이블/컬럼/DTO/UI 필드로 절대 사용하지 말 것.
- 데이터 저장/수정 화면은 실제 업무 테이블 컬럼 전체를 기준으로 생성한다. 운영·감사 컬럼이라도 저장 계약에 포함되는 컬럼이면 UI에서 명시적으로 렌더링하고, editable 여부만 read-only/hidden input/select 등으로 제어할 것.
- All physical table names must start with tb_. If the user supplied an unprefixed business table name, normalize it to the tb_ form and reflect the same canonical name in schema.sql, Mapper XML, SQL, VO metadata, React/Vue/Nexacro data contracts, and UI labels/routes where needed.
- DB 종류(MySQL/Oracle/PostgreSQL 등)에 따라 예약어를 테이블명/컬럼명으로 사용하지 말 것. 예약어 충돌 시 quote/backtick 으로 우회하지 말고 의미를 유지한 안전한 대체명으로 변경하고 schema.sql, VO, Mapper XML, SQL, Controller, JSP 전부 동일하게 반영할 것.
- 기존 테이블을 확장해야 할 때 schema.sql 또는 초기화 코드가 재실행 가능(idempotent)해야 한다. ALTER TABLE ... ADD COLUMN 은 대상 DB metadata 또는 information_schema 로 컬럼 존재 여부를 먼저 확인한 뒤, 컬럼이 없을 때만 실행할 것. 이미 존재하는 컬럼 추가 때문에 startup 이 실패하면 안 된다.
- 임의의 엔티티명이나 화면명을 추가하지 말 것.

[IMPORTANT]
- 출력은 반드시 JSON 배열만.
- 각 항목 content는 코드가 아닌 스펙만. (900자 이내)
- pom.xml, mvnw, mvnw.cmd, .mvn/wrapper/maven-wrapper.properties, application.properties는 출력하지 말 것.
""".strip()

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
        backend_block,
        frontend_block,
        task,
    ]).strip()

# autopj guard: never emit synthetic placeholder fields such as repeat7, section, tempField, sampleField into business UI or backend contracts.
