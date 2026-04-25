# Vue Adapter Stabilization

이 문서는 autopj18_validation_autorepair_integrated 기준 통합된 Vue adapter 단계의 개요다.

## 추가된 모듈
- app/adapters/vue/vue_contracts.py
- app/adapters/vue/vue_task_builder.py
- app/adapters/vue/vue_prompt_builder.py
- app/adapters/vue/vue_validator.py
- app/ui/vue_bridge.py

## 핵심 동작
- analysis_result + backend_plan → vue_plan 계산
- 결과 저장: `.autopj_debug/vue_plan.json`
- Gemini 프롬프트에 `[VUE GENERATION PLAN - SOURCE OF TRUTH]` 블록 주입
- Vue scaffold 기준 경로 고정
  - frontend/vue/src/router/index.js
  - frontend/vue/src/constants/routes.js
  - frontend/vue/src/api/client.js
  - frontend/vue/src/services/{domain}Service.js
  - frontend/vue/src/stores/index.js
  - frontend/vue/src/views/{domain}/*View.vue

## auth 규칙
- auth 도메인은 login/auth 흐름만 허용
- generic CRUD view/service 생성 금지

## 검증
- python -m compileall app tests execution_core
- tests/smoke_test_vue_engine.py
- tests/smoke_test_vue_integration.py
