"""
뉴스레터 HTML 포맷터 v2
이미지 썸네일 + 클릭 가능한 카드 레이아웃
"""
from datetime import datetime, timedelta
from timeutil import now_kst
from pathlib import Path
from typing import List
import re

from collectors.iboss import NewsItem
from collectors.neusral import CategoryNews
from collectors.heypop import HeypopItem
from collectors.longblack import LongblackItem


BADGE_COLORS = ["green", "blue", "purple", "orange", "pink", "teal"]

# 카테고리/키워드 → (배경 그라디언트, 이모지)
CATEGORY_THEMES = {
    "스타트업": ("135deg, #667eea 0%, #764ba2 100%", "🚀"),
    "네카라쿠배당토": ("135deg, #11998e 0%, #38ef7d 100%", "🏢"),
    "AI": ("135deg, #4facfe 0%, #00f2fe 100%", "🤖"),
    "MZ": ("135deg, #f093fb 0%, #f5576c 100%", "✨"),
    "HR": ("135deg, #4481eb 0%, #04befe 100%", "👥"),
    "ESG": ("135deg, #43e97b 0%, #38f9d7 100%", "🌿"),
    "트래블": ("135deg, #fa709a 0%, #fee140 100%", "✈️"),
    "유튜브": ("135deg, #ff0000 0%, #cc0000 100%", "▶️"),
    "네이버": ("135deg, #03c75a 0%, #02a148 100%", "🟢"),
    "메타": ("135deg, #0668E1 0%, #0052cc 100%", "📘"),
    "쿠팡": ("135deg, #e8002d 0%, #c40026 100%", "📦"),
    "OTT": ("135deg, #e50914 0%, #831010 100%", "🎬"),
    "광고": ("135deg, #f7971e 0%, #ffd200 100%", "📣"),
    "커머스": ("135deg, #11998e 0%, #38ef7d 100%", "🛒"),
    "SNS": ("135deg, #833ab4 0%, #fd1d1d 100%", "📱"),
    "웹툰": ("135deg, #f7971e 0%, #ffd200 100%", "🎨"),
    "규제": ("135deg, #536976 0%, #292e49 100%", "⚖️"),
    "오픈AI": ("135deg, #10a37f 0%, #0d8a6a 100%", "🧠"),
    "DEFAULT": ("135deg, #434343 0%, #000000 100%", "📰"),
}

WEEKDAY_NAMES = {
    0: "월요일", 1: "화요일", 2: "수요일",
    3: "목요일", 4: "금요일", 5: "토요일", 6: "일요일",
}


def _esc(text: str) -> str:
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def _get_theme(text: str) -> tuple:
    """텍스트에서 키워드를 찾아 테마(그라디언트, 이모지) 반환"""
    for keyword, theme in CATEGORY_THEMES.items():
        if keyword != "DEFAULT" and keyword in text:
            return theme
    return CATEGORY_THEMES["DEFAULT"]


def _render_iboss_v2(items: List[NewsItem], post_url: str = "", image_map: dict = None) -> str:
    if not items:
        return ""
    cards = ""
    for i, item in enumerate(items, 1):
        summary_html = f'<p class="v2-yt-summary">{_esc(item.summary)}</p>' if item.summary else ""
        if image_map and i in image_map:
            hero_html = f'<div class="v2-yt-hero"><img src="{image_map[i]}" alt="" loading="lazy"><span class="v2-yt-num">{i}</span></div>'
        else:
            gradient, emoji = _get_theme(item.title)
            hero_html = f'<div class="v2-yt-hero v2-yt-hero-grad" style="background:linear-gradient({gradient})"><span class="v2-yt-emoji">{emoji}</span><span class="v2-yt-num">{i}</span></div>'
        cards += f"""
        <div class="v2-yt-card">
            {hero_html}
            <div class="v2-yt-body">
                <div class="v2-yt-title">{_esc(item.title)}</div>
                {summary_html}
            </div>
        </div>"""
    source_link = f'<a class="v2-source-link" href="{post_url}" target="_blank">아이보스에서 보기 →</a>' if post_url else ""
    return f"""
    <div class="v2-card">
        <div class="v2-card-header">
            <span class="v2-card-icon">📰</span>
            <div>
                <div class="v2-card-title">오늘의 마케팅 뉴스</div>
                <div class="v2-card-source">아이보스</div>
            </div>
            {source_link}
        </div>
        <div class="v2-yt-grid">{cards}</div>
    </div>"""


