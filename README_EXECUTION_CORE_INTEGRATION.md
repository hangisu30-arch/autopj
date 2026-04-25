# NLvL20 + execution_core (MySQL-only, JSP) 통합본

이 ZIP은 NLvL20 UI에 `execution_core` 엔진을 포함하여,
Ollama 최종 JSON(file_ops) 결과를 **Eclipse eGovFrame 프로젝트 루트에 직접 반영**하고,
Spring Boot(JSP) + MyBatis + MySQL 실행에 필요한 설정을 자동 패치합니다.

## 동작 흐름
1) '제미나이 생성' -> JSON(file_ops)
2) 'Ollama 전달' -> JSON(file_ops)
3) 적용 단계에서:
   - 파일을 프로젝트 루트에 생성/덮어쓰기
   - JSP 경로를 `/WEB-INF/views/`로 정규화
   - `application.properties` 패치 (JSP view resolver, mybatis mapper-locations 등)
   - `MyBatisConfig.java` 생성 (MapperScan + SqlSessionFactory/Template + MySQL DataSource)
   - `pom.xml` 패치 (MySQL driver, JSP jasper/jstl) *가능한 경우*
   - Mapper.xml에서 테이블명을 추출해 기본 DDL을 MySQL에 적용(가능한 경우)

## MySQL 연결 정보
NLvL20 UI의 DB 입력값을 사용합니다:
- DB 이름: db_name
- 로그인 ID: db_login_id
- 비밀번호: db_password
- host/port 는 기본 `localhost:3306` 으로 가정합니다.

## 실행 후 필수
pom.xml이 변경되면 Eclipse에서:
- Maven > Update Project
또는
- `mvn clean package`
한 번 수행 후 재실행하세요.

## JSP 경로
기존 NLvL20 프롬프트의 JSP 경로는 `/WEB-INF/views/`로 변경되었습니다.
만약 LLM이 `/WEB-INF/jsp/`로 출력해도 엔진이 `/WEB-INF/views/`로 자동 변환합니다.
