# Common Backend Engine Integration

이번 단계에서 추가된 내용:

- `app/engine/backend/*`
  - 분석 결과 JSON을 기반으로 공통 backend generation plan 계산
  - controller mode 분기: JSP=`mvc_controller`, React/Vue=`rest_controller`, Nexacro=`nexacro_controller`
  - backend artifact path 계산: VO / Mapper / Mapper.xml / Service / ServiceImpl / Controller / MyBatisConfig
- `app/ui/backend_bridge.py`
  - backend plan 생성/저장/프롬프트 변환 브리지
- `app/ui/main_window.py`
  - Gemini 호출 직전에 analysis result에서 backend plan을 계산하고 `.autopj_debug/backend_plan.json` 저장
- `app/ui/prompt_templates.py`
  - Gemini 프롬프트에 `[COMMON BACKEND GENERATION PLAN - SOURCE OF TRUTH]` 블록 주입

저장 경로:
- `.autopj_debug/analysis_result.json`
- `.autopj_debug/backend_plan.json`

주의:
- 이번 단계는 공통 backend engine의 “계획층” 통합이다.
- 실제 Java 코드 생성기를 전면 교체한 단계는 아니며, Gemini/Ollama가 따라야 할 backend source-of-truth를 고정한 단계다.
