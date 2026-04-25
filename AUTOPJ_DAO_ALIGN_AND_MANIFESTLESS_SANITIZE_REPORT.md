# AUTOPJ DAO ALIGN AND MANIFESTLESS SANITIZE PATCH REPORT

## 핵심 수정
- `app/validation/post_generation_repair.py`
  - frontend UI sanitize를 manifest lookup보다 먼저 수행하도록 변경
  - manifest에 없는 JSP도 `db/schemaName/tableName/packageName` 같은 generation metadata를 즉시 제거 가능
- `app/validation/backend_compile_repair.py`
  - `DAO.java`에서 호출하는 mapper 메서드를 기준으로 companion `Mapper.java` 인터페이스를 자동 보강하는 `_ensure_dao_mapper_method_alignment` 추가
  - `cannot find symbol`이 DAO 내부 mapper 호출 불일치에서 나는 경우 로컬 contract repair 단계에서 바로 정렬
- `tests/test_compile_dao_alignment_and_manifestless_ui_sanitize.py`
  - DAO→Mapper method alignment 회귀 테스트 추가
  - manifest 없이도 metadata sanitize가 유효한지 회귀 테스트 추가

## 검증
- `python -m py_compile app/validation/post_generation_repair.py app/validation/backend_compile_repair.py tests/test_compile_dao_alignment_and_manifestless_ui_sanitize.py`
- `pytest -q tests/test_compile_dao_alignment_and_manifestless_ui_sanitize.py tests/test_post_validation_loop_guards.py tests/test_generic_dao_fallback_and_ui_sanitize.py`
- 결과: `8 passed`