def _render_neusral_v2(categories: List[CategoryNews], image_map: dict = None) -> str:
    if not categories:
        return ""
    rows_html = ""
    for cat in categories:
        _, emoji = _get_theme(cat.category)
        headline_items = "".join(
            f'<li class="v2-neu-item">{_esc(h)}</li>'
            for h in cat.headlines
        )
        rows_html += f"""
        <div class="v2-neu-row">
            <div class="v2-neu-label">
                <span class="v2-neu-emoji">{emoji}</span>
                <span class="v2-neu-cat">{_esc(cat.category)}</span>
            </div>
            <ul class="v2-neu-list">{headline_items}</ul>
        </div>"""
    return f"""
    <div class="v2-card">
        <div class="v2-card-header">
            <span class="v2-card-icon">🏷️</span>
            <div>
                <div class="v2-card-title">카테고리별 헤드라인</div>
                <div class="v2-card-source">뉴스럴</div>
            </div>
        </div>
        <div class="v2-neu-section">{rows_html}</div>
    </div>"""


def _render_heypop_v2(items: List[HeypopItem]) -> str:
    if not items:
        return ""
    cards = ""
    for item in items[:2]:
        img_html = (
            f'<img class="v2-thumb" src="{item.image_url}" alt="" loading="lazy">'
            if item.image_url else
            '<div class="v2-thumb-placeholder">🎨</div>'
        )
        desc_html = f'<p class="v2-heypop-desc">{_esc(item.description)}</p>' if item.description else ""
        cards += f"""
        <a class="v2-heypop-card" href="{item.url}" target="_blank" rel="noopener">
            {img_html}
            <div class="v2-heypop-info">
                <div class="v2-heypop-title">{_esc(item.title)}</div>
                {desc_html}
                <span class="v2-heypop-cta">자세히 보기 →</span>
            </div>
        </a>"""
    return f"""
    <div class="v2-card">
        <div class="v2-card-header">
            <span class="v2-card-icon">🎨</span>
            <div>
                <div class="v2-card-title">전시 / 팝업 / 공간 추천</div>
                <div class="v2-card-source">헤이팝</div>
            </div>
        </div>
        <div class="v2-heypop-list">{cards}</div>
    </div>"""


def _render_stibee_v2(items: list, image_map: dict = None) -> str:
    if not items:
        return ""
    # 빌더조쉬는 별도 풀카드(_render_builder_josh_v2)로 빠지므로 여기서는 제외
    items = [it for it in items if it.source != "빌더조쉬"]
    if not items:
        return ""
    cards = ""
    for item in items:
        img_path = (image_map or {}).get(item.source)
        title_html = f'<div class="v2-stibee-title">{_esc(item.title)}</div>' if item.title else ""
        if img_path:
            cards += f"""
        <a class="v2-stibee-card v2-stibee-card-img" href="{item.url}" target="_blank" rel="noopener">
            <img class="v2-stibee-thumb" src="{img_path}" alt="" loading="lazy">
            <div class="v2-stibee-info">
                <span class="v2-stibee-badge">{_esc(item.source)}</span>
                {title_html}
                <span class="v2-stibee-cta">뉴스레터 보기 →</span>
            </div>
        </a>"""
        else:
            cards += f"""
        <a class="v2-stibee-card" href="{item.url}" target="_blank" rel="noopener">
            <span class="v2-stibee-badge">{_esc(item.source)}</span>
            {title_html}
            <span class="v2-stibee-cta">뉴스레터 보기 →</span>
        </a>"""
    return f"""
    <div class="v2-card">
        <div class="v2-card-header">
            <span class="v2-card-icon">✉️</span>
            <div>
                <div class="v2-card-title">이번 주 뉴스레터</div>
            </div>
        </div>
        <div class="v2-stibee-list">{cards}</div>
    </div>"""


def _render_builder_josh_v2(stibee_items: list, image_map: dict = None) -> str:
    """빌더조쉬를 별도 풀카드(롱블랙급)로 렌더링. stibee_items에서 source='빌더조쉬'만 추출."""
    if not stibee_items:
        return ""
    bj = next((it for it in stibee_items if it.source == "빌더조쉬"), None)
    if not bj:
        return ""

    img_path = (image_map or {}).get(bj.source)
    hero_html = (
        f'<div class="v2-bj-hero"><img src="{img_path}" alt="" loading="lazy"></div>'
        if img_path else ""
    )
    subtitle_html = (
        f'<p class="v2-bj-subtitle">{_esc(bj.topic)}</p>' if bj.topic else ""
    )
    summary_items = list(bj.summary_items or [])
    summary_html = ""
    if summary_items:
        lis = "".join(f"<li>{_esc(s)}</li>" for s in summary_items)
        summary_html = f'<ol class="v2-bj-summary">{lis}</ol>'

    return f"""
    <a class="v2-bj-card" href="{bj.url}" target="_blank" rel="noopener">
        {hero_html}
        <div class="v2-bj-content">
        <div class="v2-bj-eyebrow">
            <span class="v2-bj-icon">✍️</span>
            <span>빌더조쉬 · 오늘의 인사이트</span>
        </div>
        <div class="v2-bj-title">{_esc(bj.title)}</div>
        {subtitle_html}
        {summary_html}
        <span class="v2-bj-cta">뉴스레터 읽기 →</span>
        </div>
    </a>"""


