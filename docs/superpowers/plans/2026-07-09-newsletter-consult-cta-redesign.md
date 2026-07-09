# 상담 전환형 토스풍 리디자인 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 웹 뉴스레터(v2)를 토스풍 모바일 우선 디자인으로 개편하고, 브랜드라이즈 무료 상담 CTA를 상단 진입점 + 하단 강한 블록 2단으로 강화한다.

**Architecture:** `html_formatter_v2.py`가 단일 산출물. 순수 문자열 렌더 함수(테스트 가능)를 먼저 바꾸고, 그다음 `CSS_V2` 전면 교체 + 셸(`build_html_v2`) 재작성으로 조립. 이미지 톤은 `image_gen.py`의 `STYLE_PREFIX/SUFFIX` 교체, 카톡 카피는 `formatter.py` 상수 교체.

**Tech Stack:** Python 3, BeautifulSoup(수집), 순수 f-string HTML/CSS, pytest, Pretendard(CDN), Gemini/Pollinations(이미지).

## Global Constraints

- 색 토큰(정확값): `--card:#FFFFFF` `--ground:#F2F4F6` `--ink:#191F28` `--ink2:#4E5968` `--ink3:#6B7684` `--gray:#8B95A1` `--line:#E5E8EB` `--accent:#3182F6` `--accent-d:#1B64DA` `--accent-soft:#E8F1FE`.
- 폰트: Pretendard CDN(`https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css`) + 폴백 `'Apple SD Gothic Neo','Malgun Gothic',-apple-system,sans-serif`. 기존 Noto Sans KR 링크 제거.
- 한국어 줄바꿈: `word-break: keep-all` 전면.
- 모바일 우선: `.v2-wrapper max-width:480px`. 라이트 단일 테마.
- 상담 폼 URL: 웹=`utm_source=web&utm_medium=cta&utm_campaign=brandrise&utm_content={top|bottom}`, 카톡=`utm_source=kakao&utm_medium=organic&utm_campaign=brandrise`. HTML 속성에서는 `&`를 `&amp;`로.
- 하단 CTA 카피(줄바꿈 고정): 헤드라인 `혼자 고민하지 마세요.` / 본문 `브랜드 진단부터 지금 당장 해야 할 우선순위까지,`⏎`30분 무료 상담에서 함께 정리해드려요.` / 증거 `이미 **수십 개 브랜드**가 상담받았습니다.`⏎`내 브랜드처럼, 함께 고민하는 팀원의 마음으로 봅니다.` / 버튼 `30분 무료 상담받기 →` / 미세문구 `스타트업 대표·마케팅 담당자를 위한 30분`.
- 사회적 증거는 "수십 개" 규모감만. 수치·후기·긴박감 날조 금지.
- Windows: 스크립트 실행 시 `sys.stdout.reconfigure(encoding='utf-8')`, 파일 I/O `encoding='utf-8'`.

---

### Task 1: 아이보스 뉴스 — 썸네일 리스트 + 클릭 링크

기존 2열 그리드(`_render_iboss_v2`)를 전체 균일 썸네일 리스트로 바꾸고, 각 행을 `item.url`로 가는 링크로 만든다.

**Files:**
- Modify: `html_formatter_v2.py` (`_render_iboss_v2`, 현재 64-95행)
- Test: `tests/test_html_formatter_v2.py` (신규)

**Interfaces:**
- Consumes: `NewsItem(title:str, summary:str, url:str)` (collectors/iboss.py), `image_map: dict[int,str]`(1-기반 index→이미지 경로), `_esc()`, `_get_theme()`.
- Produces: `_render_iboss_v2(items: List[NewsItem], post_url: str="", image_map: dict=None) -> str` — `.v2-newslist` 안에 `.v2-item` 링크들.

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_html_formatter_v2.py` 생성:

```python
# -*- coding: utf-8 -*-
from collectors.iboss import NewsItem
import html_formatter_v2 as H


def _items():
    return [
        NewsItem(title="네이버 플레이스광고 확대", summary="최대 18개로", url="https://ex.com/a1"),
        NewsItem(title="생성형 AI 검색", summary="챗GPT 4위", url="https://ex.com/a2"),
    ]


def test_iboss_items_are_clickable_links():
    html = H._render_iboss_v2(_items(), post_url="https://iboss.example/post")
    assert 'href="https://ex.com/a1"' in html
    assert 'href="https://ex.com/a2"' in html
    assert html.count('class="v2-item"') == 2
    assert 'v2-item-rank' in html  # 순위 배지


def test_iboss_falls_back_to_post_url_when_item_url_empty():
    items = [NewsItem(title="제목", summary="요약", url="")]
    html = H._render_iboss_v2(items, post_url="https://iboss.example/post")
    assert 'href="https://iboss.example/post"' in html


