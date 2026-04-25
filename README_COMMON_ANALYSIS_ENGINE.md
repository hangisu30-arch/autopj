# autopj(15) Common Analysis Engine Patch

이 압축 파일은 autopj(15) 기준의 1단계 `Common Analysis Engine` 코드 골격입니다.

## 포함 파일
- `app/engine/analysis/*`
- `example_run.py`
- `tests/smoke_test_analysis.py`

## 빠른 실행
```bash
python example_run.py
python tests/smoke_test_analysis.py
```

## 포함 범위
이 패치는 다음 파일들만 포함합니다.
- analysis_context.py
- analysis_result.py
- requirement_parser.py
- schema_parser.py
- domain_classifier.py
- artifact_planner.py
- naming_rules.py
- analysis_engine.py

## 목적
- 요구사항 + DB schema + frontend 모드 기반 분석 결과 JSON 생성
- CRUD / AUTH 기본 구분
- JSP / React / Vue / Nexacro별 file generation plan 초안 계산
- eGovFrame package / class / path naming 규칙 공통화
