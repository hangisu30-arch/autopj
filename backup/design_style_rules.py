from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, List, Mapping


@dataclass(frozen=True)
class DesignStylePreset:
    key: str
    label: str
    description: str
    tokens: Mapping[str, str]


_STYLE_PRESETS: List[DesignStylePreset] = [
    DesignStylePreset(
        key="simple",
        label="심플",
        description="장식을 줄이고 밝은 배경과 얇은 보더로 정돈된 업무형 화면을 만듭니다.",
        tokens={
            "app_bg": "#f6f8fb",
            "panel_bg": "#ffffff",
            "sidebar_bg": "#fbfcfe",
            "brand": "#2563eb",
            "brand_soft": "#e8f0ff",
            "text_main": "#1f2937",
            "text_sub": "#6b7280",
            "border": "#d6deeb",
            "button_text": "#ffffff",
            "shadow_soft": "0 12px 28px rgba(37, 99, 235, 0.08)",
            "radius_panel": "18px",
            "radius_button": "12px",
        },
    ),
    DesignStylePreset(
        key="modern",
        label="모던",
        description="여백을 넉넉하게 두고 부드러운 그림자와 카드형 구조를 사용하는 세련된 스타일입니다.",
        tokens={
            "app_bg": "#f2f6fb",
            "panel_bg": "#ffffff",
            "sidebar_bg": "#f8fbff",
            "brand": "#2f66e7",
            "brand_soft": "#eaf0ff",
            "text_main": "#18253d",
            "text_sub": "#64748b",
            "border": "#d7dfef",
            "button_text": "#ffffff",
            "shadow_soft": "0 18px 40px rgba(39, 73, 143, 0.10)",
            "radius_panel": "24px",
            "radius_button": "14px",
        },
    ),
    DesignStylePreset(
        key="professional",
        label="프로페셔널",
        description="신뢰감 있는 블루-그레이 톤과 안정적인 타이포 계층을 사용하는 기업형 스타일입니다.",
        tokens={
            "app_bg": "#f4f7fb",
            "panel_bg": "#ffffff",
            "sidebar_bg": "#f7f9fc",
            "brand": "#1d4ed8",
            "brand_soft": "#e0ebff",
            "text_main": "#162033",
            "text_sub": "#5b6880",
            "border": "#cfd8e6",
            "button_text": "#ffffff",
            "shadow_soft": "0 16px 36px rgba(21, 42, 84, 0.10)",
            "radius_panel": "18px",
            "radius_button": "12px",
        },
    ),
    DesignStylePreset(
        key="enterprise",
        label="엔터프라이즈",
        description="관리자 화면에 맞게 밀도 높은 테이블과 실용적인 보더 중심 구성을 사용합니다.",
        tokens={
            "app_bg": "#eef3f8",
            "panel_bg": "#ffffff",
            "sidebar_bg": "#f4f7fb",
            "brand": "#0f4c81",
            "brand_soft": "#dceeff",
            "text_main": "#102033",
            "text_sub": "#56657a",
            "border": "#c8d4e3",
            "button_text": "#ffffff",
            "shadow_soft": "0 12px 28px rgba(15, 76, 129, 0.08)",
            "radius_panel": "14px",
            "radius_button": "10px",
        },
    ),
    DesignStylePreset(
        key="public_service",
        label="공공기관형",
        description="명확한 정보 구조와 높은 가독성을 우선하는 신뢰 중심의 공공 서비스 스타일입니다.",
        tokens={
            "app_bg": "#f5f7fb",
            "panel_bg": "#ffffff",
            "sidebar_bg": "#f8faff",
            "brand": "#0b5cab",
            "brand_soft": "#e4f0ff",
            "text_main": "#152238",
            "text_sub": "#4f6078",
            "border": "#bfcde0",
            "button_text": "#ffffff",
            "shadow_soft": "0 10px 24px rgba(11, 92, 171, 0.08)",
            "radius_panel": "12px",
            "radius_button": "10px",
        },
    ),
    DesignStylePreset(
        key="dashboard",
        label="대시보드형",
        description="카드, 요약 정보, 빠른 액션을 강조하는 시각적으로 선명한 운영 대시보드 스타일입니다.",
        tokens={
            "app_bg": "#eef4ff",
            "panel_bg": "#ffffff",
            "sidebar_bg": "#f3f7ff",
            "brand": "#2563eb",
            "brand_soft": "#dbeafe",
            "text_main": "#172554",
            "text_sub": "#556987",
            "border": "#cddaf5",
            "button_text": "#ffffff",
            "shadow_soft": "0 20px 44px rgba(37, 99, 235, 0.14)",
            "radius_panel": "22px",
            "radius_button": "14px",
        },
    ),
    DesignStylePreset(
        key="premium",
        label="프리미엄",
        description="고급스러운 포인트 컬러와 깊이 있는 그림자로 절제된 프리미엄 분위기를 만듭니다.",
        tokens={
            "app_bg": "#f7f4ff",
            "panel_bg": "#ffffff",
            "sidebar_bg": "#fbf8ff",
            "brand": "#6d28d9",
            "brand_soft": "#ede9fe",
            "text_main": "#2e1065",
            "text_sub": "#6b5b95",
            "border": "#ddd6fe",
            "button_text": "#ffffff",
            "shadow_soft": "0 22px 48px rgba(109, 40, 217, 0.14)",
            "radius_panel": "24px",
            "radius_button": "16px",
        },
    ),
    DesignStylePreset(
        key="friendly",
        label="친근한 스타일",
        description="밝고 부드러운 색감, 둥근 버튼, 가벼운 그림자로 친화적인 화면을 만듭니다.",
        tokens={
            "app_bg": "#fffaf5",
            "panel_bg": "#ffffff",
            "sidebar_bg": "#fffdf8",
            "brand": "#f97316",
            "brand_soft": "#ffedd5",
            "text_main": "#4a2c17",
            "text_sub": "#8a6543",
            "border": "#f6d5b3",
            "button_text": "#ffffff",
            "shadow_soft": "0 18px 38px rgba(249, 115, 22, 0.12)",
            "radius_panel": "26px",
            "radius_button": "18px",
        },
    ),
    DesignStylePreset(
        key="vibrant",
        label="화려한 스타일",
        description="강한 포인트 컬러와 또렷한 강조 효과로 시각적 임팩트를 크게 주는 스타일입니다.",
        tokens={
            "app_bg": "linear-gradient(180deg, #fdf2ff 0%, #eef6ff 100%)",
            "panel_bg": "rgba(255, 255, 255, 0.95)",
            "sidebar_bg": "rgba(255, 255, 255, 0.92)",
            "brand": "#db2777",
            "brand_soft": "#fce7f3",
            "text_main": "#3b0764",
            "text_sub": "#7c3a86",
            "border": "#f3c7e6",
            "button_text": "#ffffff",
            "shadow_soft": "0 24px 50px rgba(219, 39, 119, 0.16)",
            "radius_panel": "24px",
            "radius_button": "16px",
        },
    ),
    DesignStylePreset(
        key="dark",
        label="다크 모드",
        description="어두운 배경과 높은 대비를 사용해 눈부심을 줄이고 포인트 컬러를 강조합니다.",
        tokens={
            "app_bg": "#0b1220",
            "panel_bg": "#111a2d",
            "sidebar_bg": "#0f172a",
            "brand": "#60a5fa",
            "brand_soft": "rgba(96, 165, 250, 0.18)",
            "text_main": "#e5eefc",
            "text_sub": "#a8b8d3",
            "border": "#25324a",
            "button_text": "#0b1220",
            "shadow_soft": "0 20px 48px rgba(2, 6, 23, 0.45)",
            "radius_panel": "22px",
            "radius_button": "14px",
        },
    ),
]

