"""
뉴스럴 브리핑 스크래퍼
목록: https://www.neusral.com/public_briefings/...
오늘 날짜 브리핑 링크를 찾아 카테고리별 헤드라인 파싱
"""

import requests
import re
from bs4 import BeautifulSoup
from dataclasses import dataclass, field
from typing import List
from datetime import datetime


@dataclass
class CategoryNews:
    category: str
    headlines: List[str] = field(default_factory=list)
    headline_urls: List[str] = field(default_factory=list)
    url: str = ""


BASE_URL = "https://www.neusral.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def fetch(list_url: str) -> List[CategoryNews]:
    """목록 페이지에서 오늘 브리핑 링크를 찾아 파싱"""
    today = datetime.now()
    # 뉴스럴 날짜 표시 형식: "2026년 03월 10일"
    today_str = f"{today.year}년 {today.month:02d}월 {today.day:02d}일"

    r = requests.get(list_url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    r.encoding = "utf-8"
    soup = BeautifulSoup(r.text, "html.parser")

    # 오늘 날짜 브리핑 링크 찾기
    briefing_url = _find_todays_briefing(soup, today_str)

    if not briefing_url:
        print(f"  [뉴스럴] 오늘({today_str}) 브리핑을 찾지 못했습니다.")
        return []

    full_url = briefing_url if briefing_url.startswith("http") else f"{BASE_URL}{briefing_url}"

    r2 = requests.get(full_url, headers=HEADERS, timeout=15)
    r2.raise_for_status()
    r2.encoding = "utf-8"
    return parse_briefing(r2.text)


def _find_todays_briefing(soup, today_str: str) -> str:
    """브리핑 목록에서 오늘 날짜 링크 반환"""
    blocks = soup.select(".briefings-block")
    for block in blocks:
        header = block.select_one(".briefings-header")
        if header and today_str in header.get_text():
            a = block.select_one("a[href]")
            if a:
                return a.get("href", "")
    return ""


def parse_briefing(html: str) -> List[CategoryNews]:
    """
    브리핑 페이지 파싱
    구조:
      <a href="..."><span style="bold; color: rgb(90,131,182)">카테고리명 </span><span>(전체보기 click)</span></a>
      <ul><li><span>헤드라인</span></li>...</ul>
    """
    soup = BeautifulSoup(html, "html.parser")
    categories: List[CategoryNews] = []

    # 전체 페이지에서 "(전체보기 click)" 포함한 a 태그 찾기
    # 카테고리 a 태그 + 바로 다음 ul이 헤드라인 목록
    for anchor in soup.find_all("a", href=True):
        anchor_text = anchor.get_text(strip=True)

        # "(전체보기 click)" 포함 여부로 카테고리 링크 식별
        if "전체보기" not in anchor_text:
            continue

        # 카테고리 이름만 추출 (전체보기 제거)
        category_name = re.sub(r"\(전체보기.*?\)", "", anchor_text).strip()

        if not category_name or len(category_name) > 25:
            continue

        # 다음 ul 찾기
        next_ul = anchor.find_next("ul")
        if not next_ul:
            continue

        headlines = []
        headline_urls = []
        for li in next_ul.select("li"):
            text = li.get_text(strip=True)
            if not text:
                continue
            headlines.append(text)
            # li 안의 <a href> 링크 추출
            li_a = li.find("a", href=True)
            if li_a:
                h = li_a.get("href", "")
                headline_urls.append(h if h.startswith("http") else f"{BASE_URL}{h}" if h else "")
            else:
                headline_urls.append("")

        if headlines:
            href = anchor.get("href", "")
            category_url = href if href.startswith("http") else f"{BASE_URL}{href}" if href else ""
            categories.append(CategoryNews(
                category=category_name,
                headlines=headlines[:3],
                headline_urls=headline_urls[:3],
                url=category_url,
            ))

    return categories


def _parse_from_text(content) -> List[CategoryNews]:
    """텍스트에서 카테고리 + 헤드라인 패턴 파싱"""
    categories: List[CategoryNews] = []
    text = content.get_text(separator="\n")
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # 카테고리 패턴
    cat_pattern = re.compile(r"^(.{2,15}(?:뉴스|트렌드|이슈|픽))\s*(?:\(전체보기.*\))?$")
    current_cat = ""
    current_headlines: List[str] = []

    for line in lines:
        m = cat_pattern.match(line)
        if m:
            if current_cat and current_headlines:
                categories.append(CategoryNews(
                    category=current_cat,
                    headlines=current_headlines[:3]
                ))
            current_cat = m.group(1)
            current_headlines = []
        elif current_cat and 10 < len(line) < 100:
            # "(전체보기 click)" 제외
            if "전체보기" not in line and "click" not in line:
                current_headlines.append(line)

    if current_cat and current_headlines:
        categories.append(CategoryNews(
            category=current_cat,
            headlines=current_headlines[:3]
        ))

    return categories


if __name__ == "__main__":
    LIST_URL = "https://www.neusral.com/public_briefings/1S4u7Okd0AL3cgeyPbP3Cw=="
    cats = fetch(LIST_URL)
    print(f"수집된 카테고리 {len(cats)}개")
    for cat in cats:
        print(f"\n🏷️{cat.category}")
        for h in cat.headlines:
            print(f"  - {h}")
