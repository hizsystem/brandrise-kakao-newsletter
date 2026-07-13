"""
자체 큐레이션 마케팅 뉴스 수집기
마케팅 미디어 RSS를 모아 Claude가 마케터 관점으로 7건 선별·요약한다.
아이보스 뉴스클리핑 대체 (2026-07-13 — i-boss.co.kr이 GitHub Actions 러너 IP를 403 차단).
기사마다 실제 원문 URL이 있어 뉴스레터에서 항목별 링크가 가능하다.
"""

import json
import re
from dataclasses import dataclass
from datetime import timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import List, Optional

import httpx
import requests
from bs4 import BeautifulSoup

from collectors.iboss import NewsItem
from timeutil import now_kst

# 피드 목록 — config의 curated_news.feeds로 덮어쓸 수 있다 (없으면 이 기본값 사용)
DEFAULT_FEEDS = [
    {"name": "매드타임스", "url": "https://www.madtimes.org/rss/allArticle.xml"},
    {"name": "브랜드브리프", "url": "https://www.brandbrief.co.kr/rss/allArticle.xml"},
    {"name": "모비인사이드", "url": "https://www.mobiinside.co.kr/feed/"},
    {"name": "바이라인네트워크", "url": "https://byline.network/feed/"},
    {"name": "플래텀", "url": "https://platum.kr/feed"},
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

FEED_TIMEOUT = 15
LLM_TIMEOUT = 120
LLM_MAX_TOKENS = 4000
MAX_CANDIDATES = 60
DEFAULT_COUNT = 7
KST = timezone(timedelta(hours=9))


@dataclass
class Candidate:
    source: str
    title: str
    description: str
    url: str
    published: object  # naive KST datetime


def fetch(config: dict, count: int = DEFAULT_COUNT) -> List[NewsItem]:
    """RSS 후보 수집 → Claude 선별·요약 → NewsItem 리스트.

    Claude 호출이 실패하면 최신순·소스 다양성 기준의 결정적 폴백으로 대신한다.
    """
    feeds = (config.get("curated_news") or {}).get("feeds") or DEFAULT_FEEDS
    candidates = _collect_candidates(feeds)
    if not candidates:
        raise RuntimeError("RSS 후보 기사가 없습니다 (전 피드 수집 실패 또는 기간 내 기사 없음)")

    items = _curate_with_llm(candidates, config, count)
    if items:
        return items

    print("  [WARN] 뉴스 큐레이션 LLM 실패 — 최신순 폴백 선별 사용")
    return _fallback_pick(candidates, count)


def _collect_candidates(feeds: list) -> List[Candidate]:
    """전 피드에서 최근 기사 수집 (월요일은 주말 포함 72시간, 그 외 36시간)."""
    now = now_kst()
    window_hours = 72 if now.weekday() == 0 else 36
    cutoff = now - timedelta(hours=window_hours)

    candidates: List[Candidate] = []
    seen_titles = set()
    for feed in feeds:
        try:
            entries = _fetch_feed(feed["name"], feed["url"])
        except Exception as e:
            print(f"  [WARN] 피드 수집 실패({feed['name']}): {e}")
            continue
        for c in entries:
            if c.published and c.published < cutoff:
                continue
            key = _norm_title(c.title)
            if not key or key in seen_titles:
                continue
            seen_titles.add(key)
            candidates.append(c)

    # 최신순 정렬 후 상한 적용 (LLM 프롬프트 크기 제한)
    candidates.sort(key=lambda c: c.published, reverse=True)
    return candidates[:MAX_CANDIDATES]


def _fetch_feed(name: str, url: str) -> List[Candidate]:
    r = requests.get(url, headers=HEADERS, timeout=FEED_TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.content, "xml")  # lxml — CDATA 깨진 피드도 관대하게 파싱

    entries = []
    for item in soup.find_all("item"):
        title = _text(item, "title")
        link = _text(item, "link")
        if not title or not link:
            continue
        entries.append(Candidate(
            source=name,
            title=title,
            description=_clean_html(_text(item, "description"))[:300],
            url=_strip_tracking(link),
            published=_parse_pubdate(_text(item, "pubDate")),
        ))
    return entries


def _strip_tracking(url: str) -> str:
    """utm_* 등 추적 파라미터 제거 (플래텀 RSS 링크에 인코딩된 한글 utm이 길게 붙음)."""
    from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
    parts = urlsplit(url)
    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if not k.lower().startswith("utm_")]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), ""))


def _text(item, tag: str) -> str:
    el = item.find(tag)
    return el.get_text(strip=True) if el else ""


def _clean_html(text: str) -> str:
    if not text:
        return ""
    plain = BeautifulSoup(text, "html.parser").get_text(separator=" ")
    return re.sub(r"\s+", " ", plain).strip()