_STYLE_MAP: Dict[str, DesignStylePreset] = {preset.key: preset for preset in _STYLE_PRESETS}
_STYLE_ALIASES = {
    "contemporary": "modern",
    "public": "public_service",
    "dark_mode": "dark",
    "friendly_style": "friendly",
    "vivid": "vibrant",
}
_BASE_TOKENS: Dict[str, str] = {
    "menu_width": "280px",
    "page_padding": "24px",
    "page_padding_mobile": "18px",
    "gap": "24px",
    "content_padding": "32px",
    "font_stack": '"Malgun Gothic", "Apple SD Gothic Neo", sans-serif',
}


def design_style_presets() -> List[DesignStylePreset]:
    return list(_STYLE_PRESETS)


def normalize_style_key(key: str | None) -> str:
    raw = (key or "simple").strip().lower()
    raw = _STYLE_ALIASES.get(raw, raw)
    return raw if raw in _STYLE_MAP else "simple"


def get_style_preset(key: str | None) -> DesignStylePreset:
    return _STYLE_MAP[normalize_style_key(key)]


def style_tokens(style_key: str | None) -> Dict[str, str]:
    preset = get_style_preset(style_key)
    merged = dict(_BASE_TOKENS)
    merged.update(dict(preset.tokens))
    merged["style_key"] = preset.key
    merged["style_label"] = preset.label
    merged["style_description"] = preset.description
    return merged


