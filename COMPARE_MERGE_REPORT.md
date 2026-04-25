# autopj_sucess_2 vs autopj (7) 비교/병합 보고서

## 비교 결과 요약
- 기준: `autopj_sucess_2`
- 비교본: `autopj (7)`
- 구조상 `autopj (7)`이 상위판이며, `autopj_sucess_2`에는 소스 변경과 테스트 보강이 누락되어 있었음.

## 핵심 차이
- `autopj (7)`에만 존재하던 파일: 84개
- 공통 파일 중 내용이 달랐던 핵심 소스/테스트: 37개

## 이번 병합에서 반영한 핵심 보강
1. 회원가입/로그인 request mapping 충돌 repair 및 startup handoff 호환성 보강
2. runtime ambiguous mapping 로그 -> static issue 변환 보강
3. mapper XML(single quote 포함) 기반 필드 추론 보강
4. 명시 요구사항(`tb_users`, `tb_schedule`) 우선 스키마 반영 보강
5. MySQL schema sync helper 호환 함수 추가
6. String ID / String datetime 규칙 보강
7. schedule mapper/controller 생성 규칙 보강

## 추가 반영 파일 범위
- `app/`
- `execution_core/`
- `tests/`
- 일부 README/patch summary 파일

## 병합 후 추가 수정
`autopj (7)` 자체에도 테스트와 코드 간 호환 누락이 있어 아래를 추가 수정함.
- `_startup_runtime_to_static_issues` compatibility helper 추가
- `_run_startup_repair_handoff` 구/신 호출 시그니처 동시 지원
- `_mysql_schema_sync_statements` compatibility helper 추가
- ambiguous mapping log detail 보강
- explicit user table -> Login/User 판별 보정
- mapper resultMap single quote 파싱 보강
- String datetime mapper/controller 출력 보정

## 검증
다음 회귀 테스트 묶음을 실행했고 모두 통과함.
- `tests/test_signup_login_route_conflict_regression.py`
- `tests/test_startup_handoff_and_entry_route_regression.py`
- `tests/test_startup_repair_handoff.py`
- `tests/test_column_comments_schema_support.py`
- `tests/test_mapper_xml_authority_for_db_and_ui.py`
- `tests/test_mapper_xml_over_schema_sql_priority.py`
- `tests/test_user_defined_schema_priority_end_to_end.py`
- `tests/test_string_id_and_datetime_query_contract.py`

결과: **34 passed**
