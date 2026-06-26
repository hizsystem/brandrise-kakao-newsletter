"""
롱블랙 웹사이트 스크래퍼
오늘의 아티클 제목과 링크 수집
"""

import re
import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


@dataclass
class LongblackItem:
    title: str
    subtitle: str
    url: str = "https://www.longblack.co/"


def _clean_subtitle(text: str) -> str:
    """롱블랙 미리보기 부제 정제.

    - 선행 바이라인("롱블랙 프렌즈 K " 등)을 제거.
    - 미리보기가 단어 중간에서 잘린 경우(종결부호로 끝나지 않음)
      마지막 완결 문장까지만 남겨 어색한 잘림을 방지.
    """
    if not text:
        return text
    text = text.strip()
    text = re.sub(r"^롱블랙\s+(프렌즈|노트|레터)\s+\S+\s+", "", text).strip()
    if text and text[-1] not in "!?.…":
        ends = list(re.finditer(r"[.!?…]", text))
        if ends:
            text = text[: ends[-1].end()].strip()
    return text


def fetch(url: str = "https://www.longblack.co/") -> LongblackItem | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.encoding = "utf-8"
        return parse(r.text)
    except Exception as e:
        print(f"  [WARN] 롱블랙 수집 실패: {e}")
        return None


def parse(html: str) -> LongblackItem | None:
    soup = BeautifulSoup(html, "html.parser")

    # 오늘의 노트 제목 - TODAY 섹션 이후 첫 번째 긴 텍스트
    text_lines = [l.strip() for l in soup.get_text(separator="\n").splitlines() if l.strip()]

    title = ""
    subtitle = ""
    link = "https://www.longblack.co/"

    # UI 텍스트로 판단되는 짧은 문구 제외 목록
    ui_texts = {"TODAY", "이 노트를 오늘 안에 읽으면", "라이브러리에 저장", "할 수 있어요!",
                "롱블랙 멤버십 가입하기", "HELLO LONGBLACK!", "생각이 탄탁한 사람들의 하루 10분 루틴"}

    # "TODAY" 이후 첫 번째 실제 아티클 제목 추출
    found_today = False
    for line in text_lines:
        if line == "TODAY":
            found_today = True
            continue
        if found_today:
            if line in ui_texts or line.isdigit() or len(line) < 8:
                continue
            # 콜론 포함한 긴 제목 형태 (예: "홍길동 : 부제목") 또는 일반 제목
            if not title:
                title = line
            elif not subtitle and line != title:
                subtitle = line
                break

    # 링크: /note/ 포함한 첫 번째 링크
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if "/note/" in href:
            link = f"https://www.longblack.co{href}" if href.startswith("/") else href
            break

    if not title:
        return None

    return LongblackItem(title=title, subtitle=_clean_subtitle(subtitle), url=link)


if __name__ == "__main__":
    item = fetch()
    if item:
        print(f"제목: {item.title}")
        print(f"부제: {item.subtitle}")
        print(f"링크: {item.url}")
