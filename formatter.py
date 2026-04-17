"""
Claude API를 사용해 수집된 뉴스를 카톡 전송 양식으로 포맷팅
"""

import httpx
from datetime import datetime
from typing import List, Optional

from collectors.iboss import NewsItem
from collectors.neusral import CategoryNews
from collectors.email_reader import EmailNewsletter
from collectors.heypop import HeypopItem
from collectors.longblack import LongblackItem


WEEKDAY_GREETINGS = {
    0: ("월요일", "한 주를 힘차게 시작하시길 바랍니다!"),
    1: ("화요일", "이번 주도 좋은 흐름 이어가세요!"),
    2: ("수요일", "한 주의 중반, 좋은 인사이트 얻으시길 바랍니다!"),
    3: ("목요일", "주말이 다가오고 있습니다, 마무리 잘 하세요!"),
    4: ("금요일", "한 주 수고 많으셨습니다!"),
    5: ("토요일", "주말도 배움을 멈추지 않는 여러분을 응원합니다!"),
    6: ("일요일", "내일을 위한 인사이트, 미리 챙겨가세요!"),
}


def build_message(
    iboss_items: List[NewsItem],
    neusral_categories: List[CategoryNews],
    email_newsletters: dict,
    heypop_items: List[HeypopItem],
    api_key: str,
    model: str = "claude-sonnet-4-6",
) -> str:
    today = datetime.now()
    date_str = today.strftime("%-m월 %-d일").replace("-", "")  # Windows에서는 %#m, %#d
    weekday = today.weekday()
    weekday_name, weekday_msg = WEEKDAY_GREETINGS.get(weekday, ("", ""))

    # --- 헤더 ---
    lines = [f"📌{date_str} 마케팅 뉴스", ""]

    # --- 아이보스 메인 뉴스 (번호 매겨진 항목) ---
    for i, item in enumerate(iboss_items, 1):
        lines.append(f"{i}. {item.title}")
        if item.summary:
            lines.append(item.summary)
        lines.append("")

    # --- 뉴스럴 카테고리별 헤드라인 ---
    for cat in neusral_categories:
        lines.append(f"🏷️{cat.category} ")
        for headline in cat.headlines:
            lines.append(f"- {headline}")
        lines.append("")

    # --- 헤이팝 (목요일) ---
    if heypop_items:
        lines.append("📌전시/팝업/공간 추천 [헤이팝 레터]")
        lines.append("")
        for item in heypop_items[:2]:
            lines.append(f"✅ {item.title}")
            if item.description:
                lines.append(item.description)
            if item.url:
                lines.append(item.url)
            lines.append("")

    # --- 롱블랙 ---
    longblack = email_newsletters.get("longblack")
    if longblack:
        lines.append(f"📌 {longblack.subject}")
        lines.append("")
        if longblack.link:
            lines.append(longblack.link)
        lines.append("")

    # --- 기타 이메일 뉴스레터 ---
    for name, newsletter in email_newsletters.items():
        if name == "longblack":
            continue
        lines.append(f"📌 [{newsletter.source}] {newsletter.subject}")
        if newsletter.link:
            lines.append(newsletter.link)
        lines.append("")

    # --- AI 인사말 생성 ---
    greeting = generate_greeting(
        api_key=api_key,
        model=model,
        iboss_items=iboss_items,
        weekday_name=weekday_name,
        weekday_msg=weekday_msg,
    )
    lines.append(greeting)

    return "\n".join(lines)


