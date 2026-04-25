# Common Analysis Engine Integration

## What changed
- Gemini 호출 직전에 Common Analysis Engine이 먼저 실행됩니다.
- 분석 결과는 `.autopj_debug/analysis_result.json` 으로 저장됩니다.
- Gemini 프롬프트에 `[COMMON ANALYSIS RESULT - SOURCE OF TRUTH]` 블록이 추가됩니다.
- 대표 도메인/기능유형/페이지/산출물 계획을 프롬프트에 주입하여 auth와 CRUD 오판을 줄입니다.

## Added files
- `app/ui/analysis_bridge.py`
- `tests/smoke_test_analysis_integration.py`

## Modified files
- `app/ui/prompt_templates.py`
- `app/ui/main_window.py`

## Current behavior
1. UI 입력값과 추가 요구사항을 읽음
2. Common Analysis Engine 실행
3. 분석 결과 JSON 저장
4. Gemini 프롬프트에 분석 결과 주입
5. Gemini -> Ollama -> file generation 흐름 유지

## Notes
- UI 구조는 크게 바꾸지 않고 기존 흐름에 최소 범위로 연결했습니다.
- 스키마는 추가 요구사항 텍스트 안의 `CREATE TABLE ...;` 또는 단순 컬럼 정의를 우선 추출합니다.