def available_style_labels_text() -> str:
    return ", ".join(p.label for p in _STYLE_PRESETS)


def build_design_style_hint(style_key: str | None) -> str:
    preset = get_style_preset(style_key)
    return f"{preset.label}: {preset.description}"


def build_design_style_prompt_block(style_key: str | None) -> str:
    preset = get_style_preset(style_key)
    tokens = style_tokens(style_key)
    return (
        "[DESIGN STYLE RULE]\n"
        f"- selected_style: {preset.label} (key={preset.key})\n"
        f"- description: {preset.description}\n"
        f"- primary_color: {tokens['brand']}\n"
        f"- background: {tokens['app_bg']}\n"
        f"- panel_radius: {tokens['radius_panel']}\n"
        "- 공통 레이아웃 클래스 구조는 유지하고, 색상/그림자/라운드/간격을 선택 스타일에 맞게 조정한다.\n"
        "- JSP/React/Vue 모두 같은 스타일 철학을 따르되 각 프론트의 파일 구조는 분리 유지한다."
    )


def _css_var_lines(tokens: Mapping[str, str], selector: str = ":root") -> str:
    ordered = [
        ("app_bg", "--app-bg"),
        ("panel_bg", "--panel-bg"),
        ("sidebar_bg", "--sidebar-bg"),
        ("brand", "--brand"),
        ("brand_soft", "--brand-soft"),
        ("text_main", "--text-main"),
        ("text_sub", "--text-sub"),
        ("border", "--panel-border"),
        ("button_text", "--button-text"),
        ("shadow_soft", "--shadow-soft"),
        ("radius_panel", "--radius-panel"),
        ("radius_button", "--radius-button"),
        ("menu_width", "--menu-width"),
        ("gap", "--layout-gap"),
        ("page_padding", "--page-padding"),
        ("page_padding_mobile", "--page-padding-mobile"),
        ("content_padding", "--content-padding"),
        ("font_stack", "--font-stack"),
    ]
    lines = [f"{selector} {{"]
    for src, css_name in ordered:
        value = tokens.get(src)
        if value is not None:
            lines.append(f"  {css_name}: {value};")
    lines.append("}")
    return "\n".join(lines)