def _build_greeting_prompt(
    iboss_items: List[NewsItem],
    weekday_name: str,
    weekday_msg: str,
    longblack_item: Optional[LongblackItem] = None,
    stibee_items: list = None,
    heypop_items: List[HeypopItem] = None,
) -> str:
    """인사말 생성용 프롬프트 조립"""
    news_context = "\n".join([
        f"- {item.title}: {item.summary[:80]}" for item in iboss_items[:7]
    ])

    if longblack_item:
        news_context += f"\n\n[롱블랙 오늘의 아티클]\n- {longblack_item.title}"
        if longblack_item.subtitle:
            news_context += f": {longblack_item.subtitle[:80]}"

    if heypop_items:
        news_context += "\n\n[헤이팝 전시/팝업 추천]"
        for item in heypop_items[:2]:
            news_context += f"\n- {item.title}: {item.description[:60]}"

    for item in (stibee_items or []):
        news_context += f"\n\n[{item.source}]"
        if item.title:
            news_context += f"\n- {item.title}"
        if item.topic:
            news_context += f" (토픽: {item.topic})"

    today = datetime.now()
    special_date_note = ""
    if today.day == 1:
        special_date_note = f"\n- 오늘은 {today.month}월의 첫날임을 첫 문단 어딘가에 자연스럽게 언급해줘 (예: \"{today.month}월의 첫날\", \"{today.month}월이 시작됐습니다\" 등 — 억지스럽지 않게)"

    return f"""아래 오늘의 마케팅 뉴스를 바탕으로 카카오톡 오픈채팅방 인사말을 작성해줘.

참고 예시 (이 형식과 길이를 따라줘):
---
안녕하세요! 월요일 마케팅 소식 전해드립니다 😊 오늘은 플랫폼 구조 변화와 글로벌 커머스 확장이 눈에 띄는 하루입니다. 다음의 실시간 트렌드 도입처럼 콘텐츠 탐색 방식이 다시 변화하고 있고, 카페24의 아마존 API 연동은 국내 브랜드의 해외 판매 장벽을 낮추며 D2C 글로벌 진출 흐름을 강화하는 모습입니다.

한편 이커머스 시장에서는 쿠팡·네이버처럼 물류·광고·핀테크를 결합한 플랫폼은 성장하는 반면, 단순 중개 중심 모델은 한계를 드러내며 수익 구조의 차별화가 더욱 중요해지고 있습니다. 동시에 그린워싱 적발 사례처럼 브랜드 메시지에서도 신뢰와 근거가 점점 더 중요한 기준이 되고 있습니다.

월요일 힘차게 시작하시고, 이번 주도 좋은 인사이트 많이 얻으시길 바랍니다! 🚀
---

작성 조건:
- {weekday_name} 인사로 시작 (예: "안녕하세요! {weekday_name} 마케팅 소식 전해드립니다 😊"){special_date_note}
- 아래 모든 콘텐츠 중에서 가장 흥미롭거나 중요한 1-2개를 골라 중심 소재로 삼아줘 (매번 마케팅 뉴스만 다루지 말 것)
- 롱블랙 아티클, 헤이팝 전시/팝업, 풋풋레터, 캐릿 등이 있으면 이 중 하나를 메인 화제로 삼아도 좋음
- 2개 문단으로 자연스럽게 연결하되, "~가 눈에 띈다", "~가 주목된다" 같은 상투적 표현을 피하고 매번 다른 문체로 작성
- 마지막 문장은 "{weekday_msg}" 분위기로 마무리 + 이모지 1개
- 총 3문단, 예시와 비슷한 길이
- 존댓말, 따뜻하고 전문적인 톤
- 반드시 100% 한국어로만 작성. 한자(漢字), 영어, 일본어, 베트남어 등 외국어 단어를 절대 섞지 마. 한글과 이모지만 사용.

오늘의 뉴스:
{news_context}

인사말만 작성 (다른 설명 없이):"""



import re as _re

def _strip_think_tags(text: str) -> str:
    """Qwen 등 모델의 <think>...</think> 사고 과정 태그 제거"""
    return _re.sub(r"<think>.*?</think>\s*", "", text, flags=_re.DOTALL).strip()


def _call_groq(api_key: str, model: str, prompt: str) -> str:
    """Groq REST API 호출"""
    with httpx.Client(timeout=30) as client:
        r = client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1000,
            },
        )
    r.raise_for_status()
    raw = r.json()["choices"][0]["message"]["content"].strip()
    return _strip_think_tags(raw)


