"""
뉴스레터 HTML 포맷터
수집된 데이터를 GitHub Pages용 아름다운 HTML로 변환
"""
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from collectors.iboss import NewsItem
from collectors.neusral import CategoryNews
from collectors.heypop import HeypopItem
from collectors.longblack import LongblackItem


BADGE_COLORS = ["green", "blue", "purple", "orange", "pink", "teal"]

WEEKDAY_NAMES = {
    0: "월요일", 1: "화요일", 2: "수요일",
    3: "목요일", 4: "금요일", 5: "토요일", 6: "일요일",
}


def _esc(text: str) -> str:
    """HTML 이스케이프"""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def _render_iboss(items: List[NewsItem]) -> str:
    if not items:
        return ""
    rows = ""
    for i, item in enumerate(items, 1):
        summary_html = f'<div class="news-summary">{_esc(item.summary)}</div>' if item.summary else ""
        rows += f"""
        <div class="news-item">
            <div class="news-num">{i}</div>
            <div class="news-title">{_esc(item.title)}</div>
            {summary_html}
        </div>"""
    return f"""
    <div class="card">
        <div class="card-header">
            <span class="card-icon">📰</span>
            <span class="card-title">오늘의 마케팅 뉴스</span>
            <span class="card-source">아이보스</span>
        </div>
        {rows}
    </div>"""


def _render_neusral(categories: List[CategoryNews]) -> str:
    if not categories:
        return ""
    rows = ""
    for i, cat in enumerate(categories):
        color = BADGE_COLORS[i % len(BADGE_COLORS)]
        headlines = "".join(f"<li>{_esc(h)}</li>" for h in cat.headlines)
        rows += f"""
        <div class="cat-item">
            <span class="cat-badge {color}">{_esc(cat.category)}</span>
            <ul class="cat-headlines">{headlines}</ul>
        </div>"""
    return f"""
    <div class="card">
        <div class="card-header">
            <span class="card-icon">🏷️</span>
            <span class="card-title">카테고리별 헤드라인</span>
            <span class="card-source">뉴스럴</span>
        </div>
        {rows}
    </div>"""


def _render_heypop(items: List[HeypopItem]) -> str:
    if not items:
        return ""
    rows = ""
    for item in items[:2]:
        desc_html = f'<div class="heypop-desc">{_esc(item.description)}</div>' if item.description else ""
        link_html = f'<a class="heypop-link" href="{item.url}" target="_blank">→ 자세히 보기</a>' if item.url else ""
        rows += f"""
        <div class="heypop-item">
            <div class="heypop-title">{_esc(item.title)}</div>
            {desc_html}
            {link_html}
        </div>"""
    return f"""
    <div class="card">
        <div class="card-header">
            <span class="card-icon">🎨</span>
            <span class="card-title">전시 / 팝업 / 공간 추천</span>
            <span class="card-source">헤이팝</span>
        </div>
        {rows}
    </div>"""


def _render_stibee(items: list) -> str:
    if not items:
        return ""
    rows = ""
    for item in items:
        title_html = f'<div class="stibee-title">{_esc(item.title)}</div>' if item.title else ""
        link_html = f'<a class="stibee-link" href="{item.url}" target="_blank">뉴스레터 보기 →</a>' if item.url else ""
        rows += f"""
        <div class="stibee-item">
            <span class="stibee-source">{_esc(item.source)}</span>
            {title_html}
            {link_html}
        </div>"""
    return f"""
    <div class="card">
        <div class="card-header">
            <span class="card-icon">✉️</span>
            <span class="card-title">이번 주 뉴스레터</span>
        </div>
        {rows}
    </div>"""


def _render_longblack(item) -> str:
    if not item:
        return ""
    subtitle_html = f'<div class="longblack-subtitle">{_esc(item.subtitle)}</div>' if item.subtitle else ""
    url = item.url or "https://www.longblack.co/"
    return f"""
    <div class="card">
        <div class="card-header">
            <span class="card-icon">📖</span>
            <span class="card-title">오늘의 롱블랙 아티클</span>
            <span class="card-source">롱블랙</span>
        </div>
        <div class="longblack-title">{_esc(item.title)}</div>
        {subtitle_html}
        <a class="longblack-link" href="{url}" target="_blank">아티클 읽기 →</a>
    </div>"""


CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: 'Noto Sans KR', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #f0f2f5;
    color: #1a1a2e;
    line-height: 1.7;
}
a { color: inherit; text-decoration: none; }
.wrapper { max-width: 680px; margin: 0 auto; padding: 32px 16px 64px; }

/* 상단 네비 */
.topnav { text-align: right; margin-bottom: 20px; }
.topnav a { font-size: 12px; color: #6b7280; border: 1px solid #e5e7eb;
             padding: 6px 14px; border-radius: 20px; transition: all 0.15s; }
.topnav a:hover { background: white; color: #6366f1; border-color: #c7d2fe; }

/* 헤더 */
.header { background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);
           color: white; padding: 40px 36px; border-radius: 20px; margin-bottom: 20px; }
.header-meta { font-size: 11px; letter-spacing: 3px; text-transform: uppercase;
                opacity: 0.45; margin-bottom: 10px; }
.header-title { font-size: 28px; font-weight: 700; margin-bottom: 4px; }
.header-subtitle { font-size: 14px; opacity: 0.5; margin-bottom: 28px; }
.greeting-box { background: rgba(255,255,255,0.07); border: 1px solid rgba(255,255,255,0.1);
                 border-radius: 14px; padding: 22px 24px; font-size: 14px; line-height: 1.9; }
.greeting-box p { margin-bottom: 12px; }
.greeting-box p:last-child { margin-bottom: 0; }

/* 카드 */
.card { background: white; border-radius: 16px; padding: 28px; margin-bottom: 16px;
         box-shadow: 0 1px 4px rgba(0,0,0,0.06), 0 4px 16px rgba(0,0,0,0.04); }
