"""
스티비(Stibee) 공유 링크 뉴스레터 파서
풋풋레터, 캐릿 등 stibee.com/api/v1.0/emails/share/... 형태 URL 파싱
"""

import requests
import re
from bs4 import BeautifulSoup
from dataclasses import dataclass, field
from typing import List, Optional

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


@dataclass
class StibeeNewsletter:
    source: str          # 풋풋레터 / 캐릿 등
    issue: str           # 호수 (예: 232호 | 2026.03.10)
    title: str           # 이번 호 주제 / 캐릿 헤드라인
    summary_items: List[str] = field(default_factory=list)  # 주요 항목
    url: str = ""
    topic: str = ""      # 풋풋레터: 이번 주 토픽
    terms: str = ""      # 풋풋레터: 이번 주 마케팅·트렌드 용어


def fetch(url: str, source_name: str = "") -> Optional[StibeeNewsletter]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        r.encoding = "utf-8"
        return parse(r.text, source_name=source_name, url=url)
    except Exception as e:
        print(f"  [WARN] 스티비 수집 실패 ({source_name}): {e}")
        return None


def parse(html: str, source_name: str = "", url: str = "") -> Optional[StibeeNewsletter]:
    soup = BeautifulSoup(html, "html.parser")
    text_lines = [l.strip() for l in soup.get_text(separator="\n").splitlines() if l.strip()]

    issue = ""
    title = ""
    summary_items: List[str] = []

    # 풋풋레터 파싱
    if "풋풋" in source_name or _detect_putput(text_lines):
        return _parse_putput(text_lines, url, source_name or "풋풋레터")

    # 캐릿 파싱
    if "캐릿" in source_name or _detect_careet(text_lines):
        return _parse_careet(text_lines, url, source_name or "캐릿")

    # 까탈로그 파싱
    if "까탈" in source_name or _detect_catalogue(text_lines):
        return _parse_catalogue(text_lines, url, source_name or "까탈로그")

    # 범용 파싱 (fallback)
    return _parse_generic(text_lines, url, source_name)


def _detect_putput(lines: List[str]) -> bool:
    return any("풋풋" in l or "putput" in l.lower() for l in lines[:10])


def _detect_careet(lines: List[str]) -> bool:
    return any("캐릿" in l or "careet" in l.lower() or "🥕" in l for l in lines[:10])


def _parse_putput(lines: List[str], url: str, source_name: str) -> StibeeNewsletter:
    issue = ""
    title = ""
    topic = ""
    terms = ""
    summary_items = []

    for i, line in enumerate(lines):
        # 호수: "232호 | 2026.03.10"
        if re.match(r"^\d+호\s*\|", line) and not issue:
            issue = line
        # 이번 주 토픽 / 이번 주 풋풋레터는? — 다음 줄이 이번 호 헤드라인
        if not topic and ("이번 주 토픽" in line or "이번 주 풋풋레터" in line):
            if i + 1 < len(lines):
                topic = lines[i + 1]
                title = topic  # title도 같이 세팅
        # 이번 주 마케팅·트렌드 용어 (휴재 안내문은 제외)
        if not terms and "마케팅" in line and "용어" in line and i + 1 < len(lines):
            cand = lines[i + 1]
            if "쉬어가" not in cand:
                terms = cand
        # ▪️ 항목들
        if line.startswith("▪️") or line.startswith("▪"):
            clean = line.lstrip("▪️").strip()
            if clean and len(clean) > 5:
                summary_items.append(clean)

    if not title:
        for line in lines[:20]:
            clean = re.sub(r"^\(광고\)", "", line).strip()
            if len(clean) > 15 and "풋풋" not in clean and "매주 화요일" not in clean:
                title = clean
                break

    return StibeeNewsletter(
        source=source_name,
        issue=issue,
        title=title,
        summary_items=summary_items[:3],
        url=url,
        topic=topic,
        terms=terms,
    )


def _parse_careet(lines: List[str], url: str, source_name: str) -> StibeeNewsletter:
    issue = ""
    title = ""
    summary_items = []

    for i, line in enumerate(lines):
        # 호수: "vol.293" or "2026 / 3 / 10 🥕"
        if re.match(r"^vol\.\d+", line, re.IGNORECASE) and not issue:
            issue = line
        if re.match(r"^\d{4}\s*/\s*\d+\s*/\s*\d+", line):
            if issue:
                issue = f"{issue} | {line.replace('🥕','').strip()}"
            else:
                issue = line.replace("🥕", "").strip()

        # 이번 주 주제 (첫 번째 줄 또는 subtitle 형태)
        clean_line = re.sub(r"^\(광고\)\s*", "", line)
        if not title and len(clean_line) > 5 and "캐릿" not in clean_line and "🥕" not in clean_line and "vol" not in clean_line.lower() and not clean_line.startswith("※") and not clean_line.startswith("["):
            if re.search(r"[가-힣]", clean_line):  # 한글 포함
                title = clean_line

        # 트렌드 항목: ✔ 또는 # 키워드
        if line.startswith("✔") or line.startswith("#"):
            clean = line.lstrip("✔#").strip()
            if clean and len(clean) > 5:
                summary_items.append(clean)
        if len(summary_items) >= 3:
            break

    # title fallback: 첫 줄 (해시태그 없는 것)
    if not title:
        for line in lines[:5]:
            if len(line) > 10 and "#" not in line:
                title = line
                break

    return StibeeNewsletter(
        source=source_name,
        issue=issue,
        title=title,
        summary_items=summary_items[:3],
        url=url,
    )


def _detect_catalogue(lines: List[str]) -> bool:
    return any("까탈" in l for l in lines[:5])


def _parse_catalogue(lines: List[str], url: str, source_name: str) -> StibeeNewsletter:
    summary_items = []
    for line in lines:
        # "#유행🧈 달리면서 버터 만들기?" 형식
        if line.startswith("#") and len(line) > 3:
            item = line.lstrip("#").strip()
            if item:
                summary_items.append(item)
    return StibeeNewsletter(
        source=source_name,
        issue="",
        title="까탈스럽게 고른 취향 뉴스레터",
        summary_items=summary_items,
        url=url,
    )


def _parse_generic(lines: List[str], url: str, source_name: str) -> Optional[StibeeNewsletter]:
    title = next((l for l in lines[:10] if len(l) > 15), "")
    return StibeeNewsletter(source=source_name, issue="", title=title, url=url)


if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    for name, url in [
        ("풋풋레터", "https://stibee.com/api/v1.0/emails/share/wEKaVmGldJJWX78nmPEFqirOyv2jtzs"),
        ("캐릿",    "https://stibee.com/api/v1.0/emails/share/Epk_eMdx6KjaXAqeaGAWWQUg3EGiYHc"),
    ]:
        item = fetch(url, source_name=name)
        if item:
            print(f"\n=== {item.source} ===")
            print(f"호수: {item.issue}")
            print(f"제목: {item.title}")
            for s in item.summary_items:
                print(f"  - {s}")
