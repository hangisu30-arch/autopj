# path: gemini_ui.py
# Gemini → Ollama UI
# - 입력: 텍스트 직접 입력 + 파일 불러오기
# - Gemini 출력(JSON file-ops) 검증 OK 시 Ollama 전달 버튼 활성화(옵션)
# - 오류는 Gemini 출력 영역에 컬러로 표시(빨강/파랑)
# - Ollama HTTP 오류 시 응답 본문(detail)까지 표시

import os
import sys
import json
import html
import traceback
from dataclasses import dataclass

import requests
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QLabel,
    QTextEdit,
    QPlainTextEdit,
    QPushButton,
    QMessageBox,
    QHBoxLayout,
    QCheckBox,
    QFileDialog,
)

from google import genai


# =========================
# ✅ 설정 (하드코딩)
# =========================
GEMINI_API_KEY = "AIzaSyD7ZN02WaarijGCtAqKl1pE6IgvxnuFDpA"
GEMINI_MODEL = "gemini-3-flash-preview"

# 🔥 Ollama 기본 모델
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5-coder:14b"
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL.rstrip('/')}/api/generate"


# =========================
# ✅ eGovFrame Architect System Prompt
# =========================
SYSTEM_PROMPT = r"""
[ROLE]
You are an eGovFrame 4.x architect and prompt engineer.
You generate ultra-precise implementation instructions for Ollama.

[OUTPUT FORMAT - STRICT]
Return ONLY a JSON array.
Do NOT return markdown.
Do NOT explain.
Do NOT wrap in ```json.

Schema:
[
  {"path":"relative/path","purpose":"one line purpose","content":"full file content"},
  ...
]

Rules:
- Each file must contain full compilable source code.
- First line of each file must include:
  // path: <relative/path>
- Follow eGovFrame naming conventions strictly.
- Use VO, Mapper, Mapper XML, Service, ServiceImpl, Controller structure.
- ServiceImpl must be a plain Spring @Service class. Do NOT extend EgovAbstractServiceImpl.
- Mapper XML namespace must match interface FQCN.
- MyBatis id naming: selectXxxList, selectXxx, insertXxx, updateXxx, deleteXxx.
- Base package must use the project name, not the sample placeholder 'example'.
- For CRUD generation, keep all file names consistent with the primary entity selected from the requirements (e.g. <Entity>VO/<Entity>Service/<Entity>Mapper/<Entity>Controller). Do not invent login/authentication files unless the user explicitly asked for authentication.
- JSP files must be under /WEB-INF/views/.
- React/Vue must include Axios API integration.
- Nexacro must include DataSet mapping (dsSearch, dsList, dsDetail, dsInput).

NEVER output explanation.
ONLY JSON array.
""".strip()


@dataclass
class GeminiResult:
    ok: bool
    text: str
    error: str = ""


@dataclass
class OllamaResult:
    ok: bool
    text: str
    error: str = ""


def validate_file_ops_json(s: str) -> tuple[bool, str]:
    try:
        data = json.loads(s)
    except Exception as e:
        return False, f"JSON parse 실패: {repr(e)}"

    if not isinstance(data, list):
        return False, "최상위 JSON은 배열(list) 이어야 합니다."

    for i, item in enumerate(data):
        if not isinstance(item, dict):
            return False, f"items[{i}]는 객체(dict)여야 합니다."
        for k in ("path", "purpose", "content"):
            if k not in item:
                return False, f"items[{i}]에 '{k}' 키가 없습니다."
            if not isinstance(item[k], str):
                return False, f"items[{i}].{k}는 문자열(str)이어야 합니다."
        if not item["path"].strip():
            return False, f"items[{i}].path가 비어있습니다."

    return True, ""


def _read_text_file_best_effort(path: str) -> tuple[bool, str]:
    for enc in ("utf-8", "utf-8-sig", "cp949"):
        try:
            with open(path, "r", encoding=enc) as f:
                return True, f.read()
        except Exception:
            continue
    return False, "파일을 읽을 수 없습니다. (인코딩 문제일 수 있음: utf-8/utf-8-sig/cp949 모두 실패)"


def _html_pre(text: str) -> str:
    return f"<pre>{html.escape(text)}</pre>"