def test_iboss_uses_thumbnail_when_image_map_given():
    html = H._render_iboss_v2(_items(), image_map={1: "images/x/iboss-1.png"})
    assert 'src="images/x/iboss-1.png"' in html
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_html_formatter_v2.py -v`
Expected: FAIL (`v2-item` 미포함 — 기존은 `v2-yt-card` 그리드).

- [ ] **Step 3: `_render_iboss_v2` 교체**

`html_formatter_v2.py`의 기존 `_render_iboss_v2`(64-95행)를 아래로 교체:

```python
def _render_iboss_v2(items: List[NewsItem], post_url: str = "", image_map: dict = None) -> str:
    if not items:
        return ""
    rows = ""
    for i, item in enumerate(items, 1):
        if image_map and i in image_map:
            thumb = f'<img class="v2-item-thumb" src="{image_map[i]}" alt="" loading="lazy">'
        else:
            gradient, emoji = _get_theme(item.title)
            thumb = (f'<span class="v2-item-thumb v2-item-thumb-grad" '
                     f'style="background:linear-gradient({gradient})">{emoji}</span>')
        summary = f'<p>{_esc(item.summary)}</p>' if item.summary else ""
        href = item.url or post_url or "#"
        rows += f"""
        <a class="v2-item" href="{_esc(href)}" target="_blank" rel="noopener">
            <span class="v2-item-thumbwrap">{thumb}<span class="v2-item-rank">{i}</span></span>
            <span class="v2-item-body"><h3>{_esc(item.title)}</h3>{summary}</span>
            <span class="v2-item-chev">›</span>
        </a>"""
    return f"""
    <div class="v2-card">
        <div class="v2-card-header">
            <span class="v2-card-icon">📰</span>
            <div>
                <div class="v2-card-title">오늘의 마케팅 뉴스</div>
                <div class="v2-card-source">아이보스 · 클릭하면 원문</div>
            </div>
        </div>
        <div class="v2-newslist">{rows}</div>
    </div>"""
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_html_formatter_v2.py -v`
Expected: PASS (3건).

- [ ] **Step 5: 커밋**

```bash
git add html_formatter_v2.py tests/test_html_formatter_v2.py
git commit -m "feat: 아이보스 뉴스 썸네일 리스트 + 기사별 클릭 링크"
```

---

### Task 2: 하단 상담 CTA 재작성

기존 `BRANDRISE_CTA_HTML`(483-495행)을 새 카피·줄바꿈·UTM(bottom)·토스 블루 블록으로 교체.

**Files:**
- Modify: `html_formatter_v2.py` (`BRANDRISE_CTA_HTML`)
- Test: `tests/test_html_formatter_v2.py`

**Interfaces:**
- Produces: `BRANDRISE_CTA_HTML: str` — `.v2-cta` 블록. `build_html_v2`가 삽입.

- [ ] **Step 1: 실패 테스트 추가**

`tests/test_html_formatter_v2.py`에 추가:

```python
def test_bottom_cta_copy_and_utm():
    cta = H.BRANDRISE_CTA_HTML
    assert "혼자 고민하지 마세요." in cta
    assert "30분 무료 상담에서 함께 정리해드려요." in cta
    assert "이미 <b>수십 개 브랜드</b>가 상담받았습니다." in cta
    assert "함께 고민하는 팀원의 마음으로 봅니다." in cta
    assert "utm_source=web" in cta
    assert "utm_content=bottom" in cta
    assert "utm_source=kakao" not in cta  # 웹 링크가 kakao로 오집계되던 버그 제거
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_html_formatter_v2.py::test_bottom_cta_copy_and_utm -v`
Expected: FAIL.

- [ ] **Step 3: `BRANDRISE_CTA_HTML` 교체**

```python
BRANDRISE_CTA_HTML = (
    '<div class="v2-cta">'
    '<div class="v2-cta-label">브랜드라이즈 무료 상담</div>'
    '<div class="v2-cta-headline">혼자 고민하지 마세요.</div>'
    '<p class="v2-cta-sub">브랜드 진단부터 지금 당장 해야 할 우선순위까지,<br>'
    '30분 무료 상담에서 함께 정리해드려요.</p>'
    '<p class="v2-cta-proof">이미 <b>수십 개 브랜드</b>가 상담받았습니다.<br>'
    '내 브랜드처럼, 함께 고민하는 팀원의 마음으로 봅니다.</p>'
    '<a class="v2-cta-btn" '
    'href="https://forms.gle/R5FaijsFD4VoTEsj9?utm_source=web&amp;utm_medium=cta&amp;utm_campaign=brandrise&amp;utm_content=bottom" '
    'target="_blank" rel="noopener">30분 무료 상담받기 →</a>'
    '<p class="v2-cta-fine">스타트업 대표·마케팅 담당자를 위한 30분</p>'
    '</div>'
)
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_html_formatter_v2.py::test_bottom_cta_copy_and_utm -v`
Expected: PASS.

- [ ] **Step 5: 커밋**

```bash
git add html_formatter_v2.py tests/test_html_formatter_v2.py
git commit -m "feat: 하단 상담 CTA 재작성(새 카피·UTM 분리)"
```

---

### Task 3: 상단 상담 진입점 신규

인사말 바로 아래에 들어갈 슬림 진입점 상수. UTM(top).

**Files:**
- Modify: `html_formatter_v2.py` (신규 상수 `BRANDRISE_ENTRY_HTML`)
- Test: `tests/test_html_formatter_v2.py`

**Interfaces:**
- Produces: `BRANDRISE_ENTRY_HTML: str` — `.v2-entry` 블록. Task 4의 `build_html_v2`가 헤더 다음에 삽입.

- [ ] **Step 1: 실패 테스트 추가**

```python
def test_top_entry_utm_and_copy():
    entry = H.BRANDRISE_ENTRY_HTML
    assert "utm_content=top" in entry
    assert "utm_source=web" in entry
    assert "막막하다면" in entry
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_html_formatter_v2.py::test_top_entry_utm_and_copy -v`
Expected: FAIL (`AttributeError: module ... has no attribute 'BRANDRISE_ENTRY_HTML'`).

- [ ] **Step 3: 상수 추가**

`BRANDRISE_CTA_HTML` 정의 바로 위에 추가:

```python
BRANDRISE_ENTRY_HTML = (
    '<div class="v2-entry">'
    '<a href="https://forms.gle/R5FaijsFD4VoTEsj9?utm_source=web&amp;utm_medium=cta&amp;utm_campaign=brandrise&amp;utm_content=top" '
    'target="_blank" rel="noopener">'
    '<span class="v2-entry-ico">💬</span>'
    '<span class="v2-entry-txt"><b>브랜딩·마케팅, 어디서부터 막막하다면</b>'
    '<span>30분 무료 상담으로 방향부터 잡아보세요</span></span>'
    '<span class="v2-entry-go">상담 →</span>'
    '</a></div>'
)
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_html_formatter_v2.py::test_top_entry_utm_and_copy -v`
Expected: PASS.

- [ ] **Step 5: 커밋**

```bash
git add html_formatter_v2.py tests/test_html_formatter_v2.py
git commit -m "feat: 상단 상담 진입점 컴포넌트 추가"
```

---

### Task 4: CSS 전면 교체(토스 토큰·Pretendard) + 셸 재작성

`CSS_V2`를 토스 토큰 기반으로 전면 교체하고, `build_html_v2`의 외곽 셸을 단일 페이퍼 구조(brandbar/header/entry/sections/cta/footer)로 재작성. Pretendard CDN 적용.

**Files:**
- Modify: `html_formatter_v2.py` (`CSS_V2` 261-473행, `build_html_v2` 498-583행)
- Test: `tests/test_html_formatter_v2.py`

**Interfaces:**
- Consumes: `BRANDRISE_ENTRY_HTML`, `BRANDRISE_CTA_HTML`, 각 `_render_*` 함수, `_esc`.
- Produces: `build_html_v2(...) -> str` (시그니처 불변) — Pretendard 링크, 토큰 CSS, entry/cta 포함.

- [ ] **Step 1: 실패 테스트 추가**

```python
from collectors.iboss import NewsItem

