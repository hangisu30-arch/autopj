from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
import tinycss2

_CACHE_TTL_SECONDS = 60 * 60 * 6
_MAX_STYLESHEETS = 8
_MAX_CSS_BYTES = 350_000
_USER_AGENT = "autopj-design-reference/1.0"

_COLOR_RE = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b|rgba?\([^\)]*\)|hsla?\([^\)]*\)")
_PX_RE = re.compile(r"(-?\d+(?:\.\d+)?)px")
_REM_RE = re.compile(r"(-?\d+(?:\.\d+)?)rem")
_FONT_FAMILY_RE = re.compile(r"font-family\s*:\s*([^;}{]+)", re.IGNORECASE)
_BOX_SHADOW_RE = re.compile(r"box-shadow\s*:\s*([^;}{]+)", re.IGNORECASE)
_MAX_WIDTH_RE = re.compile(r"max-width\s*:\s*([^;}{]+)", re.IGNORECASE)
_BREAKPOINT_RE = re.compile(r"@media[^\{]*max-width\s*:\s*(\d+)px", re.IGNORECASE)
_RADIUS_DECL_RE = re.compile(r"border-radius\s*:\s*([^;}{]+)", re.IGNORECASE)
_DECL_RE = re.compile(r"([a-zA-Z-]+)\s*:\s*([^;}{]+)")

_COMPONENT_PATTERNS = {
    "button": re.compile(r"(?:^|[\s>+~.,:#])(?:button|\.btn|\.button|\[type=['\"]?button|\[type=['\"]?submit)", re.IGNORECASE),
    "input": re.compile(r"(?:^|[\s>+~.,:#])(?:input|select|textarea|\.input|\.form-control)", re.IGNORECASE),
    "table": re.compile(r"(?:^|[\s>+~.,:#])(?:table|\.table|\.grid)", re.IGNORECASE),
    "nav": re.compile(r"(?:^|[\s>+~.,:#])(?:nav|\.nav|header|\.menu|\.navbar|aside|\.sidebar)", re.IGNORECASE),
    "card": re.compile(r"(?:^|[\s>+~.,:#])(?:\.card|\.panel|\.box|\.tile|section|article)", re.IGNORECASE),
    "badge": re.compile(r"(?:^|[\s>+~.,:#])(?:\.badge|\.tag|\.chip|\.pill)", re.IGNORECASE),
}


@dataclass
class DesignReferenceProfile:
    source_url: str = ""
    fetched_at_epoch: float = 0.0
    page_title: str = ""
    stylesheet_urls: List[str] = field(default_factory=list)
    colors: List[str] = field(default_factory=list)
    fonts: List[str] = field(default_factory=list)
    spacing_px: List[int] = field(default_factory=list)
    radius_px: List[int] = field(default_factory=list)
    shadows: List[str] = field(default_factory=list)
    max_widths: List[str] = field(default_factory=list)
    breakpoints_px: List[int] = field(default_factory=list)
    component_styles: Dict[str, Dict[str, str]] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)
    fetch_error: str = ""

    def is_usable(self) -> bool:
        return bool(self.source_url and (self.colors or self.fonts or self.component_styles)) and not self.fetch_error

    def theme_vars(self) -> Dict[str, str]:
        colors = self.colors or []
        primary = colors[0] if len(colors) > 0 else "#1f4fbf"
        secondary = colors[1] if len(colors) > 1 else "#173a8f"
        accent = colors[2] if len(colors) > 2 else "#f4a000"
        bg = colors[3] if len(colors) > 3 else "#f4f6fb"
        surface = "#ffffff"
        border = colors[4] if len(colors) > 4 else "#d8e1ef"
        text = "#1f2a37"
        muted = "#637287"
        radius = self.radius_px[0] if self.radius_px else 14
        radius_sm = max(8, min(radius, 12))
        radius_lg = min(max(radius + 6, 16), 28)
        shadow = self.shadows[0] if self.shadows else "0 10px 30px rgba(15, 23, 42, 0.08)"
        font = self.fonts[0] if self.fonts else "Arial, Helvetica, sans-serif"
        container = self.max_widths[0] if self.max_widths else "1280px"
        mobile = self.breakpoints_px[0] if self.breakpoints_px else 768
        return {
            "font": font,
            "bg": bg,
            "surface": surface,
            "border": border,
            "text": text,
            "muted": muted,
            "primary": primary,
            "secondary": secondary,
            "accent": accent,
            "radius_sm": f"{radius_sm}px",
            "radius_md": f"{radius}px",
            "radius_lg": f"{radius_lg}px",
            "shadow": shadow,
            "container": container,
            "mobile_breakpoint": f"{mobile}px",
        }


