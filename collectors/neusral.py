"""
뉴스럴 데일리픽 스크래퍼 (beehiiv 이전판, 2026-06 ~)
목록: https://newsletter.neusral.com/t/newsletter (데일리픽 아카이브, 최신순)
가장 최근 '데일리픽' 글을 찾아 발행일이 오늘(KST)인지 확인 후 헤드라인 파싱.

이전 형식(https://www.neusral.com/public_briefings/...)은 2026-06-09 이후 갱신 중단됨.
"""

import requests
import json
from bs4 import BeautifulSoup
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime, timezone, timedelta


@dataclass
class CategoryNews:
    category: str
    headlines: List[str] = field(default_factory=list)
    headline_urls: List[str] = field(default_factory=list)
    url: str = ""


SITE_URL = "https://newsletter.neusral.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

KST = timezone(timedelta(hours=9))

# 본문 h2 중 헤드라인이 아닌 푸터/안내성 항목 제외 키워드
_SKIP_HEADLINE = ("제휴", "광고문의", "Reply", "구독", "모니터링", "뉴스럴 모니터링")


def fetch(list_url: str = SITE_URL) -> List[CategoryNews]:
    """데일리픽 아카이브에서 최신 글을 찾아 오늘 발행분이면 헤드라인 파싱."""
    post_url = _find_latest_post(list_url)
    if not post_url:
        print("  [뉴스럴] 데일리픽 글 링크를 찾지 못했습니다.")
        return []

    r = requests.get(post_url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    r.encoding = "utf-8"
    soup = BeautifulSoup(r.text, "html.parser")

    published = _published_kst(soup)
    today = datetime.now().date()
    if published and published.date() != today:
        print(
            f"  [뉴스럴] 최신 데일리픽({published.date()})이 오늘({today})이 아닙니다. 건너뜁니다."
        )
        return []

    headlines = _parse_headlines(soup)
    if not headlines:
        print("  [뉴스럴] 헤드라인을 추출하지 못했습니다.")
        return []

    return [
        CategoryNews(
            category="오늘의 주요 뉴스",
            headlines=headlines,
            headline_urls=[post_url] * len(headlines),
            url=post_url,
        )
    ]


def _find_latest_post(list_url: str) -> str:
    """목록 페이지에서 첫 번째 /p/ 글 링크(최신순 정렬 가정)를 절대 URL로 반환."""
    # 데일리픽 아카이브를 우선 사용 (홈 URL이 들어와도 보정)
    if "/t/newsletter" not in list_url:
        list_url = f"{SITE_URL}/t/newsletter"

    r = requests.get(list_url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    r.encoding = "utf-8"
    soup = BeautifulSoup(r.text, "html.parser")

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("/p/"):
            return f"{SITE_URL}{href}"
        if href.startswith(f"{SITE_URL}/p/"):
            return href
    return ""


def _published_kst(soup: BeautifulSoup) -> Optional[datetime]:
    """JSON-LD의 datePublished를 KST datetime으로 반환 (없으면 None)."""
    for sc in soup.find_all("script", type="application/ld+json"):
        if not sc.string:
            continue
        try:
            data = json.loads(sc.string)
        except (json.JSONDecodeError, TypeError):
            continue
        dp = data.get("datePublished") if isinstance(data, dict) else None
        if dp:
            try:
                dt = datetime.fromisoformat(dp.replace("Z", "+00:00"))
                return dt.astimezone(KST)
            except ValueError:
                continue
    return None


def _parse_headlines(soup: BeautifulSoup, limit: int = 8) -> List[str]:
    """글 본문 h2 헤드라인 목록 추출 (푸터/안내 항목 제외)."""
    headlines: List[str] = []
    for h in soup.find_all("h2"):
        text = h.get_text(" ", strip=True)
        if not text or any(k in text for k in _SKIP_HEADLINE):
            continue
        headlines.append(text)
    return headlines[:limit]


if __name__ == "__main__":
    import sys
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    cats = fetch(f"{SITE_URL}/t/newsletter")
    print(f"수집된 카테고리 {len(cats)}개")
    for cat in cats:
        print(f"\n🏷️{cat.category}  ({cat.url})")
        for h in cat.headlines:
            print(f"  - {h}")