def test_build_uses_pretendard_and_tokens():
    html = H.build_html_v2([], [], [], None, [], greeting="안녕하세요! 테스트입니다.")
    assert "pretendard" in html.lower()
    assert "Noto+Sans+KR" not in html
    assert "--accent:#3182f6" in html.replace(" ", "").lower() or "--accent: #3182f6" in html.lower()
    assert "word-break:keep-all" in html.replace(" ", "").lower()

def test_build_includes_entry_and_cta():
    html = H.build_html_v2([], [], [], None, [], greeting="안녕하세요!")
    assert "utm_content=top" in html
    assert "utm_content=bottom" in html
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_html_formatter_v2.py -k "pretendard or entry_and_cta" -v`
Expected: FAIL.

- [ ] **Step 3: `CSS_V2` 교체**

`CSS_V2 = """ ... """`(261-473행) 전체를 아래로 교체:

```python
CSS_V2 = """
:root{
  --card:#fff;--ground:#f2f4f6;--ink:#191f28;--ink2:#4e5968;--ink3:#6b7684;
  --gray:#8b95a1;--line:#e5e8eb;--accent:#3182f6;--accent-d:#1b64da;--accent-soft:#e8f1fe;
  --font:'Pretendard','Pretendard Variable','Apple SD Gothic Neo','Malgun Gothic',
         -apple-system,BlinkMacSystemFont,system-ui,sans-serif;
}
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:var(--font);background:var(--ground);color:var(--ink);line-height:1.7;
     word-break:keep-all;-webkit-font-smoothing:antialiased;}
a{color:inherit;text-decoration:none;}
img{display:block;max-width:100%;}
.v2-wrapper{max-width:480px;margin:0 auto;padding:20px 12px 56px;}
.v2-topnav{text-align:right;margin-bottom:12px;}
.v2-topnav a{font-size:12px;color:var(--ink3);border:1px solid var(--line);padding:6px 14px;border-radius:20px;}

.v2-paper{background:var(--card);border-radius:22px;overflow:hidden;
          box-shadow:0 1px 2px rgba(23,31,40,.05),0 10px 34px rgba(23,31,40,.10);}
.v2-brandbar{display:flex;align-items:center;justify-content:space-between;padding:16px 20px;border-bottom:1px solid var(--line);}
.v2-brand{display:flex;align-items:center;gap:7px;font-weight:800;font-size:15px;letter-spacing:-.01em;}
.v2-brand-dot{width:8px;height:8px;border-radius:50%;background:var(--accent);}
.v2-brand-date{font-size:12.5px;color:var(--gray);font-variant-numeric:tabular-nums;}

.v2-header{padding:30px 20px 26px;}
.v2-eyebrow{font-size:12px;font-weight:800;letter-spacing:.11em;text-transform:uppercase;color:var(--accent);margin-bottom:12px;}
.v2-header-title{font-size:26px;line-height:1.34;font-weight:800;letter-spacing:-.035em;margin-bottom:16px;text-wrap:balance;}
.v2-greeting{font-size:15px;line-height:1.72;color:var(--ink2);}
.v2-greeting p{margin-bottom:12px;}
.v2-greeting p:last-child{margin-bottom:0;color:var(--ink);font-weight:600;}

.v2-entry{margin:20px 20px 0;}
.v2-entry a{display:flex;align-items:center;gap:12px;background:var(--ground);border-radius:16px;padding:15px 16px;min-height:60px;}
.v2-entry-ico{flex:none;width:42px;height:42px;border-radius:12px;background:var(--accent-soft);display:grid;place-items:center;font-size:20px;}
.v2-entry-txt{flex:1;min-width:0;}
.v2-entry-txt b{display:block;font-size:14.5px;font-weight:700;letter-spacing:-.01em;}
.v2-entry-txt span{display:block;font-size:12.5px;color:var(--ink3);margin-top:2px;}
.v2-entry-go{flex:none;font-size:14px;font-weight:800;color:var(--accent);}

.v2-card{padding:34px 20px 0;}
.v2-card-header{display:flex;align-items:center;gap:10px;margin-bottom:14px;}
.v2-card-icon{font-size:18px;flex:none;}
.v2-card-title{font-size:18px;font-weight:800;letter-spacing:-.02em;}
.v2-card-source{font-size:12px;color:var(--gray);margin-top:1px;}
.v2-source-link{margin-left:auto;font-size:12px;color:var(--accent);white-space:nowrap;}

.v2-newslist{display:flex;flex-direction:column;gap:2px;}
.v2-item{display:flex;align-items:center;gap:14px;padding:12px 8px;border-radius:16px;transition:background .15s;}
.v2-item:hover{background:var(--ground);}
.v2-item-thumbwrap{position:relative;flex:none;}
.v2-item-thumb{width:84px;height:84px;border-radius:15px;object-fit:cover;background:var(--ground);}
.v2-item-thumb-grad{display:flex;align-items:center;justify-content:center;font-size:34px;}
.v2-item-rank{position:absolute;top:6px;left:6px;background:rgba(25,31,40,.7);color:#fff;
              font-size:11px;font-weight:800;padding:2px 7px;border-radius:8px;font-variant-numeric:tabular-nums;}
.v2-item-body{flex:1;min-width:0;}
.v2-item-body h3{font-size:15.5px;line-height:1.44;font-weight:700;letter-spacing:-.015em;margin-bottom:5px;
                 display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}
.v2-item-body p{font-size:13px;line-height:1.5;color:var(--ink3);
                display:-webkit-box;-webkit-line-clamp:1;-webkit-box-orient:vertical;overflow:hidden;}
.v2-item-chev{flex:none;color:var(--gray);font-size:22px;line-height:1;}

.v2-neu-section{display:flex;flex-direction:column;}
.v2-neu-row{display:flex;align-items:flex-start;gap:16px;padding:13px 0;border-bottom:1px solid var(--line);}
.v2-neu-row:last-child{border-bottom:none;}
.v2-neu-label{display:flex;flex-direction:column;align-items:center;gap:5px;width:56px;flex-shrink:0;}
.v2-neu-emoji{font-size:24px;line-height:1;}
.v2-neu-cat{font-size:10px;font-weight:700;color:var(--gray);text-align:center;word-break:keep-all;}
.v2-neu-list{list-style:none;flex:1;display:flex;flex-direction:column;gap:6px;}
.v2-neu-item{font-size:13px;color:var(--ink2);line-height:1.55;padding-left:12px;position:relative;}
.v2-neu-item::before{content:"·";position:absolute;left:2px;color:var(--gray);font-weight:700;}

.v2-heypop-list{display:flex;flex-direction:column;gap:10px;}
.v2-heypop-card{display:flex;border-radius:16px;overflow:hidden;background:var(--ground);}
.v2-thumb{width:120px;height:96px;object-fit:contain;background:#fff;flex-shrink:0;}
.v2-thumb-placeholder{width:120px;height:96px;display:flex;align-items:center;justify-content:center;font-size:32px;background:#fff;flex-shrink:0;}
.v2-heypop-info{padding:14px 16px;display:flex;flex-direction:column;justify-content:center;gap:5px;min-width:0;}
.v2-heypop-title{font-size:14px;font-weight:700;line-height:1.45;}
.v2-heypop-desc{font-size:12.5px;color:var(--ink3);line-height:1.5;}
.v2-heypop-cta{font-size:11.5px;color:var(--accent);font-weight:700;margin-top:2px;}

.v2-stibee-list{display:flex;flex-direction:column;gap:10px;}
.v2-stibee-card{display:flex;flex-direction:column;gap:6px;padding:16px 18px;background:var(--ground);border-radius:16px;overflow:hidden;}
.v2-stibee-card-img{flex-direction:row;padding:0;gap:0;}
.v2-stibee-thumb{width:112px;height:96px;object-fit:contain;background:#fff;flex-shrink:0;}
.v2-stibee-info{padding:14px 16px;flex:1;min-width:0;display:flex;flex-direction:column;gap:6px;justify-content:center;}
.v2-stibee-badge{display:inline-block;font-size:11px;font-weight:700;color:var(--accent);background:var(--accent-soft);padding:3px 10px;border-radius:20px;align-self:flex-start;}
.v2-stibee-title{font-size:14px;font-weight:600;line-height:1.5;}
.v2-stibee-cta{font-size:12px;color:var(--accent);font-weight:700;}

.v2-bj-card,.v2-lb-card{display:block;color:#fff;border-radius:20px;overflow:hidden;margin-top:14px;}
.v2-bj-card{background:linear-gradient(160deg,#0c0f1a 0%,#152a52 100%);}
.v2-lb-card{background:linear-gradient(160deg,#0c0f1a 0%,#141a2e 100%);}
.v2-bj-hero,.v2-lb-hero{background:#0c1117;overflow:hidden;}
.v2-bj-hero img,.v2-lb-hero img{width:100%;height:auto;max-height:340px;min-height:150px;object-fit:contain;}
.v2-bj-content,.v2-lb-content{padding:26px 24px 28px;}
.v2-bj-eyebrow,.v2-lb-eyebrow{display:flex;align-items:center;gap:8px;font-size:11px;opacity:.55;margin-bottom:12px;letter-spacing:.08em;text-transform:uppercase;}
.v2-bj-icon,.v2-lb-icon{font-size:14px;}
.v2-bj-title,.v2-lb-title{font-size:20px;font-weight:800;line-height:1.42;margin-bottom:10px;letter-spacing:-.02em;}
.v2-bj-subtitle,.v2-lb-subtitle{font-size:13.5px;opacity:.68;line-height:1.7;margin-bottom:18px;}
.v2-bj-summary{list-style:none;counter-reset:bj;padding-top:16px;margin-bottom:20px;border-top:1px solid rgba(255,255,255,.12);}
.v2-bj-summary li{counter-increment:bj;position:relative;padding:8px 0 8px 30px;font-size:13.5px;line-height:1.6;opacity:.92;border-bottom:1px solid rgba(255,255,255,.06);}
.v2-bj-summary li:last-child{border-bottom:none;}
.v2-bj-summary li::before{content:counter(bj);position:absolute;left:0;top:8px;width:22px;height:22px;border-radius:50%;
                          background:rgba(49,130,246,.25);color:#8ab4ff;font-size:11px;font-weight:800;
                          display:flex;align-items:center;justify-content:center;}
.v2-bj-cta,.v2-lb-cta{display:inline-flex;align-items:center;gap:6px;font-size:12.5px;font-weight:700;padding:9px 18px;border-radius:22px;}
.v2-bj-cta{background:rgba(49,130,246,.2);border:1px solid rgba(49,130,246,.4);color:#cfe0ff;}
.v2-lb-cta{background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.2);}

.v2-cta{margin:40px 12px 0;border-radius:22px;padding:34px 24px 30px;
        background:linear-gradient(158deg,var(--accent) 0%,var(--accent-d) 100%);box-shadow:0 14px 38px rgba(49,130,246,.34);}
.v2-cta-label{font-size:11.5px;font-weight:800;letter-spacing:.1em;text-transform:uppercase;color:rgba(255,255,255,.72);margin-bottom:14px;}
.v2-cta-headline{font-size:26px;line-height:1.32;font-weight:800;color:#fff;letter-spacing:-.03em;margin-bottom:14px;text-wrap:balance;}
.v2-cta-sub{font-size:15px;line-height:1.62;color:rgba(255,255,255,.94);margin-bottom:10px;}
.v2-cta-proof{font-size:14px;line-height:1.62;color:rgba(255,255,255,.82);margin-bottom:24px;}
.v2-cta-proof b{color:#fff;font-weight:800;}
.v2-cta-btn{display:flex;align-items:center;justify-content:center;gap:8px;width:100%;background:#fff;color:var(--accent-d);
            font-size:17px;font-weight:800;letter-spacing:-.01em;min-height:56px;border-radius:14px;box-shadow:0 4px 14px rgba(23,31,40,.16);}
.v2-cta-fine{margin-top:14px;text-align:center;font-size:12.5px;color:rgba(255,255,255,.72);}

.v2-footer{padding:30px 20px 34px;text-align:center;}
.v2-footer-nav{display:flex;gap:7px;justify-content:center;flex-wrap:wrap;margin-bottom:14px;}
.v2-footer-nav a{font-size:12px;color:var(--ink3);border:1px solid var(--line);padding:8px 14px;border-radius:20px;}
.v2-footer-copy{font-size:11px;color:var(--gray);}

.v2-arc-week{font-size:13px;color:var(--ink3);margin-bottom:24px;}
.v2-arc-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;}
@media (max-width:560px){.v2-arc-grid{grid-template-columns:repeat(2,1fr);}}
.v2-arc-card{border-radius:14px;padding:16px 12px;display:flex;flex-direction:column;gap:6px;
             border:1px solid var(--line);background:#fff;text-align:center;}
.v2-arc-card-empty{opacity:.5;}
.v2-arc-day{font-size:13px;font-weight:800;color:var(--accent);}
.v2-arc-card-empty .v2-arc-day{color:var(--gray);}
.v2-arc-date{font-size:11.5px;color:var(--ink2);font-weight:500;}
.v2-arc-lb{font-size:11px;color:var(--ink3);line-height:1.4;
           display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}
.v2-arc-cta{font-size:11px;font-weight:700;color:var(--accent);}
.v2-arc-cta-none{color:var(--gray);font-weight:400;}

a:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:10px;}
@media (prefers-reduced-motion:reduce){*{transition:none!important;}}
"""
```

- [ ] **Step 4: `build_html_v2` 셸 재작성**

`build_html_v2`(498-583행)의 `return f"""..."""` 블록을, 링크(preconnect/stylesheet)와 body 구조를 아래로 교체. 상단부(날짜/greeting_html/이미지 prefix/sections 계산)는 그대로 두고, `weekday_short = weekday_name[:1]` 한 줄을 `weekday_name = ...` 다음에 추가한다:

```python
    weekday_short = weekday_name[:1]  # "월요일" → "월"
