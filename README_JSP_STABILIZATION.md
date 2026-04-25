# JSP Stabilization Integration

이번 통합은 `analysis_result`와 `backend_plan`을 바탕으로 JSP용 생성 계획(`jsp_plan`)을 계산하고,
그 결과를 Gemini 프롬프트에 `[JSP GENERATION PLAN - SOURCE OF TRUTH]` 블록으로 주입하는 단계입니다.

## 추가된 모듈
- `app/adapters/jsp/jsp_contracts.py`
- `app/adapters/jsp/jsp_task_builder.py`
- `app/adapters/jsp/jsp_prompt_builder.py`
- `app/adapters/jsp/jsp_validator.py`
- `app/ui/jsp_bridge.py`

## 디버그 산출물
- `.autopj_debug/jsp_plan.json`

## 핵심 규칙
- JSP는 반드시 `src/main/webapp/WEB-INF/views/{domain}/...` 아래에 생성
- MVC Controller의 return 값은 실제 JSP 파일과 일치하는 domain-relative view name 사용
  - 예: `src/main/webapp/WEB-INF/views/member/memberList.jsp` → return `"member/memberList"`
- auth 도메인은 `login.jsp`만 허용하고 generic CRUD JSP는 금지
