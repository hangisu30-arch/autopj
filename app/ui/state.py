# path: app/ui/state.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class ProjectConfig:
    project_name: str = ""
    backend_key: str = "egov_spring"
    backend_label: str = "전자정부프레임워크 (Spring Boot)"
    frontend_key: str = "jsp"
    frontend_label: str = "jsp"
    code_engine_key: str = "ollama"
    code_engine_label: str = "Ollama"
    design_style_key: str = "simple"
    design_style_label: str = "심플"
    design_url: str = ""
    database_key: str = "sqlite"
    database_label: str = "SQLite"
    db_name: str = ""
    db_login_id: str = ""
    db_password: str = ""
    output_dir: str = ""
    overwrite: bool = True
    operation_mode: str = "create"
    selected_project_id: str = ""
    selected_project_name: str = ""
    selected_project_path: str = ""
    extra_requirements: str = ""
    login_feature_enabled: bool = False
    auth_general_login: bool = False
    auth_unified_auth: bool = False
    auth_cert_login: bool = False
    auth_jwt_login: bool = False
    auth_primary_mode: str = "integrated"

    def normalize(self) -> "ProjectConfig":
        self.project_name = (self.project_name or "").strip()
        self.design_url = (self.design_url or "").strip()
        self.db_name = (self.db_name or "").strip()
        self.db_login_id = (self.db_login_id or "").strip()
        self.output_dir = (self.output_dir or "").strip()
        self.operation_mode = (self.operation_mode or "create").strip().lower() or "create"
        self.selected_project_id = (self.selected_project_id or "").strip()
        self.selected_project_name = (self.selected_project_name or "").strip()
        self.selected_project_path = (self.selected_project_path or "").strip()
        if self.operation_mode not in {"create", "modify"}:
            self.operation_mode = "create"
        self.extra_requirements = (self.extra_requirements or "").strip()
        self.auth_primary_mode = (self.auth_primary_mode or "integrated").strip().lower() or "integrated"
        if self.auth_primary_mode not in {"integrated", "general", "jwt"}:
            self.auth_primary_mode = "integrated"
        if self.auth_cert_login or self.auth_jwt_login or self.auth_general_login or self.auth_unified_auth:
            self.login_feature_enabled = True
        return self


    def is_modify_mode(self) -> bool:
        return (self.operation_mode or "create").strip().lower() == "modify"

    def operation_mode_label(self) -> str:
        return "기존 프로젝트 수정" if self.is_modify_mode() else "신규 생성"

    def operation_mode_summary(self) -> str:
        if self.is_modify_mode():
            base = "기존 프로젝트 수정: 기존 메뉴/URL/DB/테이블/공통 자산을 최대한 유지하고 관련 파일만 수정"
            if self.selected_project_name or self.selected_project_path:
                return f"{base} / 선택 프로젝트: {self.selected_project_name or '(이름 없음)'} @ {self.selected_project_path or '-'}"
            return base
        return "신규 생성: 요구사항 기준으로 필요한 파일을 생성하고 프로젝트 구조를 구성"

    def auth_feature_labels(self) -> List[str]:
        labels: List[str] = []
        if self.login_feature_enabled:
            labels.append("로그인")
        if self.auth_general_login:
            labels.append("일반 로그인")
        if self.auth_unified_auth:
            labels.append("통합인증")
        if self.auth_cert_login:
            labels.append("인증서 로그인")
        if self.auth_jwt_login:
            labels.append("JWT 로그인")
        return labels

    def frontend_branch_summary(self) -> str:
        key = (self.frontend_key or "jsp").strip().lower()
        mapping = {
            "jsp": "JSP 선택: Controller + JSP + MyBatis + 서버 렌더링",
            "react": "React 선택: Spring Boot REST API + React 프론트 + axios/fetch + router",
            "vue": "Vue 선택: Spring Boot REST API + Vue 프론트 + router + axios",
            "nexacro": "Nexacro 선택: Spring Boot API + Nexacro 화면/트랜잭션 연동",
        }
        return mapping.get(key, mapping["jsp"])

    def effective_extra_requirements(self) -> str:
        base = (self.extra_requirements or "").strip()

        blocks: List[str] = [
            "[WORK MODE CONFIRMED SETTINGS - SOURCE OF TRUTH]",
            f"- operation_mode: {'modify_existing_project' if self.is_modify_mode() else 'create_new_project'}",
            f"- operation_mode_label: {self.operation_mode_label()}",
            f"- {self.operation_mode_summary()}",
            "- 생성기는 이 블록을 작업 방식의 최종 기준으로 사용한다.",
            "- 작업 모드가 기존 프로젝트 수정이면 신규 전체 재생성보다 기존 프로젝트 구조 분석과 관련 파일 국소 수정을 우선한다.",
            f"- selected_project_id: {self.selected_project_id or '-'}",
            f"- selected_project_name: {self.selected_project_name or '-'}",
            f"- selected_project_path: {self.selected_project_path or '-'}",
            "",
            "[FRONTEND UI CONFIRMED SETTINGS - SOURCE OF TRUTH]",
            f"- frontend_mode: {(self.frontend_key or 'jsp').strip().lower() or 'jsp'}",
            f"- {self.frontend_branch_summary()}",
            "- 생성기는 이 블록을 프론트엔드 생성 방식의 최종 기준으로 사용한다.",
        ]

        if self.login_feature_enabled:
            lines: List[str] = [
                "[AUTH UI CONFIRMED SETTINGS - SOURCE OF TRUTH]",
                "- 로그인 기능 포함",
            ]
            if self.auth_general_login:
                lines.append("- 일반 로그인(ID/PW) 포함")
            if self.auth_unified_auth:
                lines.append("- 통합인증 포함")
            if self.auth_cert_login:
                lines.append("- 인증서 로그인 포함")
            if self.auth_jwt_login:
                lines.append("- JWT 로그인 포함")
            mode_map = {
                "integrated": "통합인증 우선",
                "general": "일반 로그인 우선",
                "jwt": "JWT 로그인 우선",
            }
            lines.append(f"- 기본 진입 방식: {mode_map.get(self.auth_primary_mode, '통합인증 우선')}")
            lines.append("- 생성기는 이 블록을 로그인/인증 관련 최종 설정으로 사용한다.")
            blocks.append("\n".join(lines))

        injected = "\n\n".join(blocks)
        return f"{base}\n\n{injected}".strip() if base else injected
