"""
빌더조쉬(maily.so/josh) 뉴스레터 파서
og 메타 + 본문 추출 → LLM(Claude→Groq→Gemini 폴백)으로 3줄 요약 자동 생성
"""

import re
import requests
import httpx
from bs4 import BeautifulSoup
from typing import Optional

from collectors.stibee import StibeeNewsletter


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

BODY_CHAR_CAP = 4000  # LLM 입력 길이 제한 (Groq 무료 티어 토큰 제한 대응)
LLM_TIMEOUT = 60
LLM_MAX_TOKENS = 800


def fetch(
    url: str,
    config: dict,
    source_name: str = "빌더조쉬",
) -> Optional[StibeeNewsletter]:
    """maily.so 글 URL → StibeeNewsletter (3줄 요약 포함). 실패 시 None.

    config는 main.load_config() 결과 그대로 받음 (anthropic/groq/gemini 키 사용).
    """
    try:
        r = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        r.encoding = "utf-8"
    except Exception as e:
        print(f"  [WARN] 빌더조쉬 수집 실패 (요청): {e}")
        return None

    try:
        title, subtitle, body = _parse(r.text)
    except Exception as e:
        print(f"  [WARN] 빌더조쉬 파싱 실패: {e}")
        return None

    if not title or not body:
        print(
            f"  [WARN] 빌더조쉬 파싱 결과 부족 "
            f"(title={bool(title)}, body_len={len(body) if body else 0})"
        )
        return None

    summary_items = _summarize(body[:BODY_CHAR_CAP], config)

    return StibeeNewsletter(
        source=source_name,
        issue="",
        title=title,
        summary_items=summary_items,
        url=url,
        topic=subtitle,
        terms="",
    )


def _parse(html: str) -> tuple[str, str, str]:
    """og:title, og:description, 본문 텍스트 반환."""
    soup = BeautifulSoup(html, "html.parser")

    title = _meta(soup, "og:title")
    subtitle = _meta(soup, "og:description").strip()

    article = soup.find("article")
    if article:
        body = article.get_text(separator="\n", strip=True)
    else:
        main = soup.find("main")
        body = main.get_text(separator="\n", strip=True) if main else ""

    body = re.sub(r"\n{3,}", "\n\n", body)
    return title, subtitle, body


def _meta(soup: BeautifulSoup, prop: str) -> str:
    tag = soup.find("meta", attrs={"property": prop}) or soup.find(
        "meta", attrs={"name": prop}
    )
    return (tag.get("content") if tag else "") or ""


def _summarize(body: str, config: dict) -> list[str]:
    """Claude → Groq → Gemini 순으로 폴백. 모두 실패 시 빈 리스트."""
    prompt = f"""아래는 마케팅/비즈니스 분야의 인터뷰 또는 에세이 뉴스레터 본문입니다.
카카오톡 오픈채팅 독자(마케터·창업가)가 읽고 원문 클릭으로 이어지도록 3줄 요약을 작성해주세요.

## 작성 규칙
- 정확히 3줄. 각 줄은 한 문장, 60~90자.
- 핵심 인사이트·구체적 숫자·고유명사·도구명을 보존.
- "~합니다", "~해요" 어미는 피하고 종결어미는 "~." 또는 명사 종결 사용 (예: "월 5,000달러 고정수익을 설계." / "트레로·셜·n8n 조합으로 운영 표준화.").
- 줄마다 다른 측면(전략/타겟/실행)을 다루고 같은 표현 반복 금지.
- 번호·기호 없이 본문만 한 줄씩 출력. 머리말("요약:", "1." 등) 금지.

## 본문
---
{body}
---

위 본문을 3줄 요약해주세요."""

    api_key = (config.get("anthropic") or {}).get("api_key", "")
    model = (config.get("anthropic") or {}).get("model", "claude-sonnet-4-6")
    groq_key = (config.get("groq") or {}).get("api_key", "")
    groq_model = (config.get("groq") or {}).get("model", "llama-3.3-70b-versatile")
    gemini_key = (config.get("gemini") or {}).get("api_key", "")
    gemini_model = (config.get("gemini") or {}).get("model", "gemini-2.0-flash")

    if api_key:
        text = _call_claude(prompt, api_key, model)
        if text:
            return _parse_summary(text)
    if groq_key:
        text = _call_groq(prompt, groq_key, groq_model)
        if text:
            return _parse_summary(text)
    if gemini_key:
        text = _call_gemini(prompt, gemini_key, gemini_model)
        if text:
            return _parse_summary(text)
    return []


def _call_claude(prompt: str, api_key: str, model: str) -> str:
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
        return r.json()["content"][0]["text"].strip()
    except Exception as e:
        print(f"  [WARN] 빌더조쉬 요약 Claude 실패: {e}")
        return ""


def _call_groq(prompt: str, api_key: str, model: str) -> str:
    try:
        with httpx.Client(timeout=LLM_TIMEOUT) as client:
            r = client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": LLM_MAX_TOKENS,
                },
            )
        r.raise_for_status()
        raw = r.json()["choices"][0]["message"]["content"].strip()
        return re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    except Exception as e:
        print(f"  [WARN] 빌더조쉬 요약 Groq 실패: {e}")
        return ""


def _call_gemini(prompt: str, api_key: str, model: str) -> str:
    try:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={api_key}"
        )
        with httpx.Client(timeout=LLM_TIMEOUT) as client:
            r = client.post(
                url,
                headers={"content-type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"maxOutputTokens": LLM_MAX_TOKENS},
                },
            )
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        print(f"  [WARN] 빌더조쉬 요약 Gemini 실패: {e}")
        return ""


def _parse_summary(text: str) -> list[str]:
    lines = []
    for raw in text.splitlines():
        clean = raw.strip()
        clean = re.sub(r"^\s*(\d+[.)]|[-•·▪️])\s*", "", clean)
        if clean and len(clean) > 5:
            lines.append(clean)
    return lines[:3]


if __name__ == "__main__":
    import sys
    import io
    import yaml
    from pathlib import Path

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    cfg_path = Path(__file__).parent.parent / "config.yaml"
    with open(cfg_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    test_url = "https://maily.so/josh/posts/knrj1pn1rld"
    item = fetch(test_url, config=cfg)
    if item:
        print(f"source: {item.source}")
        print(f"title:  {item.title}")
        print(f"topic:  {item.topic}")
        print(f"url:    {item.url}")
        print("summary_items:")
        for i, s in enumerate(item.summary_items, 1):
            print(f"  {i}. {s}")
    else:
        print("FAILED")