def render_jsp_common_css(style_key: str | None) -> str:
    vars_block = _css_var_lines(style_tokens(style_key))
    return f'''/* path: src/main/webapp/css/common.css */
{vars_block}

* {{ box-sizing: border-box; }}
html {{ scroll-behavior: smooth; }}
body {{
  margin: 0;
  background: var(--app-bg);
  color: var(--text-main);
  font-family: var(--font-stack);
}}

a {{ color: inherit; text-decoration: none; }}

a:hover {{
  text-decoration: none;
}}

.page-wrap {{
  min-height: 100vh;
  padding: var(--page-padding);
}}

.app-layout {{
  display: grid;
  grid-template-columns: var(--menu-width) minmax(0, 1fr);
  gap: var(--layout-gap);
  align-items: start;
}}

.app-sidebar {{
  background: var(--sidebar-bg);
  border: 1px solid var(--panel-border);
  border-radius: var(--radius-panel);
  box-shadow: var(--shadow-soft);
  padding: 24px 18px;
  position: sticky;
  top: 24px;
}}

.sidebar-title {{
  margin: 0 0 18px;
  color: var(--brand);
  font-size: 24px;
  font-weight: 800;
}}

.menu-section + .menu-section {{
  margin-top: 20px;
}}

.menu-section-title {{
  margin: 0 0 10px;
  color: var(--text-main);
  font-size: 15px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 10px;
}}

.menu-icon-badge {{
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 82px;
  padding: 4px 10px;
  border-radius: 999px;
  background: var(--brand-soft);
  color: var(--brand);
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.02em;
}}

.menu-list {{
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  gap: 10px;
}}

.menu-link {{
  display: block;
  border-radius: var(--radius-button);
  padding: 12px 14px;
  background: var(--panel-bg);
  border: 1px solid var(--panel-border);
  color: var(--text-main);
  font-weight: 600;
}}

.menu-link:hover {{
  border-color: var(--brand);
  background: var(--brand-soft);
}}

.content-panel {{
  background: var(--panel-bg);
  border: 1px solid var(--panel-border);
  border-radius: var(--radius-panel);
  box-shadow: var(--shadow-soft);
  padding: var(--content-padding);
  min-height: 420px;
}}

.content-panel h1,
.content-panel h2,
.content-panel h3 {{
  margin-top: 0;
  color: var(--brand);
}}

.page-header {{
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 18px;
  margin-bottom: 22px;
  padding-bottom: 18px;
  border-bottom: 2px solid var(--brand-soft);
}}

.page-header h1 {{
  margin: 0;
  font-size: clamp(28px, 3vw, 42px);
  line-height: 1.12;
  letter-spacing: -0.03em;
}}

.page-header p,
.page-header .page-lead {{
  margin: 10px 0 0;
  color: var(--text-sub);
  font-size: 15px;
  line-height: 1.65;
}}

.page-card {{
  width: 100%;
  background: var(--panel-bg);
  border: 1px solid var(--panel-border);
  border-radius: calc(var(--radius-panel) - 6px);
  padding: 22px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.05);
}}

.page-card + .page-card {{
  margin-top: 18px;
}}

.search-form {{
  display: grid;
  gap: 16px;
}}

.form-grid {{
  display: grid;
  grid-template-columns: repeat(2, minmax(220px, 1fr));
  gap: 16px 18px;
  align-items: end;
}}

.form-grid > div,
.form-row {{
  min-width: 0;
}}

.form-grid label,
.form-row label,
.search-form label {{
  display: block;
  margin-bottom: 8px;
  color: var(--text-main);
  font-size: 14px;
  font-weight: 700;
}}

.action-row {{
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
  padding-top: 2px;
}}

.content-panel table,
.content-panel ul,
.content-panel form,
.content-panel .table-wrap {{
  width: 100%;
}}

.table-wrap {{
  overflow: hidden;
  border: 1px solid var(--panel-border);
  border-radius: calc(var(--radius-panel) - 6px);
  background: var(--panel-bg);
}}

.data-table,
.content-panel table {{
  width: 100%;
  border-collapse: collapse;
  table-layout: auto;
}}

.data-table thead th,
.content-panel thead th {{
  padding: 16px 18px;
  text-align: left;
  vertical-align: middle;
  font-size: 14px;
  font-weight: 800;
  color: var(--text-main);
  background: var(--brand-soft);
  border-top: 2px solid var(--brand);
  border-bottom: 1px solid var(--panel-border);
  white-space: nowrap;
}}

.data-table tbody td,
.content-panel tbody td {{
  padding: 16px 18px;
  vertical-align: middle;
  font-size: 14px;
  color: var(--text-main);
  background: var(--panel-bg);
  border-bottom: 1px solid var(--panel-border);
  line-height: 1.55;
}}

.data-table tbody tr:hover td,
.content-panel tbody tr:hover td {{
  background: var(--sidebar-bg);
}}

.data-table tbody tr:last-child td,
.content-panel tbody tr:last-child td {{
  border-bottom: 0;
}}

.text-link {{
  color: var(--brand);
  font-weight: 700;
}}

.text-link:hover {{
  text-decoration: underline;
}}

.empty-state {{
  padding: 26px 18px !important;
  text-align: center;
  color: var(--text-sub);
  background: var(--sidebar-bg) !important;
}}

button,
.btn,
input[type='submit'],
input[type='button'] {{
  border: 0;
  border-radius: var(--radius-button);
  background: var(--brand);
  color: var(--button-text);
  padding: 12px 18px;
  font-weight: 700;
  cursor: pointer;
}}

button:hover,
.btn:hover,
input[type='submit']:hover,
input[type='button']:hover {{
  opacity: 0.95;
}}

input,
select,
textarea {{
  width: 100%;
  border: 1px solid var(--panel-border);
  border-radius: var(--radius-button);
  padding: 10px 12px;
  background: var(--panel-bg);
  color: var(--text-main);
}}

input:focus,
select:focus,
textarea:focus {{
  outline: 2px solid var(--brand-soft);
  outline-offset: 1px;
  border-color: var(--brand);
}}

th,
td {{
  border-color: var(--panel-border);
}}

@media (max-width: 960px) {{
  .page-wrap {{
    padding: var(--page-padding-mobile);
  }}
  .app-layout {{
    grid-template-columns: 1fr;
  }}
  .app-sidebar {{
    position: static;
  }}
  .page-header {{
    padding-bottom: 14px;
  }}
  .form-grid {{
    grid-template-columns: 1fr;
  }}
}}
'''


