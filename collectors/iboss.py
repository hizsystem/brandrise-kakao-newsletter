"""
아이보스 마케팅 뉴스 클리핑 스크래퍼
게시판: https://www.i-boss.co.kr/ab-7214
오늘 날짜 뉴스클리핑 글을 자동으로 찾아서 파싱
"""

import requests
import re
import time
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import List
from datetime import datetime
from timeutil import now_kst


@dataclass
class NewsItem:
    title: str
    summary: str
    url: str = ""


BOARD_URL = "https://www.i-boss.co.kr/ab-7214"
BASE_URL = "https://www.i-boss.co.kr"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


# i-boss가 간헐적으로 5xx(목록 520, 기사 500 등)를 반환 → 재시도로 일시적 오류 흡수
_TRANSIENT_STATUS = {500, 502, 503, 504, 520, 521, 522, 523, 524}


def _get(url: str, retries: int = 3, backoff: float = 3.0) -> requests.Response:
    """일시적 5xx 오류는 재시도. 마지막 시도까지 실패하면 예외 전파."""
    last_exc = None
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            r.encoding = "utf-8"
            return r
        except requests.exceptions.HTTPError as e:
            last_exc = e
            status = e.response.status_code if e.response is not None else None
            if status not in _TRANSIENT_STATUS or attempt == retries - 1:
                raise
            print(f"  [아이보스] {status} 일시 오류, 재시도 {attempt + 1}/{retries - 1}...")
            time.sleep(backoff)
        except requests.exceptions.RequestException as e:
            last_exc = e
            if attempt == retries - 1:
                raise
            print(f"  [아이보스] 요청 오류({e}), 재시도 {attempt + 1}/{retries - 1}...")
            time.sleep(backoff)
    if last_exc:
        raise last_exc
    raise RuntimeError("아이보스 요청 실패")


def fetch(url: str = BOARD_URL) -> List[NewsItem]:
    """오늘 날짜 뉴스클리핑 글을 찾아서 파싱"""
    today = now_kst()
    today_str = f"{today.month}월 {today.day}일"

    # 게시판 목록에서 오늘 글 링크 찾기
    r = _get(url)
    soup = BeautifulSoup(r.text, "html.parser")

    post_url = _find_todays_post(soup, today_str)

    if not post_url:
        print(f"  [아이보스] 오늘({today_str}) 뉴스클리핑 글을 찾지 못했습니다.")
        return []

    # 글 페이지 파싱
    full_url = post_url if post_url.startswith("http") else f"{BASE_URL}/{post_url.lstrip('/')}"
    r2 = _get(full_url)
    items = parse_post(r2.text)
    # 개별 기사 URL이 없으면 아이보스 포스트 URL로 채움
    for item in items:
        if not item.url:
            item.url = full_url
    return items



def _find_todays_post(soup, today_str: str) -> str:
    """게시판 목록에서 오늘 날짜 뉴스클리핑 링크 반환"""
    # 정확한 게시글 링크 패턴: ab-숫자-숫자 형태
    post_pattern = re.compile(r"^ab-\d+-\d+$")
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        href = a.get("href", "").strip("/")
        # "[3월 10일 마케팅 뉴스클리핑]" + 게시글 URL 패턴
        if today_str in text and "클리핑" in text and post_pattern.match(href):
            return href
    return ""


def parse_post(html: str) -> List[NewsItem]:
    """뉴스클리핑 글 본문에서 번호 매겨진 항목 파싱"""
    soup = BeautifulSoup(html, "html.parser")
    items: List[NewsItem] = []

    # 본문 컨테이너 찾기 (아이보스 클래스: ABA-article-contents, content_view)
    content = (
        soup.select_one(".ABA-article-contents")
        or soup.select_one(".content_view")
        or soup.select_one(".bo_v_con")
        or soup.select_one("#bo_v_con")
        or soup.select_one(".view_content")
    )

    # 본문 텍스트 전체로 fallback
    if not content:
        content = soup.select_one("body")

    if not content:
        return []

    # DOM 기반으로 외부 링크 목록 미리 수집 (i-boss.co.kr 제외한 외부 도메인만)
    external_links: List[str] = []
    for a in content.find_all("a", href=True):
        h = a.get("href", "").strip()
        if h.startswith("http") and "i-boss.co.kr" not in h:
            external_links.append(h)

    text = content.get_text(separator="\n")
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    current_title = ""
    current_summary_lines: List[str] = []
    current_url = ""
    link_idx = 0  # external_links 순서대로 각 기사에 배정

    for line in lines:
        # "1. 제목" 패턴
        m = re.match(r"^(\d{1,2})\.\s+(.+)$", line)
        if m:
            if current_title:
                items.append(NewsItem(
                    title=current_title,
                    summary=" ".join(current_summary_lines),
                    url=current_url,
                ))
                if current_url and current_url != "":
                    link_idx += 1
            current_title = m.group(2)
            current_summary_lines = []
            # DOM에서 찾은 외부 링크를 순서대로 배정
            current_url = external_links[link_idx] if link_idx < len(external_links) else ""
        elif current_title:
            # 텍스트에 URL이 직접 있으면 우선 사용
            if re.match(r"^(https?://)", line) and not current_url:
                current_url = line.strip()
            elif (len(line) > 15
                  and not line.startswith("[")
                  and not line.startswith("출처")
                  and not re.match(r"^(https?://|www\.)", line)):
                current_summary_lines.append(line)

    if current_title:
        items.append(NewsItem(
            title=current_title,
            summary=" ".join(current_summary_lines),
            url=current_url,
        ))

    return items


if __name__ == "__main__":
    items = fetch()
    print(f"수집된 뉴스 {len(items)}건")
    for i, item in enumerate(items, 1):
        print(f"\n{i}. {item.title}")
        print(f"   {item.summary[:100]}")