```

sections 계산은 기존 유지(단, iboss는 Task 1으로 이미 리스트 렌더). return 블록:

```python
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta property="og:title" content="Brandrise 데일리 — {date_str}">
    <meta property="og:description" content="{weekday_name} 마케팅 뉴스레터 · Brandrise">
    <meta property="og:type" content="website">
    <title>Brandrise 데일리 | {date_str}</title>
    <link rel="preconnect" href="https://cdn.jsdelivr.net">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css">
    <style>{CSS_V2}</style>
</head>
<body>
<div class="v2-wrapper">
    {topnav}
    <div class="v2-paper">
        <div class="v2-brandbar">
            <div class="v2-brand"><span class="v2-brand-dot"></span>Brandrise 데일리</div>
            <div class="v2-brand-date">{date_str} · {weekday_short}</div>
        </div>
        <div class="v2-header">
            <div class="v2-eyebrow">오늘의 마케팅</div>
            <div class="v2-header-title">{date_str} 마케팅 뉴스</div>
            <div class="v2-greeting">{greeting_html}</div>
        </div>
        {BRANDRISE_ENTRY_HTML}
        {sections}
        {BRANDRISE_CTA_HTML}
        <div class="v2-footer">
            <div class="v2-footer-nav">{footer_nav}</div>
            <div class="v2-footer-copy">Brandrise · 매일 아침 자동 업데이트</div>
        </div>
    </div>