def render_react_navigation_css(style_key: str | None) -> str:
    vars_block = _css_var_lines(style_tokens(style_key))
    return f'''{vars_block}

body {{
  background: var(--app-bg);
  color: var(--text-main);
  font-family: var(--font-stack);
}}

.react-app-shell {{
  min-height: 100vh;
  display: grid;
  grid-template-columns: var(--menu-width) minmax(0, 1fr);
  gap: var(--layout-gap);
  padding: var(--page-padding);
  background: var(--app-bg);
}}

.react-app-content {{
  min-width: 0;
}}

.react-side-menu {{
  position: sticky;
  top: 24px;
  border-radius: var(--radius-panel);
  padding: 24px 18px;
  background: var(--sidebar-bg);
  border: 1px solid var(--panel-border);
  box-shadow: var(--shadow-soft);
}}

.react-side-menu__brand {{
  margin-bottom: 18px;
  color: var(--brand);
  font-size: 24px;
  font-weight: 800;
}}

.react-side-menu__section + .react-side-menu__section {{
  margin-top: 18px;
}}

.react-side-menu__title {{
  margin: 0 0 10px;
  font-size: 15px;
  color: var(--text-main);
  display: flex;
  align-items: center;
  gap: 10px;
}}

.react-side-menu__icon {{
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 82px;
  padding: 4px 10px;
  border-radius: 999px;
  background: var(--brand-soft);
  color: var(--brand);
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.02em;
}}

.react-side-menu__list {{
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  gap: 10px;
}}

.react-side-menu__link {{
  display: block;
  border-radius: var(--radius-button);
  padding: 12px 14px;
  background: var(--panel-bg);
  border: 1px solid var(--panel-border);
  color: var(--text-main);
  font-weight: 600;
  text-decoration: none;
}}

.react-side-menu__link:hover {{
  border-color: var(--brand);
  background: var(--brand-soft);
}}

.page-card,
.page-shell > .page-card {{
  border-radius: var(--radius-panel);
  background: var(--panel-bg);
  border: 1px solid var(--panel-border);
  box-shadow: var(--shadow-soft);
  color: var(--text-main);
}}

.page-header h1,
.page-card h1,
.page-card h2,
.page-card h3 {{
  color: var(--brand);
}}

button,
.btn {{
  border-radius: var(--radius-button);
  border: 0;
  background: var(--brand);
  color: var(--button-text);
}}

input,
select,
textarea {{
  border: 1px solid var(--panel-border);
  border-radius: var(--radius-button);
  background: var(--panel-bg);
  color: var(--text-main);
}}

.data-table th,
.data-table td {{
  border-color: var(--panel-border);
}}

@media (max-width: 960px) {{
  .react-app-shell {{
    grid-template-columns: 1fr;
    padding: var(--page-padding-mobile);
  }}

  .react-side-menu {{
    position: static;
  }}
}}
'''