class GeminiWorker(QThread):
    done_sig = pyqtSignal(object)  # GeminiResult
    log_sig = pyqtSignal(str)

    def __init__(self, user_input: str):
        super().__init__()
        self.user_input = user_input

    def run(self):
        try:
            self.log_sig.emit("Gemini eGov Architect 호출 중...")

            client = genai.Client(api_key=GEMINI_API_KEY)
            final_prompt = SYSTEM_PROMPT + "\n\n[USER_INPUT]\n" + self.user_input

            resp = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=final_prompt,
            )

            text = (getattr(resp, "text", None) or "").strip()
            self.done_sig.emit(GeminiResult(ok=True, text=text))

        except Exception:
            tb = traceback.format_exc()
            self.done_sig.emit(GeminiResult(ok=False, text="", error=tb))


class OllamaWorker(QThread):
    done_sig = pyqtSignal(object)  # OllamaResult
    log_sig = pyqtSignal(str)

    def __init__(self, prompt: str):
        super().__init__()
        self.prompt = prompt

    def run(self):
        try:
            self.log_sig.emit("Ollama 전송 중...")

            payload = {
                "model": OLLAMA_MODEL,
                "prompt": self.prompt,
                "stream": False,
            }

            r = requests.post(OLLAMA_GENERATE_URL, json=payload, timeout=600)

            if r.status_code != 200:
                try:
                    j = r.json()
                    detail = j.get("error") or j
                except Exception:
                    detail = (r.text or "").strip()
                raise RuntimeError(f"Ollama HTTP {r.status_code}: {detail}")

            data = r.json()
            text = (data.get("response") or "").strip()
            self.done_sig.emit(OllamaResult(ok=True, text=text))

        except Exception:
            tb = traceback.format_exc()
            self.done_sig.emit(OllamaResult(ok=False, text="", error=tb))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("eGovFrame Architect Generator (Gemini → Ollama)")
        self.setMinimumSize(1100, 920)

        self.gemini_worker = None
        self.ollama_worker = None
        self._last_gemini_text_ok = False

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setSpacing(10)

        layout.addWidget(QLabel("기능 정의 + DB 스키마 입력 (직접 입력 또는 파일 불러오기)"))
        self.input_edit = QPlainTextEdit()
        self.input_edit.setPlaceholderText(
            "여기에 [SELECTED_ENV] + [DOMAIN] + [FUNCTION_DEFINITION] + [DB_SCHEMA] 를 입력하거나, '파일 불러오기'로 텍스트 파일을 선택하세요..."
        )
        self.input_edit.setMinimumHeight(220)
        layout.addWidget(self.input_edit)

        btn_row = QHBoxLayout()

        self.load_file_btn = QPushButton("파일 불러오기")
        self.load_file_btn.clicked.connect(self.on_load_file)
        btn_row.addWidget(self.load_file_btn)

        self.run_btn = QPushButton("Gemini 생성")
        self.run_btn.clicked.connect(self.on_run_gemini)
        btn_row.addWidget(self.run_btn)

        self.send_ollama_btn = QPushButton("Ollama로 전달")
        self.send_ollama_btn.setEnabled(False)
        self.send_ollama_btn.clicked.connect(self.on_send_ollama)
        btn_row.addWidget(self.send_ollama_btn)

        self.strict_check = QCheckBox("Gemini 출력 JSON 검증 통과 시에만 Ollama 전달 허용")
        self.strict_check.setChecked(True)
        self.strict_check.stateChanged.connect(self.refresh_ollama_button_state)
        btn_row.addWidget(self.strict_check)

        self.clear_btn = QPushButton("초기화")
        self.clear_btn.clicked.connect(self.on_clear)
        btn_row.addWidget(self.clear_btn)

        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        layout.addWidget(QLabel("Gemini 출력 (JSON File Operations)"))
        self.gemini_out = QTextEdit()
        self.gemini_out.setReadOnly(True)
        self.gemini_out.setMinimumHeight(280)
        layout.addWidget(self.gemini_out)

        layout.addWidget(QLabel("Ollama 응답"))
        self.ollama_out = QPlainTextEdit()
        self.ollama_out.setReadOnly(True)
        self.ollama_out.setMinimumHeight(220)
        layout.addWidget(self.ollama_out)

        hint = QLabel(
            f"Ollama: {OLLAMA_GENERATE_URL}  |  model={OLLAMA_MODEL}  (고정 설정)"
        )
        layout.addWidget(hint)

    def set_busy(self, busy: bool):
        self.load_file_btn.setEnabled(not busy)
        self.run_btn.setEnabled(not busy)
        self.clear_btn.setEnabled(not busy)
        self.input_edit.setEnabled(not busy)
        self.strict_check.setEnabled(not busy)

        if busy:
            self.send_ollama_btn.setEnabled(False)

        self.status_label.setText("작업 중..." if busy else "")

    def refresh_ollama_button_state(self):
        if not self._last_gemini_text_ok and self.strict_check.isChecked():
            self.send_ollama_btn.setEnabled(False)
            return
        self.send_ollama_btn.setEnabled(bool(self.gemini_out.toPlainText().strip()))

    def show_gemini_error_red(self, title: str, detail: str):
        self.gemini_out.setHtml(
            f'<span style="color:#d32f2f;"><b>{html.escape(title)}</b><br>{_html_pre(detail)}</span>'
        )

    def append_gemini_info_blue(self, title: str, detail: str):
        self.gemini_out.append(
            f'<span style="color:#1976d2;"><b>{html.escape(title)}</b><br>{_html_pre(detail)}</span>'
        )

    def on_clear(self):
        self.input_edit.setPlainText("")
        self.gemini_out.clear()
        self.ollama_out.setPlainText("")
        self.status_label.setText("")
        self._last_gemini_text_ok = False
        self.send_ollama_btn.setEnabled(False)

    def on_load_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "입력 파일 선택",
            "",
            "Text Files (*.txt *.md *.json);;All Files (*)",
        )
        if not path:
            return

        ok, content = _read_text_file_best_effort(path)
        if not ok:
            QMessageBox.critical(self, "파일 읽기 실패", content)
            return

        self.input_edit.setPlainText(content)
        self.status_label.setText(f"파일 로드 완료: {path}")

    def on_run_gemini(self):
        user_input = self.input_edit.toPlainText().strip()
        if not user_input:
            QMessageBox.information(self, "알림", "입력 내용을 작성하거나 파일을 불러오세요.")
            return

        self.set_busy(True)
        self.gemini_out.clear()
        self.ollama_out.setPlainText("")
        self._last_gemini_text_ok = False
        self.send_ollama_btn.setEnabled(False)

        self.gemini_worker = GeminiWorker(user_input=user_input)
        self.gemini_worker.log_sig.connect(self.on_log)
        self.gemini_worker.done_sig.connect(self.on_gemini_done)
        self.gemini_worker.start()

    def on_send_ollama(self):
        gemini_text = self.gemini_out.toPlainText().strip()
        if not gemini_text:
            QMessageBox.information(self, "알림", "Gemini 출력이 비어있습니다.")
            return

        if self.strict_check.isChecked():
            ok, err = validate_file_ops_json(gemini_text)
            if not ok:
                QMessageBox.critical(self, "전송 불가", f"Gemini 출력 JSON 검증 실패:\n{err}")
                return

        self.set_busy(True)
        self.ollama_out.setPlainText("")

        self.ollama_worker = OllamaWorker(prompt=gemini_text)
        self.ollama_worker.log_sig.connect(self.on_log)
        self.ollama_worker.done_sig.connect(self.on_ollama_done)
        self.ollama_worker.start()

    def on_log(self, msg: str):
        self.status_label.setText(msg)

    def on_gemini_done(self, result: GeminiResult):
        self.set_busy(False)

        if result.ok:
            self.gemini_out.setPlainText(result.text)

            ok, err = validate_file_ops_json(result.text) if result.text.strip() else (False, "empty")
            self._last_gemini_text_ok = ok

            self.status_label.setText("Gemini 완료 (JSON 검증 OK)" if ok else f"Gemini 완료 (JSON 검증 FAIL: {err})")
            self.refresh_ollama_button_state()
        else:
            self.status_label.setText("Gemini 실패")
            self.show_gemini_error_red("Gemini ERROR", result.error)
            self._last_gemini_text_ok = False
            self.send_ollama_btn.setEnabled(False)

    def on_ollama_done(self, result: OllamaResult):
        self.set_busy(False)

        if result.ok:
            self.ollama_out.setPlainText(result.text or "(empty response)")
            self.status_label.setText("Ollama 완료")
        else:
            self.status_label.setText("Ollama 실패")
            self.append_gemini_info_blue("Ollama ERROR", result.error)

        self.refresh_ollama_button_state()


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