def _render_longblack_v2(item, lb_image: str = "") -> str:
    if not item:
        return ""
    url = item.url or "https://www.longblack.co/"
    subtitle_html = f'<p class="v2-lb-subtitle">{_esc(item.subtitle)}</p>' if item.subtitle else ""
    hero_html = f'<div class="v2-lb-hero"><img src="{lb_image}" alt="" loading="lazy"></div>' if lb_image else ""
    return f"""
    <a class="v2-lb-card" href="{url}" target="_blank" rel="noopener">
        {hero_html}
        <div class="v2-lb-content">
        <div class="v2-lb-eyebrow">
            <span class="v2-lb-icon">📖</span>
            <span>롱블랙 · 오늘의 아티클</span>
        </div>
        <div class="v2-lb-title">{_esc(item.title)}</div>
        {subtitle_html}
        <span class="v2-lb-cta">아티클 읽기 →</span>
        </div>
    </a>"""


CSS_V2 = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: 'Noto Sans KR', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #f0f2f5;
    color: #1a1a2e;
    line-height: 1.7;
}
a { color: inherit; text-decoration: none; }
.v2-wrapper { max-width: 720px; margin: 0 auto; padding: 32px 16px 64px; }

/* 상단 네비 */
.v2-topnav { text-align: right; margin-bottom: 20px; }
.v2-topnav a { font-size: 12px; color: #6b7280; border: 1px solid #e5e7eb;
               padding: 6px 14px; border-radius: 20px; transition: all 0.15s; }
.v2-topnav a:hover { background: white; color: #6366f1; }

/* 헤더 */
.v2-header { background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);
             color: white; padding: 40px 36px; border-radius: 20px; margin-bottom: 20px; }
.v2-header-meta { font-size: 11px; letter-spacing: 3px; text-transform: uppercase;
                  opacity: 0.45; margin-bottom: 10px; }
.v2-header-title { font-size: 28px; font-weight: 700; margin-bottom: 4px; }
.v2-header-subtitle { font-size: 14px; opacity: 0.5; margin-bottom: 28px; }
.v2-greeting { background: rgba(255,255,255,0.07); border: 1px solid rgba(255,255,255,0.1);
               border-radius: 14px; padding: 22px 24px; font-size: 14px; line-height: 1.9; }
.v2-greeting p { margin-bottom: 12px; }
.v2-greeting p:last-child { margin-bottom: 0; }

/* 기본 카드 */
.v2-card { background: white; border-radius: 16px; padding: 24px 28px; margin-bottom: 16px;
           box-shadow: 0 1px 4px rgba(0,0,0,0.06), 0 4px 16px rgba(0,0,0,0.04); }
