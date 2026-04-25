# PATCH_REQUEST_PARAM_ROUTE_FALSE_POSITIVE_REPORT

## 원인
- duplicate request mapping 정적 검사에서 메서드 annotation만 읽어야 하는데,
  annotation + method signature 전체를 함께 읽고 있었다.
- 그래서 `@RequestParam("loginId")` 같은 파라미터 문자열까지 route 후보로 잘못 수집되었다.
- 결과적으로 아래 같은 정상 코드가 오탐으로 실패했다.
  - `@GetMapping("/detail.do")`
  - `public String detail(@RequestParam("loginId") String loginId, ...)`
  - validator가 `/detail.do` 외에 `/loginId`도 route로 잘못 인식

## 수정
- 파일: `app/validation/generated_project_validator.py`
- duplicate request mapping 검사에서 method-level route 추출 대상을
  `m.group(0)`(전체 메서드 헤더)에서
  `@{kind}({annotation_args})`(순수 annotation)로 축소

## 추가 테스트
- `tests/test_request_mapping_request_param_false_positive_regression.py`
  - `@RequestParam("loginId")`가 route로 오인되지 않는지 검증
- 기존 회원가입/매핑 충돌 회귀 테스트도 함께 통과

## 검증 결과
- `pytest -q tests/test_member_request_mapping_conflict_regression.py tests/test_request_mapping_request_param_false_positive_regression.py`
- 결과: `3 passed`
