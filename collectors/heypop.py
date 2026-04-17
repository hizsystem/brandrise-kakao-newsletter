"""
헤이팝 스크래퍼 (목요일)
URL: https://heypop.kr/
팝업/전시/공간 관련 큐레이션 사이트
"""

import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass, field
from typing import List


@dataclass
class HeypopItem:
    title: str
    description: str
    url: str = ""
    category: str = "트렌드 뉴스"
    image_url: str = ""


def fetch(url: str) -> List[HeypopItem]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return parse(resp.text, url)


def parse(html: str, base_url: str = "https://heypop.kr") -> List[HeypopItem]:
    soup = BeautifulSoup(html, "html.parser")
    items: List[HeypopItem] = []

    # .card-item 구조: a.title (제목+링크), p (설명)
    for card in soup.select(".card-item"):
        title_el = card.select_one("a.title")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title:
            continue

        href = title_el.get("href", "")
        link = href if href.startswith("http") else f"{base_url.rstrip('/')}/{href.lstrip('/')}"

        desc_el = card.select_one("p")
        description = desc_el.get_text(strip=True) if desc_el else ""

        img_el = card.select_one("img")
        image_url = img_el.get("src", "") if img_el else ""

        items.append(HeypopItem(title=title, description=description, url=link, image_url=image_url))

    return items[:2]


if __name__ == "__main__":
    items = fetch("https://heypop.kr/")
    print(f"수집된 항목 {len(items)}개")
    for item in items:
        print(f"  - {item.title}")