.card-header { display: flex; align-items: center; gap: 8px; margin-bottom: 20px;
                padding-bottom: 14px; border-bottom: 1px solid #f3f4f6; }
.card-icon { font-size: 18px; }
.card-title { font-size: 13px; font-weight: 600; color: #374151; }
.card-source { font-size: 11px; color: #9ca3af; margin-left: auto;
                background: #f9fafb; padding: 3px 10px; border-radius: 20px; }

/* 아이보스 뉴스 */
.news-item { padding: 16px 0; border-bottom: 1px solid #f3f4f6; }
.news-item:last-child { border-bottom: none; padding-bottom: 0; }
.news-num { display: inline-flex; align-items: center; justify-content: center;
             width: 22px; height: 22px; background: #eef2ff; color: #6366f1;
             border-radius: 50%; font-size: 11px; font-weight: 700; margin-bottom: 8px; }
.news-title { font-size: 15px; font-weight: 600; margin-bottom: 6px; color: #111827; }
.news-summary { font-size: 13px; color: #6b7280; line-height: 1.7; }

/* 뉴스럴 카테고리 */
.cat-item { padding: 14px 0; border-bottom: 1px solid #f3f4f6; }
.cat-item:last-child { border-bottom: none; padding-bottom: 0; }
.cat-badge { display: inline-block; font-size: 11px; font-weight: 600;
               padding: 3px 10px; border-radius: 20px; margin-bottom: 10px; }
.cat-badge.green  { background: #ecfdf5; color: #059669; }
.cat-badge.blue   { background: #eff6ff; color: #3b82f6; }
.cat-badge.purple { background: #f5f3ff; color: #8b5cf6; }
.cat-badge.orange { background: #fff7ed; color: #ea580c; }
.cat-badge.pink   { background: #fdf2f8; color: #db2777; }
.cat-badge.teal   { background: #f0fdfa; color: #0d9488; }
.cat-headlines { list-style: none; }
.cat-headlines li { font-size: 13px; color: #4b5563; padding: 3px 0;
                      display: flex; align-items: flex-start; gap: 6px; }
.cat-headlines li::before { content: "›"; color: #d1d5db; flex-shrink: 0; }

/* 헤이팝 */
.heypop-item { padding: 16px 0; border-bottom: 1px solid #f3f4f6; }
.heypop-item:last-child { border-bottom: none; padding-bottom: 0; }
.heypop-title { font-size: 15px; font-weight: 600; color: #111827; margin-bottom: 4px; }
.heypop-desc { font-size: 13px; color: #6b7280; margin-bottom: 10px; }
.heypop-link { font-size: 12px; color: #6366f1; border: 1px solid #e0e7ff;
                padding: 5px 14px; border-radius: 20px; display: inline-block; }
.heypop-link:hover { background: #eef2ff; }

/* 스티비 뉴스레터 */
.stibee-item { padding: 14px 0; border-bottom: 1px solid #f3f4f6; }
.stibee-item:last-child { border-bottom: none; padding-bottom: 0; }
.stibee-source { font-size: 11px; font-weight: 600; color: #d97706;
                   background: #fffbeb; padding: 3px 10px; border-radius: 20px;
                   display: inline-block; margin-bottom: 8px; }
.stibee-title { font-size: 14px; color: #374151; margin-bottom: 10px; }
.stibee-link { font-size: 12px; color: #6366f1; border: 1px solid #e0e7ff;
                padding: 5px 14px; border-radius: 20px; display: inline-block; }
.stibee-link:hover { background: #eef2ff; }

/* 롱블랙 */
.longblack-title { font-size: 17px; font-weight: 700; color: #111827; margin-bottom: 6px; }
.longblack-subtitle { font-size: 13px; color: #6b7280; margin-bottom: 16px; }
.longblack-link { display: inline-flex; align-items: center; gap: 6px; font-size: 13px;
                   font-weight: 500; color: white; background: #0f172a;
                   padding: 9px 20px; border-radius: 20px; }
.longblack-link:hover { background: #1e1b4b; }

/* 푸터 */
.footer { text-align: center; padding: 40px 0 0; }
.footer-nav { display: flex; gap: 10px; justify-content: center; flex-wrap: wrap; margin-bottom: 16px; }
.footer-nav a { font-size: 12px; color: #6b7280; border: 1px solid #e5e7eb;
                  padding: 7px 16px; border-radius: 20px; }
.footer-nav a:hover { background: white; color: #6366f1; }
.footer-copy { font-size: 11px; color: #9ca3af; }

/* 반응형 */
@media (max-width: 500px) {
    .header { padding: 28px 20px; }
    .header-title { font-size: 22px; }
    .card { padding: 20px; }
}
"""


def build_html(
    iboss_items: List[NewsItem],
    neusral_categories: List[CategoryNews],
    heypop_items: List[HeypopItem],
    longblack_item,
    stibee_items: list,
    greeting: str,
    is_subpage: bool = False,
) -> str:
    """뉴스레터 데이터를 완성된 HTML 문서로 변환.
    is_subpage=True: newsletters/YYYY-MM-DD.html (공유 링크용)
    is_subpage=False: index.html (루트, 최신)
    """
    today = datetime.now()
    date_str = f"{today.month}월 {today.day}일"
    date_iso = today.strftime("%Y-%m-%d")
    weekday_name = WEEKDAY_NAMES.get(today.weekday(), "")

    greeting_html = _esc(greeting).replace("\n\n", "</p><p>").replace("\n", "<br>")
    greeting_html = f"<p>{greeting_html}</p>"

    sections = "\n".join(filter(None, [
        _render_iboss(iboss_items),
        _render_neusral(neusral_categories),
        _render_heypop(heypop_items),
        _render_stibee(stibee_items or []),
        _render_longblack(longblack_item),
    ]))

    # 페이지 종류별 네비게이션
    if is_subpage:
        # 공유 링크 페이지: 최신 뉴스레터로 돌아가기
        topnav = '<div class="topnav"><a href="../">← 최신 뉴스레터</a></div>'
        footer_nav = '<a href="../">← 최신 뉴스레터</a>'
    else:
        # 루트(index.html): 오늘 링크 공유 + 공고 페이지
        topnav = ""
        footer_nav = (
            f'<a href="newsletters/{date_iso}.html">🔗 오늘 링크 공유</a>'
            f'<a href="grants/">📋 지원사업 공고</a>'
        )

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta property="og:title" content="Brandrise 데일리 — {date_str}">
    <meta property="og:description" content="{weekday_name} 마케팅 뉴스레터 · Brandrise">
    <meta property="og:type" content="website">
    <title>Brandrise 데일리 | {date_str}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>{CSS}</style>
</head>
<body>
<div class="wrapper">

    {topnav}

    <div class="header">
        <div class="header-meta">BRANDRISE DAILY · {date_iso}</div>
        <div class="header-title">{date_str} 마케팅 뉴스레터</div>
        <div class="header-subtitle">{weekday_name} · 매일 아침 자동 업데이트</div>
        <div class="greeting-box">{greeting_html}</div>
    </div>

    {sections}

    <div class="footer">
        <div class="footer-nav">
            {footer_nav}
        </div>
        <div class="footer-copy">Brandrise · 매일 자동 업데이트</div>
    </div>

</div>
</body>
</html>"""


def build_archive_html(newsletters_dir: Path) -> str:
    """아카이브 목록 페이지 생성"""
    files = sorted(newsletters_dir.glob("*.html"), reverse=True)

    items_html = ""
    for f in files:
        date_str = f.stem  # "2026-03-26"
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            wd = ["월", "화", "수", "목", "금", "토", "일"][dt.weekday()]
            display = f"{dt.year}년 {dt.month}월 {dt.day}일 ({wd})"
        except ValueError:
            display = date_str
        items_html += f"""
        <a class="archive-item" href="v2/newsletters/{date_str}.html">
            <span class="archive-date">{display}</span>
            <span class="archive-arrow">→</span>
        </a>"""

    if not items_html:
        items_html = '<p class="empty">아직 발행된 뉴스레터가 없습니다.</p>'

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Brandrise 데일리 — 아카이브</title>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: 'Noto Sans KR', sans-serif; background: #f0f2f5; color: #1a1a2e; }}
        .wrapper {{ max-width: 680px; margin: 0 auto; padding: 32px 16px 64px; }}
        .back {{ display: inline-block; font-size: 13px; color: #6b7280; margin-bottom: 24px;
                  border: 1px solid #e5e7eb; padding: 7px 16px; border-radius: 20px; }}
        .back:hover {{ background: white; color: #6366f1; }}
        h1 {{ font-size: 24px; font-weight: 700; margin-bottom: 6px; }}
        .subtitle {{ font-size: 14px; color: #6b7280; margin-bottom: 28px; }}
        .archive-item {{ display: flex; align-items: center; justify-content: space-between;
                           background: white; border-radius: 12px; padding: 18px 22px; margin-bottom: 10px;
                           box-shadow: 0 1px 4px rgba(0,0,0,0.06); text-decoration: none; color: inherit; }}
        .archive-item:hover {{ box-shadow: 0 4px 16px rgba(99,102,241,0.15); color: #6366f1; }}
        .archive-date {{ font-size: 15px; font-weight: 500; }}
        .archive-arrow {{ color: #9ca3af; }}
        .empty {{ color: #9ca3af; font-size: 14px; }}
    </style>
</head>
<body>
<div class="wrapper">
    <a class="back" href="index.html">← 최신 뉴스레터</a>
    <h1>뉴스레터 아카이브</h1>
    <p class="subtitle">Brandrise 데일리 전체 목록</p>
    {items_html}
</div>
</body>
</html>"""


def save_newsletter(
    iboss_items: List[NewsItem],
    neusral_categories: List[CategoryNews],
    heypop_items: List[HeypopItem],
    longblack_item,
    stibee_items: list,
    greeting: str,
    docs_dir: Path,
) -> Path:
    """
    HTML 생성 후 docs/ 폴더에 저장.
    - docs/newsletters/YYYY-MM-DD.html  (오늘 버전)
    - docs/index.html                   (최신 = 오늘)
    - docs/archive.html                 (전체 목록)
    저장된 파일 경로 반환
    """
    date_iso = datetime.now().strftime("%Y-%m-%d")
    newsletters_dir = docs_dir / "newsletters"
    newsletters_dir.mkdir(parents=True, exist_ok=True)

    # 공유 링크용 (subpage): newsletters/YYYY-MM-DD.html
    subpage_html = build_html(
        iboss_items, neusral_categories, heypop_items,
        longblack_item, stibee_items, greeting, is_subpage=True,
    )
    newsletter_path = newsletters_dir / f"{date_iso}.html"
    newsletter_path.write_text(subpage_html, encoding="utf-8")

    # 루트용 (index.html): 최신 뉴스레터
    index_html = build_html(
        iboss_items, neusral_categories, heypop_items,
        longblack_item, stibee_items, greeting, is_subpage=False,
    )
    (docs_dir / "index.html").write_text(index_html, encoding="utf-8")

    return newsletter_path


def build_weekly_archive_v1(today: datetime, newsletters_dir: Path) -> str:
    """
    주말용 주간 아카이브 페이지 (v1 스타일).
    이번 주 월~금 링크 목록.
    newsletters_dir: docs/newsletters/
    """
    monday = today - timedelta(days=today.weekday())
    weekday_names = ["월요일", "화요일", "수요일", "목요일", "금요일"]
    first = monday
    last = monday + timedelta(days=4)
    range_str = f"{first.month}월 {first.day}일 — {last.month}월 {last.day}일"

    items_html = ""
    for i in range(5):
        d = monday + timedelta(days=i)
        d_iso = d.strftime("%Y-%m-%d")
        d_label = f"{d.year}년 {d.month}월 {d.day}일 ({weekday_names[i]})"
        html_path = newsletters_dir / f"{d_iso}.html"
        if html_path.exists():
            items_html += f"""
        <a class="archive-item" href="newsletters/{d_iso}.html">
            <span class="archive-date">{d_label}</span>
            <span class="archive-arrow">→</span>
        </a>"""
        else:
            items_html += f"""
        <div class="archive-item archive-item-empty">
            <span class="archive-date">{d_label}</span>
            <span class="archive-arrow" style="color:#d1d5db;">준비 중</span>
        </div>"""

    if not items_html:
        items_html = '<p class="empty">이번 주 발행된 뉴스레터가 없습니다.</p>'

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Brandrise 데일리 — 이번 주 아카이브</title>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: 'Noto Sans KR', sans-serif; background: #f0f2f5; color: #1a1a2e; }}
        .wrapper {{ max-width: 680px; margin: 0 auto; padding: 32px 16px 64px; }}
        .back {{ display: inline-block; font-size: 13px; color: #6b7280; margin-bottom: 24px;
                 border: 1px solid #e5e7eb; padding: 7px 16px; border-radius: 20px; text-decoration: none; }}
        .back:hover {{ background: white; color: #6366f1; }}
        h1 {{ font-size: 24px; font-weight: 700; margin-bottom: 6px; }}
        .subtitle {{ font-size: 14px; color: #6b7280; margin-bottom: 28px; }}
        .archive-item {{ display: flex; justify-content: space-between; align-items: center;
                         background: white; border: 1px solid #e5e7eb; border-radius: 12px;
                         padding: 16px 20px; margin-bottom: 10px; text-decoration: none;
                         color: #1a1a2e; transition: box-shadow 0.15s; }}
        .archive-item:not(.archive-item-empty):hover {{ box-shadow: 0 4px 16px rgba(99,102,241,0.12); }}
        .archive-item-empty {{ opacity: 0.45; }}
        .archive-date {{ font-size: 14px; font-weight: 500; }}
        .archive-arrow {{ font-size: 14px; color: #6366f1; font-weight: 700; }}
        .footer {{ text-align: center; padding-top: 32px; font-size: 12px; color: #9ca3af; }}
    </style>
</head>
<body>
<div class="wrapper">
    <a class="back" href="newsletters/">← 아카이브 전체 보기</a>
    <h1>이번 주 뉴스레터</h1>
    <p class="subtitle">{range_str}</p>
    {items_html}
    <div class="footer">Brandrise · 매일 자동 업데이트</div>
</div>
</body>
</html>"""