def _parse_pubdate(raw: str):
    """RFC822(워드프레스, tz 포함)와 'YYYY-MM-DD HH:MM:SS'(ndsoft, KST naive) 모두 처리."""
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo:
            dt = dt.astimezone(KST).replace(tzinfo=None)
        return dt
    except (TypeError, ValueError):
        pass
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})", raw)
    if m:
        from datetime import datetime
        return datetime(*(int(g) for g in m.groups()))
    return None


def _norm_title(title: str) -> str:
    return re.sub(r"[\s\W_]+", "", title).lower()


def _curate_with_llm(candidates: List[Candidate], config: dict, count: int) -> List[NewsItem]:
    api_key = (config.get("anthropic") or {}).get("api_key", "")
    model = (config.get("anthropic") or {}).get("model", "claude-sonnet-4-6")
    if not api_key:
        return []

    prompt = _build_prompt(candidates, count)
    try:
        with httpx.Client(timeout=LLM_TIMEOUT) as client:
            r = client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": LLM_MAX_TOKENS,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
        r.raise_for_status()
        text = r.json()["content"][0]["text"].strip()
    except Exception as e:
        print(f"  [WARN] 뉴스 큐레이션 Claude 실패: {e}")
        return []

    return _parse_llm_response(text, candidates, count)


def _build_prompt(candidates: List[Candidate], count: int) -> str:
    lines = [
        f"[{i}] ({c.source}) {c.title}" + (f" — {c.description}" if c.description else "")
        for i, c in enumerate(candidates)
    ]
    numbered = "\n".join(lines)
    return f"""당신은 국내 마케터 대상 데일리 뉴스레터의 뉴스 에디터입니다.
아래 후보 기사 중 마케터에게 가장 유용한 {count}건을 골라 요약해주세요.

## 선별 기준
- 우선: 플랫폼(네이버·카카오·구글·메타·유튜브·인스타그램·틱톡 등)의 광고·검색·커머스 변화, 광고·마케팅 업계 동향, 소비 트렌드, AI와 마케팅, 이커머스·리테일 전략, 주목할 브랜드 캠페인
- 제외: 인사·부고·포토뉴스, 마케터 시사점 없는 기업 홍보성 보도자료, 세미나·수강생 모집 공고
- 같은 사건을 다룬 기사는 1건만. 서로 다른 주제·출처로 다양하게 구성
- 중요한 순서로 정렬

## 요약 규칙
- title: 후보 제목을 간결하게 정리 (그대로 써도 됨, 40자 이내 권장)
- summary: 2~4문장, 200자 내외. 제공된 제목·설명에 있는 사실만 사용하고 추측·과장 금지. 숫자와 고유명사 보존. 가능하면 마지막 문장에 마케터 관점의 시사점
- 문어체 평서문으로 쓴다 ("~했다", "~된다", "~전망이다")

## 후보 기사
{numbered}

## 출력 형식
아래 JSON 배열만 출력한다. 코드펜스·설명·주석 금지.
[{{"index": 후보번호, "title": "...", "summary": "..."}}]"""


def _parse_llm_response(text: str, candidates: List[Candidate], count: int) -> List[NewsItem]:
    m = re.search(r"\[[\s\S]*\]", text)
    if not m:
        print("  [WARN] 뉴스 큐레이션 응답에서 JSON을 찾지 못함")
        return []
    try:
        picks = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        print(f"  [WARN] 뉴스 큐레이션 JSON 파싱 실패: {e}")
        return []

    items: List[NewsItem] = []
    for pick in picks[:count]:
        try:
            idx = int(pick["index"])
            title = str(pick["title"]).strip()
            summary = str(pick["summary"]).strip()
        except (KeyError, TypeError, ValueError):
            continue
        if not (0 <= idx < len(candidates)) or not title or not summary:
            continue
        items.append(NewsItem(title=title, summary=summary, url=candidates[idx].url))
    return items


def _fallback_pick(candidates: List[Candidate], count: int) -> List[NewsItem]:
    """LLM 없이 최신순으로 뽑되 한 소스가 절반을 넘지 않게 분산. 요약은 RSS 설명 그대로."""
    per_source_cap = max(1, count // 2)
    picked: List[Candidate] = []
    source_counts: dict = {}
    for c in candidates:
        if source_counts.get(c.source, 0) >= per_source_cap:
            continue
        picked.append(c)
        source_counts[c.source] = source_counts.get(c.source, 0) + 1
        if len(picked) >= count:
            break
    return [NewsItem(title=c.title, summary=c.description, url=c.url) for c in picked]


if __name__ == "__main__":
    import sys, io, yaml
    from pathlib import Path
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    cfg_path = Path(__file__).resolve().parent.parent / "config.yaml"
    with open(cfg_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    for i, it in enumerate(fetch(cfg), 1):
        print(f"\n{i}. {it.title}")
        print(f"   {it.summary}")
        print(f"   {it.url}")