</div>
</body>
</html>"""
```

- [ ] **Step 5: 통과 확인 + 기존 테스트 회귀**

Run: `python -m pytest tests/test_html_formatter_v2.py -v`
Expected: 전체 PASS.

- [ ] **Step 6: 커밋**

```bash
git add html_formatter_v2.py tests/test_html_formatter_v2.py
git commit -m "feat: CSS 토스 토큰 전면 교체 + 단일 페이퍼 셸 + Pretendard"
```

---

### Task 5: 이미지 파이프라인 — 토스풍 프롬프트

`image_gen.py`의 스타일 상수를 토스풍 플랫 일러스트로 교체하고, 프롬프트 생성 지시에서 질감 변주(클레이/수채화 등) 지시를 제거해 스타일 일관성을 확보.

**Files:**
- Modify: `image_gen.py` (`STYLE_PREFIX` 47행, `STYLE_SUFFIX` 49-53행, `generate_prompts_batch` 질감 지시 103행 부근)
- Test: `tests/test_image_gen_style.py` (신규)

**Interfaces:**
- Produces: `STYLE_PREFIX: str`, `STYLE_SUFFIX: str`, `_build_fallback_prompt(title:str)->str`.

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_image_gen_style.py`:

```python
# -*- coding: utf-8 -*-
import image_gen as G


def test_style_constants_are_toss_flat():
    combined = (G.STYLE_PREFIX + G.STYLE_SUFFIX)
    assert "#3182F6" in combined
    assert "flat" in combined.lower() or "Toss" in combined
    # 기존 핑크/민트 팔레트 잔재 없음
    assert "#FFB5C8" not in combined
    assert "pink" not in combined.lower()
    assert "mint" not in combined.lower()


def test_fallback_prompt_wraps_with_style():
    p = G._build_fallback_prompt("쿠팡 멤버십 확대")
    assert p.startswith(G.STYLE_PREFIX)
    assert p.endswith(G.STYLE_SUFFIX)
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_image_gen_style.py -v`
Expected: FAIL (현재 STYLE에 pink/mint 포함).

- [ ] **Step 3: 스타일 상수 교체**

`image_gen.py` 47-53행 교체:

```python
STYLE_PREFIX = "Flat vector illustration in the clean friendly style of the Toss fintech app: "

STYLE_SUFFIX = (
    ". Soft rounded geometric shapes, minimal composition with generous negative space, "
    "smooth subtle gradients, gentle soft shadows, no outlines. Muted soft palette with a clear "
    "blue (#3182F6) as the main accent on a plain off-white (#F2F4F6) background. Single clear "
    "central concept, centered. No people, no faces, no text, no letters, no numbers, no logos, "
    "no photorealism, no dark moody tones."
)
```

- [ ] **Step 4: 프롬프트 지시에서 질감 변주 제거(일관성)**

`generate_prompts_batch`의 아래 줄(약 103행)을 교체:

기존:
```python
            "- 매 기사마다 **질감 변주**를 주세요: 부드러운 클레이, 종이접기(paper-craft), 플랫 일러스트, 수채화, 미니어처 모형 등\n"
```
교체:
```python
            "- 질감은 **전 기사 공통으로 토스풍 플랫 벡터 일러스트**로 통일하세요. 클레이·수채화·사실적 질감 금지. 변주는 사물 조합과 구도로만 주세요.\n"
```

- [ ] **Step 5: 통과 확인**

Run: `python -m pytest tests/test_image_gen_style.py -v`
Expected: PASS.

- [ ] **Step 6: 커밋**

```bash
git add image_gen.py tests/test_image_gen_style.py
git commit -m "feat: 아이보스 이미지 생성 토스풍 플랫 일러스트로 통일"
```

---

### Task 6: 카톡 텍스트 CTA 카피 정합

`formatter.py`의 `BRANDRISE_FOOTER`를 새 톤에 맞추되 UTM은 kakao 유지.

**Files:**
- Modify: `formatter.py` (`BRANDRISE_FOOTER` 73-80행)
- Test: `tests/test_kakao_footer.py` (신규)

**Interfaces:**
- Produces: `BRANDRISE_FOOTER: str` (평문, 카톡 전송용).

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_kakao_footer.py`:

```python
# -*- coding: utf-8 -*-
import formatter as F


def test_kakao_footer_new_tone_keeps_kakao_utm():
    foot = F.BRANDRISE_FOOTER
    assert "혼자 고민하지 마세요" in foot
    assert "30분 무료 상담" in foot
    assert "utm_source=kakao" in foot   # 카톡은 kakao 유지
    assert "utm_source=web" not in foot
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_kakao_footer.py -v`
Expected: FAIL.

- [ ] **Step 3: `BRANDRISE_FOOTER` 교체**

```python
BRANDRISE_FOOTER = (
    "━━━━━━━━━━━━━\n"
    "혼자 고민하지 마세요 — 브랜드라이즈 무료 상담\n"
    "- 브랜드 진단부터 지금 당장 해야 할 우선순위까지, 30분 무료 상담에서 함께 정리해드려요.\n"
    "- 이미 수십 개 브랜드가 상담받았어요. 내 브랜드처럼, 함께 고민하는 팀원의 마음으로 봅니다.\n"
    "- 스타트업 대표·마케팅 담당자를 위한 30분 (주변 추천도 환영해요💛)\n"
    "- 무료 상담 신청 https://forms.gle/R5FaijsFD4VoTEsj9?utm_source=kakao&utm_medium=organic&utm_campaign=brandrise"
)
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_kakao_footer.py -v`
Expected: PASS.

- [ ] **Step 5: 커밋**

```bash
git add formatter.py tests/test_kakao_footer.py
git commit -m "feat: 카톡 상담 CTA 카피 새 톤 정합(UTM kakao 유지)"
```

---

### Task 7: 통합 시각 검증(전 요일 섹션 조합)

모든 섹션이 새 디자인으로 렌더되는지 실제 데이터로 확인. 모바일 뷰포트 스크린샷.

**Files:**
- Create: `scratch_render_check.py` (임시 검증 스크립트, 커밋 제외)

- [ ] **Step 1: 전체 렌더 확인 스크립트 작성**

`scratch_render_check.py`:

```python
# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from pathlib import Path
from collectors.iboss import NewsItem
from collectors.neusral import CategoryNews
from collectors.heypop import HeypopItem
from collectors.longblack import LongblackItem
import html_formatter_v2 as H

iboss = [NewsItem(f"샘플 기사 {i}", "요약 문장이 여기에 들어갑니다.", f"https://ex.com/{i}") for i in range(1, 8)]
neu = [CategoryNews("오늘의 주요 뉴스", [f"헤드라인 {i}" for i in range(1, 6)], [], "https://neu.example")]
hey = [HeypopItem(title="전시 제목", description="설명", url="https://heypop.kr/x", image_url="")]
lb = LongblackItem(title="롱블랙 아티클 제목", subtitle="부제", url="https://longblack.co/note/1")

html = H.build_html_v2(iboss, neu, hey, lb, [], greeting="안녕하세요! 테스트 인사말입니다.\n\n두 번째 문단입니다.")
Path("scratch_render_check.html").write_text(html, encoding="utf-8")
print("written scratch_render_check.html", len(html), "bytes")
```

Run: `python scratch_render_check.py`
Expected: `written scratch_render_check.html ...`. HeypopItem/LongblackItem 필드명이 다르면 해당 dataclass 정의(collectors/)를 확인해 맞춘다.

- [ ] **Step 2: 브라우저 모바일 뷰포트 확인**

`scratch_render_check.html`을 브라우저에서 열고 개발자도구 모바일 뷰(폭 390)로 확인. 체크:
- Pretendard 적용(폰트가 맑은고딕이 아닌 Pretendard).
- 아이보스 7행 썸네일 리스트, 행 클릭 시 `https://ex.com/*`로 이동.
- 상단 진입점·하단 CTA 노출, CTA 줄바꿈 2줄씩.
- 뉴스럴·헤이팝·롱블랙 섹션이 새 토큰(토스 블루·회색)으로 렌더, 인디고 잔재 없음.
- 가로 스크롤 없음.

- [ ] **Step 3: 실데이터 프리뷰(선택)**

Run: `python main.py --preview`
Expected: 콘솔 출력에 에러 없음(네트워크 수집 성공 시). 저장은 안 됨.

- [ ] **Step 4: 임시 파일 정리**

```bash
rm -f scratch_render_check.py scratch_render_check.html
```

- [ ] **Step 5: 전체 테스트 최종 확인 + 커밋 없음**

Run: `python -m pytest tests/ -v`
Expected: 전체 PASS. (Task 7은 검증 전용, 커밋 산출물 없음.)

---

## Self-Review

**1. Spec coverage**
- §4 디자인 시스템 → Task 4(CSS 토큰·폰트·레이아웃). ✔
- §5 페이지 구조(상단 진입점+하단 CTA) → Task 3, 4. ✔
- §6.1 아이보스 썸네일+클릭 → Task 1. ✔
- §6.2 상단 진입점 → Task 3. ✔
- §6.3 하단 CTA(카피·줄바꿈·UTM) → Task 2. ✔
- §6.4 롱블랙 유지 → Task 4 CSS(v2-lb 리톤). ✔
- §5 나머지 섹션(뉴스럴·헤이팝·스티비·빌더조쉬) 재스타일 → Task 4 CSS(레거시 리톤). ✔
- §7 이미지 토스풍 → Task 5. ✔
- §8 전환 추적(UTM 분리) → Task 2·3(web/top/bottom), Task 6(kakao). ✔
- §9 변경 파일(html_formatter_v2·image_gen·formatter) → Task 1-6. ✔
- §11 성공 기준(요일별 일관·모바일·클릭) → Task 7. ✔

**2. Placeholder scan:** 각 스텝에 실제 코드 포함. TBD/TODO 없음. ✔

**3. Type consistency:** `BRANDRISE_ENTRY_HTML`(Task 3 생성)·`BRANDRISE_CTA_HTML`(Task 2)를 Task 4 `build_html_v2`가 소비. `_render_iboss_v2` 시그니처 불변. 클래스명 `v2-item*`/`v2-cta*`/`v2-entry*`가 렌더 함수와 CSS에서 일치. ✔

**주의(구현자용):** Task 7 Step 1의 `HeypopItem`·`LongblackItem`·`CategoryNews` 생성 인자는 각 dataclass 실제 필드에 맞춰야 한다(collectors/ 확인). 빌더조쉬·스티비 섹션은 화/수/금에만 등장하므로 해당 요일 실데이터 또는 샘플 `StibeeNewsletter`로 별도 육안 확인 권장.
