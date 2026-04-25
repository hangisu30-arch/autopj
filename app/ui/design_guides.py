from __future__ import annotations

from typing import Dict

_CERTLOGIN_REFERENCE = """[REFERENCE DESIGN - EGOV CERTLOGIN INSPIRED]
- 참고 기준: eGov certlogin 계열 공통 CSS에서 추출한 톤을 따른다.
- 동일 복제는 금지하되, 다음 성격을 재해석해 반영한다.
  - 진한 블루 포인트 헤더/버튼/탭 (#0c4ca4, #3d70b6, #4688d2 계열)
  - 옅은 블루 검색 패널/업무 박스 (#eef3fb 계열)
  - 밝은 회색 보더/배경과 카드형 구획 (#d9d9d9, #f4f4f4, #f7f7f7 계열)
  - 타이틀/검색/테이블/카드/버튼이 계층적으로 구분되는 업무 시스템 스타일
  - 무거운 테이블 일변도 대신 카드, 배지, 패널, 툴바를 혼합한 풍부한 레이아웃
- JSP는 기존 common.css가 있으면 우선 유지하고, 필요한 규칙만 병합한다.
- inline style 남발 금지. 공통 CSS 또는 페이지 CSS로 정리한다.
- 반응형에서 좌우 2단 레이아웃은 1단 스택으로 자연스럽게 전환한다.
""".strip()

_STYLE_GUIDES: Dict[str, str] = {
    "simple": """[DESIGN STYLE - SIMPLE]
- 여백, 정렬, 타이포만 정돈한 절제된 업무형 UI로 구성한다.
- 색상은 중립 톤 + 1개의 포인트 색만 사용한다.
- 카드 그림자/장식은 최소화하되 밋밋하지 않게 구획은 분명히 한다.
""".strip(),
    "modern": """[DESIGN STYLE - MODERN]
- 카드형 레이아웃, 명확한 툴바, 둥근 모서리, 부드러운 그림자를 사용한다.
- 검색영역/상태영역/목록영역의 시각적 계층을 분명히 만든다.
- 버튼/배지/입력창은 통일된 컴포넌트 스타일을 사용한다.
""".strip(),
    "contemporary": """[DESIGN STYLE - CONTEMPORARY]
- 넓은 여백, 굵은 섹션 제목, 깔끔한 카드 분할, 큰 클릭 영역을 사용한다.
- 데스크톱과 모바일 모두에서 자연스럽게 읽히는 레이아웃으로 구성한다.
- 단순 박스 나열이 아니라 핵심 정보가 먼저 보이는 현대적 정보구조를 적용한다.
""".strip(),
    "portal": """[DESIGN STYLE - PORTAL]
- 공공/행정 포털형 업무 UI를 목표로 한다.
- 상단 헤더, 업무 툴바, 검색 패널, 본문 카드, 하단 액션 영역을 분명히 나눈다.
- 블루 계열 포인트와 안정적인 회색/화이트 바탕을 사용한다.
""".strip(),
    "executive": """[DESIGN STYLE - EXECUTIVE]
- 임원 대시보드/업무 포털처럼 정돈되고 고급스러운 업무 화면을 만든다.
- 진한 네이비/블루 포인트, 옅은 배경, 강한 타이틀 대비를 사용한다.
- 핵심 액션 버튼과 상태 배지를 눈에 띄게 배치한다.
""".strip(),
    "rich": """[DESIGN STYLE - RICH]
- 카드, 배지, 요약박스, 빈 상태, 툴바, 필터 영역을 적극적으로 사용한다.
- 화면이 빈약해 보이지 않도록 섹션별 시각 장치를 충분히 넣는다.
- 단, 과한 그래픽보다 업무 시스템에서 바로 쓸 수 있는 정돈된 풍부함을 우선한다.
""".strip(),
}

_SHARED_GUIDE = """[DESIGN IMPLEMENTATION RULES]
- 디자인만 설명하지 말고 실제 JSP/HTML/CSS 구조에 반영한다.
- 폼, 목록, 상세, 빈 상태, 검색 패널, 버튼, 배지 스타일을 모두 정의한다.
- JSP에서는 공통 자산(common.css 등)이 있으면 유지/병합하고, 없으면 공통 CSS 파일을 생성한다.
- 일정/대시보드/포털형 화면은 table만으로 끝내지 말고 카드, 패널, 배지를 사용한다.
- 모바일에서는 툴바, 검색조건, 2단 패널, 카드 목록이 세로로 자연스럽게 정렬되어야 한다.
""".strip()


def build_design_guidance(style_key: str, design_url: str = "") -> str:
    key = (style_key or "simple").strip().lower()
    style_block = _STYLE_GUIDES.get(key, _STYLE_GUIDES["simple"])
    url_block = ""
    if design_url:
        url_block = (
            "[DESIGN URL USAGE]\n"
            f"- 디자인 URL 참고: {design_url}\n"
            "- 레이아웃 분위기, 섹션 구성, 간격 체계, 버튼/카드 톤만 참고한다.\n"
            "- 브랜드/로고/문구/이미지/저작물은 복사하지 않는다.\n"
        ).strip()
    blocks = [_CERTLOGIN_REFERENCE, style_block, _SHARED_GUIDE]
    if url_block:
        blocks.append(url_block)
    return "\n\n".join(blocks)