def _call_gemini(api_key: str, model: str, prompt: str) -> str:
    """Gemini REST API 호출"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    with httpx.Client(timeout=30) as client:
        r = client.post(
            url,
            headers={"content-type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": 1000},
            },
        )
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()


def _call_claude(api_key: str, model: str, prompt: str) -> str:
    """Claude REST API 호출 (폴백)"""
    with httpx.Client(timeout=30) as client:
        r = client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
    r.raise_for_status()
    return r.json()["content"][0]["text"].strip()


def generate_greeting(
    api_key: str,
    model: str,
    iboss_items: List[NewsItem],
    weekday_name: str,
    weekday_msg: str,
    longblack_item: Optional[LongblackItem] = None,
    stibee_items: list = None,
    heypop_items: List[HeypopItem] = None,
    groq_api_key: str = "",
    groq_model: str = "llama-3.3-70b-versatile",
    gemini_api_key: str = "",
    gemini_model: str = "gemini-2.0-flash",
) -> str:
    """오늘의 뉴스 기반 인사말 생성 (Groq 우선 → Gemini → Claude 폴백, 전부 무료/저비용)"""
    prompt = _build_greeting_prompt(
        iboss_items=iboss_items,
        weekday_name=weekday_name,
        weekday_msg=weekday_msg,
        longblack_item=longblack_item,
        stibee_items=stibee_items,
        heypop_items=heypop_items,
    )

    # 1차: Claude (품질 우선)
    if api_key:
        try:
            result = _call_claude(api_key, model, prompt)
            print("  [OK] Claude로 인사말 생성 완료")
            return result
        except Exception as e:
            print(f"  [WARN] Claude 인사말 생성 실패: {e}")

    # 2차: Groq (폴백)
    if groq_api_key:
        try:
            result = _call_groq(groq_api_key, groq_model, prompt)
            print("  [OK] Groq로 인사말 생성 완료 (폴백)")
            return result
        except Exception as e:
            print(f"  [WARN] Groq 인사말 생성 실패: {e}")

    # 3차: Gemini (폴백)
    if gemini_api_key:
        try:
            result = _call_gemini(gemini_api_key, gemini_model, prompt)
            print("  [OK] Gemini로 인사말 생성 완료 (폴백)")
            return result
        except Exception as e:
            print(f"  [WARN] Gemini 인사말 생성 실패: {e}")

    # 4차: 기본 인사말
    return f"안녕하세요! {weekday_name} 마케팅 소식 전해드립니다 😊 {weekday_msg}"


def build_message_windows_date(
    iboss_items: List[NewsItem],
    neusral_categories: List[CategoryNews],
    email_newsletters: dict,
    heypop_items: List[HeypopItem],
    api_key: str,
    model: str = "claude-sonnet-4-6",
    longblack_item=None,
    stibee_items: list = None,
    greeting: str = None,
) -> str:
    """Windows 호환 날짜 포맷 버전"""
    today = datetime.now()
    # Windows에서는 %-m 미지원 → lstrip("0") 사용
    month = str(today.month)
    day = str(today.day)
    date_str = f"{month}월 {day}일"
    weekday = today.weekday()
    weekday_name, weekday_msg = WEEKDAY_GREETINGS.get(weekday, ("", ""))

    lines = [f"📌{date_str} 마케팅 뉴스", ""]

    for i, item in enumerate(iboss_items, 1):
        lines.append(f"{i}. {item.title}")
        if item.summary:
            lines.append(item.summary)
        lines.append("")

    for cat in neusral_categories:
        lines.append(f"🏷️{cat.category} ")
        for headline in cat.headlines:
            lines.append(f"- {headline}")
        lines.append("")

    if heypop_items:
        lines.append("📌전시/팝업/공간 추천 [헤이팝 레터]")
        lines.append("")
        for item in heypop_items[:2]:
            lines.append(f"✅ {item.title}")
            if item.description:
                lines.append(item.description)
            if item.url:
                lines.append(item.url)
            lines.append("")

    # 스티비 뉴스레터 (풋풋레터, 캐릿 등) - 롱블랙보다 앞
    for item in (stibee_items or []):
        if "풋풋" in item.source:
            lines.append("📌 바쁜 현대인을 위한 마케팅·트렌드 뉴스 [풋풋레터]")
            if item.title:
                lines.append(item.title)
            lines.append("")
            lines.append("(자세한 소식은 본문에서)")
            lines.append(item.url)
            lines.append("")
        elif "캐릿" in item.source:
            lines.append("📌 캐릿 트렌드 레터")
            if item.title:
                lines.append(item.title)
            lines.append("")
            lines.append(item.url)
            lines.append("")
        elif "까탈" in item.source:
            lines.append("📌까탈스럽게 고른 취향 뉴스레터 [까탈로그]")
            lines.append("")
            for idx, si in enumerate(item.summary_items, 1):
                lines.append(f"{idx}. {si}")
            lines.append("")
            lines.append("(자세한 소식은 본문에서)")
            lines.append(item.url)
            lines.append("")
        else:
            header = f"📌 {item.source}"
            if item.issue:
                header += f" {item.issue}"
            lines.append(header)
            if item.title:
                lines.append(item.title)
            lines.append(item.url)
            lines.append("")

    # 롱블랙 (웹 스크래핑 우선, 없으면 이메일)
    lb_from_email = email_newsletters.get("longblack")
    if longblack_item:
        lines.append(f"📌 {longblack_item.title}")
        lines.append("")
        lines.append(longblack_item.url)
        lines.append("")
    elif lb_from_email:
        lines.append(f"📌 {lb_from_email.subject}")
        lines.append("")
        if lb_from_email.link:
            lines.append(lb_from_email.link)
        lines.append("")

    # 기타 이메일 뉴스레터 (까탈로그 등)
    for name, newsletter in email_newsletters.items():
        if name == "longblack":
            continue
        lines.append(f"📌 {newsletter.subject}")
        if newsletter.link:
            lines.append(newsletter.link)
        lines.append("")

    if greeting is None:
        greeting = generate_greeting(
            api_key=api_key,
            model=model,
            iboss_items=iboss_items,
            weekday_name=weekday_name,
            weekday_msg=weekday_msg,
            longblack_item=longblack_item,
            stibee_items=stibee_items,
            heypop_items=heypop_items,
        )
    lines.append(greeting)

    return "\n".join(lines)
