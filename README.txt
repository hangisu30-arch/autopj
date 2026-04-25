AI Project Generator - UI Top Panel (Gemini 출력 JSON file-ops 강제)

요청 반영:
- '제미나이 생성' 시 Gemini 출력 자체를 JSON file-op 배열로 강제.
- Ollama는 이 JSON을 기반으로 실행/보강 단계만 수행 가능(후속 단계에서 연결).

변경 사항:
- app/ui/prompt_templates.py 추가: JSON file-ops 강제 프롬프트 생성
- app/ui/json_validator.py 추가: Gemini 출력 검증
- app/ui/main_window.py 수정: Gemini 호출 프롬프트를 JSON 강제 버전으로 변경 + 검증 실패 시 에러 표시

설치/실행:
  python -m venv .venv
  .\.venv\Scripts\Activate.ps1
  python -m pip install -r requirements.txt
  python run.py

설정:
- app/ui/gemini_client.py 에서 GEMINI_API_KEY 하드코딩 교체
- 모델: gemini-3-flash-preview


[v6 변경]
- JSON 검증 규칙 개선: 파일 확장자별 path 주석 문법 허용(//, #, --, <!--, /*)


[v7 변경]
- 프론트엔드 선택값(frontend_key)에 따라 Gemini 생성 산출물을 동적으로 변경(JSP/React/Vue/Nexacro)
- JSP 강제 문구 제거, frontend 규칙 블록을 분기 적용


[v8 변경]
- '제미나이 생성' 버튼을 추가 요구사항 입력창 바로 아래로 이동 (UI 위치 변경만)


[v9 변경]
- '제미나이 생성' 버튼 우측 정렬 (UI 정렬 변경만)


[v10 변경]
- JSON(.json) 파일은 주석 불가이므로 path 주석 검증 예외 처리
- 프롬프트에 .json 주석 금지 규칙 추가
- React/Vue 선택 시 JSP 생성 금지 규칙 강화


[v11 변경]
- React/Vue 선택 시 JSP 파일 생성되면 JSON 검증 단계에서 하드 FAIL
- validate_file_ops_json에 frontend_key 전달


[v12 변경]
- .vue를 HTML 주석 타입으로 검증(<!-- path: ... -->)하도록 수정
- 확장자 룰을 테이블화(.jsx/.tsx/.md/.env 포함), .json/.env는 주석 검사 생략


[v13 변경]
- Gemini 429(RESOURCE_EXHAUSTED/Quota exceeded) 발생 시, retry-after 힌트 포함한 친절한 에러 메시지로 표시 (UI 변경 없음)


[v14 변경]
- .txt 파일은 path 주석을 강제하지 않도록 예외 처리(검증 스킵)
- 프롬프트 룰에도 .txt 주석 금지/예외 명시


[v15 변경]
- 체크박스 추가: 'Gemini 출력 json 검증 통과 시에만 Ollama 전달 허용'
- 체크 ON 시: 마지막 Gemini JSON 검증 ok=True 일 때만 'Ollama 전달' 버튼 활성화
- Ollama 전달 버튼/로직 복구(요청 기능): localhost:11434 /api/generate, model=qwen2.5-coder:14b


[v16 변경]
- QCheckBox.stateChanged 시그널 인자(int)로 인해 _update_ollama_gate_state 호출 에러 발생 → 슬롯 시그니처에 인자(_state) 추가하여 해결


[v17 변경]
- _update_ollama_gate_state 메서드가 클래스 외부에 정의되어 AttributeError 발생 → MainWindow 내부로 재정의하여 해결


[v18 변경]
- MainWindow 내 Ollama 관련 메서드 누락/미정의로 AttributeError 발생 → _update_ollama_gate_state/on_ollama_send/on_ollama_done 를 MainWindow 내부에 추가
- on_gemini_done 에서 _last_gemini_json_ok 업데이트 및 gate 상태 반영 추가