.v2-card-header { display: flex; align-items: center; gap: 10px; margin-bottom: 20px;
                  padding-bottom: 14px; border-bottom: 1px solid #f3f4f6; }
.v2-card-icon { font-size: 20px; flex-shrink: 0; }
.v2-card-title { font-size: 14px; font-weight: 700; color: #111827; }
.v2-card-source { font-size: 11px; color: #9ca3af; margin-top: 1px; }
.v2-source-link { margin-left: auto; flex-shrink: 0; font-size: 11px; color: #6366f1;
                  border: 1px solid #e0e7ff; padding: 5px 12px; border-radius: 20px;
                  transition: background 0.15s; white-space: nowrap; }
.v2-source-link:hover { background: #eef2ff; }

/* 아이보스 — YouTube 썸네일 그리드 */
.v2-yt-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
@media (max-width: 520px) { .v2-yt-grid { grid-template-columns: 1fr; } }
.v2-yt-card { border-radius: 14px; overflow: hidden; border: 1px solid #ebebeb;
              background: white; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
              transition: transform 0.15s, box-shadow 0.15s; }
.v2-yt-card:hover { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(0,0,0,0.1); }
.v2-yt-hero { position: relative; aspect-ratio: 16 / 9; overflow: hidden; background: #e5e7eb; }
.v2-yt-hero img { width: 100%; height: 100%; object-fit: cover; display: block; }
.v2-yt-hero-grad { display: flex; align-items: center; justify-content: center; }
.v2-yt-emoji { font-size: 44px; }
.v2-yt-num { position: absolute; top: 10px; left: 10px;
             background: rgba(0,0,0,0.72); color: white;
             font-size: 11px; font-weight: 800; padding: 3px 9px;
             border-radius: 6px; letter-spacing: 0.3px; }
.v2-yt-body { padding: 13px 15px 15px; }
.v2-yt-title { font-size: 13.5px; font-weight: 700; color: #0f172a; line-height: 1.5;
               margin-bottom: 5px;
               display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
               overflow: hidden; }
.v2-yt-summary { font-size: 12px; color: #64748b; line-height: 1.6; }

/* 뉴스럴 — 가로형 레이아웃 */
.v2-neu-section { display: flex; flex-direction: column; }
.v2-neu-row { display: flex; align-items: flex-start; gap: 18px;
              padding: 14px 0; border-bottom: 1px solid #f3f4f6; }
.v2-neu-row:first-child { padding-top: 4px; }
.v2-neu-row:last-child { border-bottom: none; padding-bottom: 0; }
.v2-neu-label { display: flex; flex-direction: column; align-items: center; gap: 5px;
                width: 60px; flex-shrink: 0; padding-top: 2px; }
.v2-neu-emoji { font-size: 26px; line-height: 1; }
.v2-neu-cat { font-size: 10px; font-weight: 700; color: #6b7280;
              text-align: center; line-height: 1.3; word-break: keep-all; }
.v2-neu-list { list-style: none; flex: 1; display: flex; flex-direction: column; gap: 6px; }
.v2-neu-item { font-size: 12.5px; color: #374151; line-height: 1.6;
               padding-left: 13px; position: relative; }
.v2-neu-item::before { content: "·"; position: absolute; left: 2px; color: #d1d5db;
                       font-size: 16px; line-height: 1.3; font-weight: 700; }

/* 헤이팝 — 이미지 카드 */
.v2-heypop-list { display: flex; flex-direction: column; gap: 12px; }
.v2-heypop-card { display: flex; gap: 0; border-radius: 14px; overflow: hidden;
                  background: white; border: 1px solid #ebebeb;
                  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
                  transition: box-shadow 0.15s, transform 0.15s; }
.v2-heypop-card:hover { box-shadow: 0 6px 24px rgba(99,102,241,0.14); transform: translateY(-1px); }
.v2-thumb { width: 130px; height: 100px; object-fit: contain; background: #f8f9fb; flex-shrink: 0; display: block; }
.v2-thumb-placeholder { width: 130px; height: 100px; display: flex; align-items: center;
                         justify-content: center; font-size: 36px; background: #f3f4f6; flex-shrink: 0; }
.v2-heypop-info { padding: 14px 18px; display: flex; flex-direction: column;
                  justify-content: center; gap: 5px; min-width: 0; }
.v2-heypop-title { font-size: 14px; font-weight: 700; color: #0f172a; line-height: 1.45; }
.v2-heypop-desc { font-size: 12.5px; color: #64748b; line-height: 1.55; }
.v2-heypop-cta { font-size: 11.5px; color: #6366f1; font-weight: 600; margin-top: 2px; }

/* 스티비 뉴스레터 */
.v2-stibee-list { display: flex; flex-direction: column; gap: 10px; }
.v2-stibee-card { display: flex; flex-direction: column; gap: 6px; padding: 18px 20px;
                  background: white; border-radius: 14px; border: 1px solid #ebebeb;
                  box-shadow: 0 1px 3px rgba(0,0,0,0.05); transition: box-shadow 0.15s; overflow: hidden; }
.v2-stibee-card:hover { box-shadow: 0 6px 20px rgba(99,102,241,0.12); }
.v2-stibee-card-img { flex-direction: row; padding: 0; gap: 0; }
.v2-stibee-thumb { width: 120px; height: 100px; object-fit: contain; background: #f8f9fb; flex-shrink: 0; display: block; }
.v2-stibee-info { padding: 16px 18px; flex: 1; min-width: 0; display: flex;
                  flex-direction: column; gap: 6px; justify-content: center; }
.v2-stibee-badge { display: inline-block; font-size: 11px; font-weight: 700; color: #b45309;
                   background: #fef3c7; padding: 3px 10px; border-radius: 20px;
                   align-self: flex-start; letter-spacing: 0.2px; }
.v2-stibee-title { font-size: 14px; font-weight: 600; color: #1e293b; line-height: 1.5; }
.v2-stibee-cta { font-size: 12px; color: #6366f1; font-weight: 600; }

/* 롱블랙 — 클릭 가능한 피처드 카드 */
.v2-lb-card { display: block; background: linear-gradient(160deg, #0c0f1a 0%, #1a1f3a 100%);
              color: white; border-radius: 20px; overflow: hidden; margin-bottom: 16px;
              transition: transform 0.18s, box-shadow 0.18s;
              box-shadow: 0 6px 28px rgba(10,15,40,0.35); }
.v2-lb-card:hover { transform: translateY(-3px); box-shadow: 0 12px 40px rgba(10,15,40,0.45); }
.v2-lb-hero { background: #0c1117; overflow: hidden; }
.v2-lb-hero img { width: 100%; height: auto; max-height: 360px; min-height: 160px;
                  object-fit: contain; opacity: 1; display: block; }
.v2-lb-content { padding: 28px 32px 32px; }
.v2-lb-eyebrow { display: flex; align-items: center; gap: 8px; font-size: 11.5px;
                 opacity: 0.5; margin-bottom: 12px; letter-spacing: 1px; text-transform: uppercase; }
.v2-lb-icon { font-size: 15px; }
.v2-lb-title { font-size: 21px; font-weight: 800; line-height: 1.4; margin-bottom: 10px; letter-spacing: -0.3px; }
.v2-lb-subtitle { font-size: 13.5px; opacity: 0.6; line-height: 1.8; margin-bottom: 22px; }
.v2-lb-cta { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; font-weight: 700;
             background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2);
             padding: 9px 20px; border-radius: 24px; letter-spacing: 0.3px; }

/* 빌더조쉬 — 클릭 가능한 피처드 카드 (롱블랙급, 보라/인디고 톤) */
.v2-bj-card { display: block; background: linear-gradient(160deg, #1a1147 0%, #312e81 100%);
              color: white; border-radius: 20px; overflow: hidden; margin-bottom: 16px;
              transition: transform 0.18s, box-shadow 0.18s;
              box-shadow: 0 6px 28px rgba(49,46,129,0.35); }
.v2-bj-card:hover { transform: translateY(-3px); box-shadow: 0 12px 40px rgba(49,46,129,0.5); }
.v2-bj-hero { background: #0f0a2b; overflow: hidden; }
.v2-bj-hero img { width: 100%; height: auto; max-height: 360px; min-height: 160px;
                  object-fit: contain; opacity: 1; display: block; }
.v2-bj-content { padding: 28px 32px 32px; }
.v2-bj-eyebrow { display: flex; align-items: center; gap: 8px; font-size: 11.5px;
                 opacity: 0.55; margin-bottom: 12px; letter-spacing: 1px; text-transform: uppercase; }
.v2-bj-icon { font-size: 15px; }
.v2-bj-title { font-size: 21px; font-weight: 800; line-height: 1.4; margin-bottom: 10px; letter-spacing: -0.3px; }
.v2-bj-subtitle { font-size: 13.5px; opacity: 0.62; line-height: 1.8; margin-bottom: 20px; }
.v2-bj-summary { list-style: none; counter-reset: bj-num; padding: 0; margin: 0 0 22px;
                 border-top: 1px solid rgba(255,255,255,0.12); padding-top: 18px; }
.v2-bj-summary li { counter-increment: bj-num; position: relative;
                    padding: 8px 0 8px 32px; font-size: 13.5px; line-height: 1.65;
                    opacity: 0.92; border-bottom: 1px solid rgba(255,255,255,0.06); }
.v2-bj-summary li:last-child { border-bottom: none; }
.v2-bj-summary li::before { content: counter(bj-num); position: absolute; left: 0; top: 8px;
                            width: 22px; height: 22px; border-radius: 50%;
                            background: rgba(167,139,250,0.2); color: #c4b5fd;
                            font-size: 11px; font-weight: 800; display: flex;
                            align-items: center; justify-content: center; }
.v2-bj-cta { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; font-weight: 700;
             background: rgba(167,139,250,0.18); border: 1px solid rgba(167,139,250,0.35);
             padding: 9px 20px; border-radius: 24px; letter-spacing: 0.3px; color: #ede9fe; }

/* 푸터 */
.v2-footer { text-align: center; padding: 40px 0 0; }
.v2-footer-nav { display: flex; gap: 10px; justify-content: center; flex-wrap: wrap; margin-bottom: 16px; }
.v2-footer-nav a { font-size: 12px; color: #6b7280; border: 1px solid #e5e7eb;
                   padding: 7px 16px; border-radius: 20px; transition: all 0.15s; }
.v2-footer-nav a:hover { background: white; color: #6366f1; }
.v2-footer-copy { font-size: 11px; color: #9ca3af; }

/* 브랜드라이즈 상담 CTA */
.v2-cta { background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%); border-radius: 16px;
          padding: 28px 28px 30px; margin-top: 24px; }
.v2-cta-title { font-size: 16px; font-weight: 700; color: #ffffff; margin-bottom: 14px; }
.v2-cta-list { list-style: none; margin: 0 0 22px; padding: 0; }
.v2-cta-list li { font-size: 13.5px; line-height: 1.65; color: #cbd5e1; padding-left: 15px;
                  position: relative; margin-bottom: 7px; }
.v2-cta-list li::before { content: "·"; position: absolute; left: 3px; color: #818cf8; font-weight: 700; }
.v2-cta-btn { display: inline-block; background: #6366f1; color: #ffffff; font-size: 14px; font-weight: 700;
              padding: 12px 26px; border-radius: 10px; transition: background 0.15s; }
.v2-cta-btn:hover { background: #818cf8; }

/* 주간 아카이브 */
.v2-arc-week { font-size: 13px; opacity: 0.5; margin-bottom: 28px; letter-spacing: 0.5px; }
.v2-arc-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin-bottom: 16px; }
@media (max-width: 560px) { .v2-arc-grid { grid-template-columns: repeat(2, 1fr); } }
.v2-arc-card { border-radius: 14px; padding: 18px 14px; display: flex; flex-direction: column;
               gap: 6px; border: 1px solid #ebebeb; background: white;
               box-shadow: 0 1px 4px rgba(0,0,0,0.05); text-align: center; }
.v2-arc-card-active { transition: transform 0.15s, box-shadow 0.15s; }
.v2-arc-card-active:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(99,102,241,0.15); }
.v2-arc-card-empty { opacity: 0.45; }
.v2-arc-day { font-size: 13px; font-weight: 800; color: #6366f1; }
.v2-arc-card-empty .v2-arc-day { color: #9ca3af; }
.v2-arc-date { font-size: 11.5px; color: #374151; font-weight: 500; }
.v2-arc-lb { font-size: 11px; color: #64748b; line-height: 1.45; margin-top: 2px;
             display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.v2-arc-cta { font-size: 11px; font-weight: 700; color: #6366f1; margin-top: 4px; }
.v2-arc-cta-none { color: #d1d5db; font-weight: 400; }

/* 반응형 */
@media (max-width: 500px) {
    .v2-header { padding: 28px 20px; }
    .v2-header-title { font-size: 22px; }
    .v2-card { padding: 18px 20px; }
    .v2-lb-card { padding: 22px 20px; }
    .v2-bj-content { padding: 22px 20px 24px; }
    .v2-bj-title { font-size: 18.5px; }
    .v2-bj-summary li { padding-left: 28px; font-size: 13px; }
    .v2-thumb { width: 90px; height: 70px; }
    .v2-thumb-placeholder { width: 90px; height: 70px; }
}
"""


def _prefix(image_map: dict, is_subpage: bool) -> dict:
    """서브페이지용 이미지 경로에 ../ 접두사 추가"""
    if not image_map or not is_subpage:
        return image_map or {}
    return {k: f"../{v}" for k, v in image_map.items()}


# 브랜드라이즈 무료 상담 CTA (모든 뉴스레터 페이지 하단 공통)
BRANDRISE_CTA_HTML = (
    '<div class="v2-cta">'
    '<div class="v2-cta-title">⭐ 살짝 공지드려요</div>'
    '<ul class="v2-cta-list">'
    '<li>마케팅이나 브랜딩에 고민이 있다면, 브랜드라이즈에서 무료로 상담받아보세요.</li>'
    '<li>직접 만나보니, 무엇부터 어떻게 풀어야 할지 막막해하는 분들이 많아 시작했어요.</li>'
    '<li>필요하시면 언제든 편하게 말씀주세요. 주변 추천도 환영합니다 💛</li>'
    '</ul>'
    '<a class="v2-cta-btn" href="https://forms.gle/R5FaijsFD4VoTEsj9?utm_source=kakao&amp;utm_medium=organic&amp;utm_campaign=brandrise" '
    'target="_blank" rel="noopener">무료 상담 신청하기 →</a>'
    '</div>'
)


def build_html_v2(
    iboss_items: List[NewsItem],
    neusral_categories: List[CategoryNews],
    heypop_items: List[HeypopItem],
    longblack_item,
    stibee_items: list,
    greeting: str,
    iboss_post_url: str = "",
    iboss_image_map: dict = None,
    neusral_image_map: dict = None,
    lb_image: str = "",
    stibee_image_map: dict = None,
    is_subpage: bool = False,
) -> str:
    today = now_kst()
    date_str = f"{today.month}월 {today.day}일"
    date_iso = today.strftime("%Y-%m-%d")
    weekday_name = WEEKDAY_NAMES.get(today.weekday(), "")

    greeting_html = _esc(greeting).replace("\n\n", "</p><p>").replace("\n", "<br>")
    greeting_html = f"<p>{greeting_html}</p>"

    # 서브페이지는 이미지 경로에 ../ 접두사 필요
    p_iboss = _prefix(iboss_image_map, is_subpage)
    p_neusral = _prefix(neusral_image_map, is_subpage)
    p_stibee = _prefix(stibee_image_map, is_subpage)
    p_lb = f"../{lb_image}" if lb_image and is_subpage else lb_image

    sections = "\n".join(filter(None, [
        _render_iboss_v2(iboss_items, iboss_post_url, p_iboss),
        _render_neusral_v2(neusral_categories, p_neusral),
        _render_heypop_v2(heypop_items),
        _render_builder_josh_v2(stibee_items or [], p_stibee),
        _render_stibee_v2(stibee_items or [], p_stibee),
        _render_longblack_v2(longblack_item, p_lb),
    ]))

    if is_subpage:
        topnav = '<div class="v2-topnav"><a href="../../v2/">← 최신 뉴스레터</a></div>'
        footer_nav = '<a href="../../v2/">← 최신 뉴스레터</a><a href="../archive.html">📚 전체 아카이브</a>'
    else:
        topnav = ""
        footer_nav = (
            f'<a href="newsletters/{date_iso}.html">🔗 오늘 링크 공유</a>'
            f'<a href="../grants/">📋 지원사업 공고</a>'
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
    <style>{CSS_V2}</style>
</head>
<body>
<div class="v2-wrapper">

    {topnav}

    <div class="v2-header">
        <div class="v2-header-meta">BRANDRISE DAILY · {date_iso}</div>
        <div class="v2-header-title">{date_str} 마케팅 뉴스레터</div>
        <div class="v2-header-subtitle">{weekday_name} · 매일 아침 자동 업데이트</div>
        <div class="v2-greeting">{greeting_html}</div>
    </div>

    {sections}

    {BRANDRISE_CTA_HTML}

    <div class="v2-footer">
        <div class="v2-footer-nav">
            {footer_nav}
        </div>
        <div class="v2-footer-copy">Brandrise · 매일 자동 업데이트</div>
    </div>

</div>
</body>
</html>"""


def save_newsletter_v2(
    iboss_items: List[NewsItem],
    neusral_categories: List[CategoryNews],
    heypop_items: List[HeypopItem],
    longblack_item,
    stibee_items: list,
    greeting: str,
    docs_dir: Path,
    iboss_post_url: str = "",
    anthropic_api_key: str = "",
    gemini_api_key: str = "",
) -> Path:
    """
    v2 HTML 생성 후 docs/v2/ 폴더에 저장.
    - docs/v2/newsletters/YYYY-MM-DD.html
    - docs/v2/index.html
    이미지 생성: Gemini 우선, Pollinations.ai 폴백
    """
    date_iso = now_kst().strftime("%Y-%m-%d")
    v2_dir = docs_dir / "v2"
    newsletters_dir = v2_dir / "newsletters"
    newsletters_dir.mkdir(parents=True, exist_ok=True)

    from image_gen import (
        generate_iboss_images,
        fetch_longblack_image, fetch_stibee_images,
    )

    # Pollinations.ai AI 이미지 (아이보스만 — 뉴스럴은 아이콘으로 대체)
    iboss_image_map = {}
    neusral_image_map = {}
    try:
        engine = "Gemini" if gemini_api_key else "Pollinations"
        print(f"  → {engine} 이미지 생성 중...")
        if iboss_items:
            iboss_image_map = generate_iboss_images(
                iboss_items, docs_dir, date_iso, anthropic_api_key, gemini_api_key
            )
        print(f"     AI 이미지 완료 (아이보스 {len(iboss_image_map)}개)")
    except Exception as e:
        print(f"  [WARN] AI 이미지 생성 실패: {e}")

    # OG 이미지 스크래핑 (롱블랙 + 스티비)
    lb_image = ""
    stibee_image_map = {}
    try:
        print("  → OG 이미지 스크래핑 중...")
        lb_image = fetch_longblack_image(longblack_item, docs_dir, date_iso)
        stibee_image_map = fetch_stibee_images(stibee_items, docs_dir, date_iso)
    except Exception as e:
        print(f"  [WARN] OG 이미지 스크래핑 실패: {e}")

    def _build(is_subpage: bool) -> str:
        return build_html_v2(
            iboss_items, neusral_categories, heypop_items,
            longblack_item, stibee_items, greeting, iboss_post_url,
            iboss_image_map=iboss_image_map,
            neusral_image_map=neusral_image_map,
            lb_image=lb_image,
            stibee_image_map=stibee_image_map,
            is_subpage=is_subpage,
        )

    newsletter_path = newsletters_dir / f"{date_iso}.html"
    newsletter_path.write_text(_build(is_subpage=True), encoding="utf-8")
    (v2_dir / "index.html").write_text(_build(is_subpage=False), encoding="utf-8")
    # 루트 index.html → 최신 날짜별 URL로 리다이렉트
    redirect_url = f"v2/newsletters/{date_iso}.html"
    (docs_dir / "index.html").write_text(
        f'<!DOCTYPE html><html><head><meta charset="UTF-8">'
        f'<meta http-equiv="refresh" content="0; url={redirect_url}">'
        f'<script>location.href="{redirect_url}"</script>'
        f'</head><body></body></html>',
        encoding="utf-8",
    )

    return newsletter_path


def build_weekly_archive_v2(today: datetime, newsletters_dir: Path) -> str:
    """
    주말용 주간 아카이브 페이지 (v2 스타일).
    이번 주 월~금 카드 5장 + 각 날짜의 뉴스레터 링크.
    newsletters_dir: docs/v2/newsletters/
    """
    import re as _re

    # 이번 주 월요일 기준
    monday = today - timedelta(days=today.weekday())  # weekday: 5=토, 6=일
    weekday_names = ["월요일", "화요일", "수요일", "목요일", "금요일"]

    date_str = f"{today.month}월 {today.day}일"
    date_iso = today.strftime("%Y-%m-%d")
    first = monday
    last = monday + timedelta(days=4)
    range_str = f"{first.month}월 {first.day}일 — {last.month}월 {last.day}일"

    def _extract_lb_title(html_path: Path) -> str:
        try:
            text = html_path.read_text(encoding="utf-8")
            m = _re.search(r'class="v2-lb-title"[^>]*>([^<]{4,80})<', text)
            return m.group(1).strip() if m else ""
        except Exception:
            return ""

    cards_html = ""
    for i in range(5):
        d = monday + timedelta(days=i)
        d_iso = d.strftime("%Y-%m-%d")
        d_label = f"{d.month}월 {d.day}일"
        html_path = newsletters_dir / f"{d_iso}.html"
        lb_title = _extract_lb_title(html_path) if html_path.exists() else ""
        lb_html = f'<span class="v2-arc-lb">{_esc(lb_title)}</span>' if lb_title else ""

        if html_path.exists():
            cards_html += f"""
        <a class="v2-arc-card v2-arc-card-active" href="newsletters/{d_iso}.html">
            <span class="v2-arc-day">{weekday_names[i]}</span>
            <span class="v2-arc-date">{d_label}</span>
            {lb_html}
            <span class="v2-arc-cta">보기 →</span>
        </a>"""
        else:
            cards_html += f"""
        <div class="v2-arc-card v2-arc-card-empty">
            <span class="v2-arc-day">{weekday_names[i]}</span>
            <span class="v2-arc-date">{d_label}</span>
            <span class="v2-arc-cta v2-arc-cta-none">준비 중</span>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta property="og:title" content="Brandrise 데일리 — 이번 주 아카이브">
    <meta property="og:description" content="{range_str} 마케팅 뉴스레터 모아보기">
    <title>Brandrise 데일리 v2 | 이번 주 아카이브</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>{CSS_V2}</style>
</head>
<body>
<div class="v2-wrapper">

    <div class="v2-header">
        <div class="v2-header-meta">BRANDRISE DAILY v2 · WEEKLY ARCHIVE</div>
        <div class="v2-header-title">이번 주 뉴스레터</div>
        <div class="v2-arc-week">{range_str}</div>
    </div>

    <div class="v2-card">
        <div class="v2-card-header">
            <span class="v2-card-icon">📅</span>
            <div>
                <div class="v2-card-title">요일별 뉴스레터</div>
                <div class="v2-card-source">클릭하면 해당 날짜 뉴스레터로 이동합니다</div>
            </div>
        </div>
        <div class="v2-arc-grid">{cards_html}
        </div>
    </div>

    <div class="v2-footer">
        <div class="v2-footer-nav">
            <a href="../grants/">📋 지원사업 공고</a>
        </div>
        <div class="v2-footer-copy">Brandrise · 매일 자동 업데이트</div>
    </div>

</div>
</body>
</html>"""


def build_full_archive_v2(newsletters_dir: Path) -> str:
    """v2 전체 아카이브 페이지 — docs/v2/archive.html"""
    files = sorted(newsletters_dir.glob("*.html"), reverse=True)
    wd_names = ["월", "화", "수", "목", "금", "토", "일"]

    items_html = ""
    for f in files:
        date_str = f.stem
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            wd = wd_names[dt.weekday()]
            display = f"{dt.year}년 {dt.month}월 {dt.day}일 ({wd})"
        except ValueError:
            continue
        items_html += f"""
        <a class="v2-arc-full-item" href="newsletters/{date_str}.html">
            <span class="v2-arc-full-date">{display}</span>
            <span class="v2-arc-full-arrow">→</span>
        </a>"""

    if not items_html:
        items_html = '<p style="color:#9ca3af;font-size:13px;">아직 발행된 뉴스레터가 없습니다.</p>'

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Brandrise 데일리 v2 | 전체 아카이브</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>{CSS_V2}
.v2-arc-full-item {{ display: flex; justify-content: space-between; align-items: center;
                     background: white; border: 1px solid #e5e7eb; border-radius: 12px;
                     padding: 16px 20px; margin-bottom: 10px; color: #1a1a2e;
                     transition: box-shadow 0.15s; }}
.v2-arc-full-item:hover {{ box-shadow: 0 4px 16px rgba(99,102,241,0.12); }}
.v2-arc-full-date {{ font-size: 14px; font-weight: 500; }}
.v2-arc-full-arrow {{ font-size: 14px; color: #6366f1; font-weight: 700; }}
    </style>
</head>
<body>
<div class="v2-wrapper">
    <div class="v2-header">
        <div class="v2-header-meta">BRANDRISE DAILY v2 · ARCHIVE</div>
        <div class="v2-header-title">전체 아카이브</div>
        <div class="v2-header-subtitle">발행된 모든 뉴스레터 목록</div>
    </div>
    <div class="v2-card">
        <div class="v2-card-header">
            <span class="v2-card-icon">📂</span>
            <div>
                <div class="v2-card-title">날짜별 뉴스레터</div>
            </div>
            <a class="v2-source-link" href="./">← 최신 뉴스레터</a>
        </div>
        {items_html}
    </div>
    <div class="v2-footer">
        <div class="v2-footer-copy">Brandrise · 매일 자동 업데이트</div>
    </div>
</div>
</body>
</html>"""