def render_vue_menu_css(style_key: str | None) -> str:
    vars_block = _css_var_lines(style_tokens(style_key))
    return f'''{vars_block}

body {{
  background: var(--app-bg);
  color: var(--text-main);
  font-family: var(--font-stack);
}}

.vue-app-shell {{
  min-height: 100vh;
  display: grid;
  grid-template-columns: var(--menu-width) minmax(0, 1fr);
  gap: var(--layout-gap);
  padding: var(--page-padding);
  background: var(--app-bg);
}}

.vue-app-content {{
  min-width: 0;
}}

.vue-side-menu {{
  position: sticky;
  top: 24px;
  border-radius: var(--radius-panel);
  padding: 24px 18px;
  background: var(--sidebar-bg);
  border: 1px solid var(--panel-border);
  box-shadow: var(--shadow-soft);
}}

.vue-side-menu__brand {{
  margin-bottom: 18px;
  color: var(--brand);
  font-size: 24px;
  font-weight: 800;
}}

.vue-side-menu__section + .vue-side-menu__section {{
  margin-top: 18px;
}}

.vue-side-menu__title {{
  margin: 0 0 10px;
  font-size: 15px;
  color: var(--text-main);
  display: flex;
  align-items: center;
  gap: 10px;
}}

.vue-side-menu__icon {{
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 82px;
  padding: 4px 10px;
  border-radius: 999px;
  background: var(--brand-soft);
  color: var(--brand);
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.02em;
}}

.vue-side-menu__list {{
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  gap: 10px;
}}

.vue-side-menu__link {{
  display: block;
  border-radius: var(--radius-button);
  padding: 12px 14px;
  background: var(--panel-bg);
  border: 1px solid var(--panel-border);
  color: var(--text-main);
  font-weight: 600;
  text-decoration: none;
}}

.vue-side-menu__link:hover {{
  border-color: var(--brand);
  background: var(--brand-soft);
}}

.page-card,
.page-shell > .page-card {{
  border-radius: var(--radius-panel);
  background: var(--panel-bg);
  border: 1px solid var(--panel-border);
  box-shadow: var(--shadow-soft);
  color: var(--text-main);
}}

.page-header h1,
.page-card h1,
.page-card h2,
.page-card h3 {{
  color: var(--brand);
}}

button,
.btn {{
  border-radius: var(--radius-button);
  border: 0;
  background: var(--brand);
  color: var(--button-text);
}}

input,
select,
textarea {{
  border: 1px solid var(--panel-border);
  border-radius: var(--radius-button);
  background: var(--panel-bg);
  color: var(--text-main);
}}

.data-table th,
.data-table td {{
  border-color: var(--panel-border);
}}

@media (max-width: 960px) {{
  .vue-app-shell {{
    grid-template-columns: 1fr;
    padding: var(--page-padding-mobile);
  }}

  .vue-side-menu {{
    position: static;
  }}
}}
'''


def render_design_style_metadata_json(style_key: str | None) -> str:
    preset = get_style_preset(style_key)
    payload = {
        "key": preset.key,
        "label": preset.label,
        "description": preset.description,
        "tokens": style_tokens(style_key),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def render_design_style_metadata_js(style_key: str | None) -> str:
    payload = render_design_style_metadata_json(style_key).strip()
    return f"const DESIGN_STYLE = {payload};\n\nexport default DESIGN_STYLE;\n"
