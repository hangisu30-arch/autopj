# 디자인 스타일 풍성화 패치

## 반영 내용
- 디자인 스타일 옵션 확장
  - 포털형
  - 업무포털 고급형
  - 풍부한 카드형
  - 대시보드형
  - 다크 포인트
- Gemini 프롬프트에 디자인 풍성화 지침 추가
  - 헤더/서브텍스트/검색 카드/요약 카드/콘텐츠 카드/empty-state 강제
  - common.css 우선 재사용 및 병합 강조
  - eGovFrame certlogin `com.css`, `main_portal.css` 레퍼런스 톤 반영
  - 디자인 URL 참고 규칙 강화
- JSP/React/Vue 생성 규칙에 카드형 레이아웃, 배지, 도움말 텍스트, 반응형 지침 보강

## 검증
- `python -m compileall app tests`
- `PYTHONPATH=. pytest -q tests/test_design_richness_prompt.py`
