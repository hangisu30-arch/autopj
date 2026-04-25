# autopj_sucess_2 추가 보강 패치 보고서

이번 추가 패치는 `MemberController` 의 Spring request mapping conflict 가 반복되는 문제를 직접 겨냥했다.

## 추가 반영 내용

1. `generated_project_validator.py`
- 동일 Controller 파일 내부의 중복 매핑도 `ambiguous_request_mapping` 으로 검출하도록 보강
- 기존에는 서로 다른 파일 간 충돌만 잡아서, 같은 `MemberController.java` 내부 중복은 놓칠 수 있었음

2. `project_auto_repair.py`
- `member`, `user`, `account` 계열 도메인을 회원가입/회원관리 도메인으로 인식하도록 확장
- `Spring request mapping conflict detected` 발생 시 `MemberController` 를 안전한 회원가입 라우트 구조로 직접 재작성하도록 보강
- 재작성 라우트:
  - `@RequestMapping("/member")`
  - `@GetMapping({"/register.do", "/form.do"})`
  - `@GetMapping("/checkLoginId.do")`
  - `@PostMapping({"/actionRegister.do", "/save.do"})`
  - `@GetMapping("/list.do")`

3. 회귀 테스트 추가
- 같은 Controller 내부의 중복 매핑 검출 테스트 추가
- `MemberController` 가 `/login` 네임스페이스를 잘못 점유한 경우 자동 복구 테스트 추가

## 실행 검증

다음 테스트 묶음 통과:
- `tests/test_member_request_mapping_conflict_regression.py`
- `tests/test_signup_login_route_conflict_regression.py`
- `tests/test_startup_handoff_and_entry_route_regression.py`
- `tests/test_startup_repair_handoff.py`
- `tests/test_post_validation_loop_guards.py`

결과: **22 passed**