def _cache_dir() -> str:
    root = os.path.join(tempfile.gettempdir(), "autopj_design_reference_cache")
    os.makedirs(root, exist_ok=True)
    return root


def _cache_path(url: str) -> str:
    key = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return os.path.join(_cache_dir(), f"{key}.json")


def _normalize_url(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    if raw.startswith("//"):
        raw = f"https:{raw}"
    elif not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", raw):
        raw = f"https://{raw}"
    return raw


def _load_cached_profile(url: str) -> Optional[DesignReferenceProfile]:
    path = _cache_path(url)
    if not os.path.exists(path):
        return None
    try:
        data = json.loads(open(path, "r", encoding="utf-8").read())
        fetched = float(data.get("fetched_at_epoch") or 0.0)
        if time.time() - fetched > _CACHE_TTL_SECONDS:
            return None
        return DesignReferenceProfile(**data)
    except Exception:
        return None


def _store_cached_profile(profile: DesignReferenceProfile) -> None:
    if not profile.source_url:
        return
    path = _cache_path(profile.source_url)
    try:
        with open(path, "w", encoding="utf-8") as fp:
            json.dump(asdict(profile), fp, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _fetch_text(url: str, timeout: float = 8.0) -> str:
    headers = {"User-Agent": _USER_AGENT, "Accept": "text/html,text/css,*/*;q=0.8"}
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    resp.encoding = resp.encoding or resp.apparent_encoding or "utf-8"
    body = resp.text or ""
    if len(body.encode("utf-8", errors="ignore")) > _MAX_CSS_BYTES:
        body = body[:_MAX_CSS_BYTES]
    return body


def _normalize_color(value: str) -> str:
    v = str(value or "").strip()
    if not v:
        return ""
    if v.startswith("#"):
        if len(v) == 4:
            return "#" + "".join(ch * 2 for ch in v[1:]).lower()
        return v.lower()
    return re.sub(r"\s+", " ", v.lower())


def _css_texts_from_html(page_url: str, html: str) -> Tuple[List[str], List[str], str]:
    soup = BeautifulSoup(html or "", "lxml")
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
    css_texts: List[str] = []
    style_urls: List[str] = []
    for tag in soup.find_all("style"):
        text = tag.get_text("\n", strip=False)
        if text and text.strip():
            css_texts.append(text)
    seen: set[str] = set()
    for link in soup.find_all("link"):
        rel = " ".join(link.get("rel") or []).lower()
        href = (link.get("href") or "").strip()
        if not href or "stylesheet" not in rel:
            continue
        absolute = urljoin(page_url, href)
        if absolute in seen:
            continue
        seen.add(absolute)
        style_urls.append(absolute)
        if len(style_urls) >= _MAX_STYLESHEETS:
            break
    for css_url in style_urls:
        try:
            css_texts.append(_fetch_text(css_url, timeout=8.0))
        except Exception:
            continue
    return css_texts, style_urls, title


def _number_samples(text: str, regex: re.Pattern[str], *, rem_scale: int = 16) -> List[int]:
    out: List[int] = []
    for raw in regex.findall(text or ""):
        try:
            value = float(raw)
            px = int(round(value * rem_scale)) if regex is _REM_RE else int(round(value))
            if px >= 0:
                out.append(px)
        except Exception:
            continue
    return out


def _top_values(counter: Counter, limit: int) -> List[str]:
    return [item for item, _count in counter.most_common(limit) if item]


def _compact_selector(selector: str) -> str:
    return re.sub(r"\s+", " ", str(selector or "").strip())[:120]


def _extract_component_styles(css_texts: List[str]) -> Dict[str, Dict[str, str]]:
    result: Dict[str, Dict[str, str]] = {}
    for css in css_texts:
        try:
            rules = tinycss2.parse_stylesheet(css, skip_comments=True, skip_whitespace=True)
        except Exception:
            continue
        for rule in rules:
            if getattr(rule, "type", "") != "qualified-rule":
                continue
            selector = tinycss2.serialize(getattr(rule, "prelude", [])).strip()
            declarations = tinycss2.serialize(getattr(rule, "content", [])).strip()
            if not selector or not declarations:
                continue
            for name, pattern in _COMPONENT_PATTERNS.items():
                if name in result:
                    continue
                if not pattern.search(selector):
                    continue
                props: Dict[str, str] = {"selector": _compact_selector(selector)}
                for key, value in _DECL_RE.findall(declarations):
                    prop = key.strip().lower()
                    val = re.sub(r"\s+", " ", value.strip())
                    if prop in {"background", "background-color", "color", "border", "border-radius", "box-shadow", "padding", "gap", "font-size", "font-weight"} and prop not in props:
                        props[prop] = val
                result[name] = props
    return result


def _build_profile(url: str, html: str, css_texts: List[str], stylesheet_urls: List[str], title: str) -> DesignReferenceProfile:
    css_blob = "\n\n".join(css_texts)
    colors = Counter(_normalize_color(c) for c in _COLOR_RE.findall(css_blob))
    fonts = Counter()
    for raw in _FONT_FAMILY_RE.findall(css_blob):
        families = [re.sub(r"['\"]", "", part.strip()) for part in raw.split(",")]
        for family in families:
            if family and family.lower() not in {"inherit", "initial", "unset"}:
                fonts[family] += 1
    radii = Counter(v for v in _number_samples(css_blob, _PX_RE) if 2 <= v <= 40)
    spacing = Counter(v for v in (_number_samples(css_blob, _PX_RE) + _number_samples(css_blob, _REM_RE)) if 4 <= v <= 80)
    shadows = Counter(re.sub(r"\s+", " ", s.strip()) for s in _BOX_SHADOW_RE.findall(css_blob) if s.strip())
    max_widths = Counter(re.sub(r"\s+", " ", s.strip()) for s in _MAX_WIDTH_RE.findall(css_blob) if s.strip())
    breakpoints = Counter(int(v) for v in _BREAKPOINT_RE.findall(css_blob) if v)
    if not radii:
        for raw in _RADIUS_DECL_RE.findall(css_blob):
            radii.update(v for v in _number_samples(raw, _PX_RE) if 2 <= v <= 40)
            radii.update(v for v in _number_samples(raw, _REM_RE) if 2 <= v <= 40)

    notes: List[str] = []
    if breakpoints:
        notes.append(f"대표 모바일 breakpoint는 {next(iter(breakpoints))}px 부근이다.")
    if max_widths:
        notes.append(f"콘텐츠 최대 폭은 {max_widths.most_common(1)[0][0]} 부근이다.")
    if fonts:
        notes.append(f"주요 폰트 계열은 {fonts.most_common(1)[0][0]} 이다.")

    return DesignReferenceProfile(
        source_url=url,
        fetched_at_epoch=time.time(),
        page_title=title,
        stylesheet_urls=stylesheet_urls,
        colors=_top_values(colors, 6),
        fonts=_top_values(fonts, 4),
        spacing_px=[value for value, _count in spacing.most_common(8)],
        radius_px=[value for value, _count in radii.most_common(6)],
        shadows=_top_values(shadows, 4),
        max_widths=_top_values(max_widths, 4),
        breakpoints_px=[value for value, _count in breakpoints.most_common(4)],
        component_styles=_extract_component_styles(css_texts),
        notes=notes,
    )


def get_design_reference_profile(design_url: str, *, force_refresh: bool = False) -> Optional[DesignReferenceProfile]:
    url = _normalize_url(design_url)
    if not url:
        return None
    if not force_refresh:
        cached = _load_cached_profile(url)
        if cached is not None:
            return cached
    try:
        html = _fetch_text(url, timeout=10.0)
        css_texts, stylesheet_urls, title = _css_texts_from_html(url, html)
        profile = _build_profile(url, html, css_texts, stylesheet_urls, title)
        if not profile.colors and not profile.fonts and not profile.component_styles:
            profile.fetch_error = "no_design_tokens_detected"
        _store_cached_profile(profile)
        return profile
    except Exception as exc:
        profile = DesignReferenceProfile(source_url=url, fetched_at_epoch=time.time(), fetch_error=str(exc))
        _store_cached_profile(profile)
        return profile


def build_precise_design_reference_block(design_url: str) -> str:
    profile = get_design_reference_profile(design_url)
    if profile is None:
        return ""
    if profile.fetch_error:
        return "\n".join([
            "[DESIGN REFERENCE ANALYSIS - PRECISE MODE]",
            f"- 디자인 URL: {profile.source_url}",
            f"- 정밀 분석 실패: {profile.fetch_error}",
            "- 실패 시에도 URL의 화면 구조를 참고 대상으로 유지하되, CSS는 토큰 기반으로 새로 생성한다.",
            "- 브랜드 자산/문구/이미지/로고는 복제하지 않는다.",
        ])
    vars_map = profile.theme_vars()
    lines: List[str] = [
        "[DESIGN REFERENCE ANALYSIS - PRECISE MODE]",
        f"- 디자인 URL: {profile.source_url}",
        f"- 페이지 제목: {profile.page_title or '(unknown)'}",
        f"- 연결 stylesheet 수: {len(profile.stylesheet_urls)}",
        f"- 대표 색상: {', '.join(profile.colors[:6]) or '(none)'}",
        f"- 대표 폰트: {', '.join(profile.fonts[:4]) or '(none)'}",
        f"- 대표 radius(px): {', '.join(str(v) for v in profile.radius_px[:6]) or '(none)'}",
        f"- 대표 spacing(px): {', '.join(str(v) for v in profile.spacing_px[:8]) or '(none)'}",
        f"- 대표 shadow: {', '.join(profile.shadows[:3]) or '(none)'}",
        f"- 대표 max-width: {', '.join(profile.max_widths[:3]) or '(none)'}",
        f"- 대표 breakpoint(px): {', '.join(str(v) for v in profile.breakpoints_px[:4]) or '(none)'}",
        "- 아래 토큰을 기준으로 JSP/React/Vue/Nexacro 공통 스타일을 새로 생성한다.",
        f"- theme.font = {vars_map['font']}",
        f"- theme.primary = {vars_map['primary']}",
        f"- theme.secondary = {vars_map['secondary']}",
        f"- theme.accent = {vars_map['accent']}",
        f"- theme.background = {vars_map['bg']}",
        f"- theme.border = {vars_map['border']}",
        f"- theme.radius.md = {vars_map['radius_md']}",
        f"- theme.shadow = {vars_map['shadow']}",
        f"- theme.contentMax = {vars_map['container']}",
        f"- theme.mobileBreakpoint = {vars_map['mobile_breakpoint']}",
    ]
    for component, props in sorted((profile.component_styles or {}).items()):
        if not props:
            continue
        detail = ", ".join(f"{k}={v}" for k, v in props.items() if k != "selector")
        selector = props.get("selector") or component
        lines.append(f"- {component} style hint: selector={selector}; {detail}".rstrip())
    lines.append("- 원본 CSS selector/문구를 복제하지 말고, 추출한 토큰과 컴포넌트 힌트를 바탕으로 재구성한다.")
    return "\n".join(lines)


__all__ = [
    "DesignReferenceProfile",
    "get_design_reference_profile",
    "build_precise_design_reference_block",
]
