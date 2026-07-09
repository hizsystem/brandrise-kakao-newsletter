"""
Claude API를 사용해 수집된 뉴스를 카톡 전송 양식으로 포맷팅
"""

import httpx
import re as _re
from datetime import date, datetime, timedelta
from timeutil import now_kst
from pathlib import Path
from typing import List, Optional, Tuple

try:
    import holidays as _holidays
except ImportError:
    _holidays = None

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


# 금지 표현 (AI 클리셰 — 프롬프트로 1차 차단, 잔류 시 재교정)
_BANNED_PHRASES: Tuple[str, ...] = (
    "마음에 걸리",
    "눈에 띄",
    "주목된",
    "주목할 만",
    "엿볼 수 있",
    "한 모습입니다",
    "는 모습입니다",
    "낯설지 않",
    "사뭇 다르",
    "새삼 느끼",
    "다시 한번 실감",
)

# 월 기준 주차 표현 — 코드가 LLM에 '몇째 주' 정보를 주지 않으므로,
# LLM이 임의로 지어내면(예: "둘째 주") 사실 오류가 된다. 탐지 후 재교정한다.
# 상대 표현("이번 주", "한 주", "지난 주", "주말")은 매칭하지 않는다.
_WEEK_OF_MONTH_RE: _re.Pattern = _re.compile(
    r"(?:첫째|둘째|셋째|넷째|다섯째|여섯째|\d+\s*째)\s*주|\d+\s*주\s*차"
)


# 고유명사 한글 음역 → 일반 표기 치환 규칙
_PROPER_NOUN_FIXES: Tuple[Tuple[_re.Pattern, str], ...] = (
    (_re.compile(r"오픈\s*아이(?=[\s가-힣,.!?'\"]|$)"), "오픈AI"),
    (_re.compile(r"오픈\s*에이\s*아이"), "오픈AI"),
    (_re.compile(r"챗\s*지\s*피\s*티"), "챗GPT"),
    (_re.compile(r"(?<![가-힣A-Za-z])지피티(?![A-Za-z])"), "GPT"),
    (_re.compile(r"앤\s*쓰로픽"), "앤트로픽"),
    (_re.compile(r"엔트로픽"), "앤트로픽"),
    (_re.compile(r"클라우드(?=\s*(?:오퍼스|소넷|하이쿠|모델|API))"), "클로드"),
)

_OUTPUT_DIR = Path(__file__).parent

# 뉴스레터 맨 하단 고정 푸터 — 브랜드라이즈 무료 상담 안내
# (인사말·🔗 링크와 분리해 메시지 맨 끝에 붙인다. main.py 참조)
BRANDRISE_FOOTER = (
    "━━━━━━━━━━━━━\n"
    "혼자 고민하지 마세요 — 브랜드라이즈 무료 상담\n"
    "- 브랜드 진단부터 지금 당장 해야 할 우선순위까지, 30분 무료 상담에서 함께 정리해드려요.\n"
    "- 이미 수십 개 브랜드가 상담받았어요. 내 브랜드처럼, 함께 고민하는 팀원의 마음으로 봅니다.\n"
    "- 스타트업 대표·마케팅 담당자를 위한 30분 (주변 추천도 환영해요💛)\n"
    "- 무료 상담 신청 https://forms.gle/R5FaijsFD4VoTEsj9?utm_source=kakao&utm_medium=organic&utm_campaign=brandrise"
)


def _is_off_day(d: date) -> bool:
    """주말 / 한국 공휴일 / 근로자의 날(5/1) 여부"""
    if d.weekday() >= 5:
        return True
    if d.month == 5 and d.day == 1:  # 근로자의 날 (holidays 라이브러리 미포함)
        return True
    if _holidays is not None:
        try:
            return d in _holidays.KR(years=d.year)
        except Exception:
            return False
    return False


def _consecutive_off_days_after(today_d: date, limit: int = 14) -> int:
    """오늘 다음 날부터 연속된 비업무일(주말+공휴일) 수"""
    count = 0
    d = today_d + timedelta(days=1)
    while count < limit and _is_off_day(d):
        count += 1
        d += timedelta(days=1)
    return count


def _days_since_last_newsletter(today_d: date) -> int:
    """오늘 직전 가장 최근 output_*.txt와 오늘 사이의 일수 차이. 파일 없으면 0."""
    today_str = today_d.strftime("%Y%m%d")
    candidates: List[date] = []
    for f in _OUTPUT_DIR.glob("output_*.txt"):
        if today_str in f.name:
            continue
        m = _re.match(r"output_(\d{8})\.txt", f.name)
        if not m:
            continue
        try:
            d = datetime.strptime(m.group(1), "%Y%m%d").date()
        except ValueError:
            continue
        if d < today_d:
            candidates.append(d)
    if not candidates:
        return 0
    return (today_d - max(candidates)).days


def _time_of_day_hint(hour: int) -> Tuple[str, str]:
    """발송 시각(0~23) → (라벨, 톤 규칙)"""
    if 5 <= hour < 11:
        return (
            "아침 (오전)",
            "아침/오전 톤. 하루를 시작하는 분위기. "
            "'저녁', '밤', '늦은 시간', '오늘 하루 마무리', '푹 쉬세요', "
            "'한 주 마무리' 등 늦은 시간 인사는 절대 사용하지 말 것.",
        )
    if 11 <= hour < 14:
        return ("점심 (낮)", "낮 시간 톤. 저녁·밤 인사 사용 금지.")
    if 14 <= hour < 18:
        return ("오후", "오후 톤. 밤 인사 사용 금지.")
    if 18 <= hour < 22:
        return ("저녁", "저녁 톤. 아침 인사 사용 금지.")
    return ("밤/새벽", "야간 톤.")


def _normalize_proper_nouns(text: str) -> str:
    """한글 음역 고유명사를 일반 통용 표기로 치환"""
    for pattern, repl in _PROPER_NOUN_FIXES:
        text = pattern.sub(repl, text)
    return text


def _find_banned_phrases(text: str) -> List[str]:
    """텍스트에서 발견된 금지 표현 반환 (없으면 빈 리스트)"""
    return [p for p in _BANNED_PHRASES if p in text]


def _find_week_of_month(text: str) -> List[str]:
    """LLM이 임의로 지어낸 월 기준 주차 표현(첫째 주, 둘째 주, N주차 등) 반환"""
    return [m.group(0).strip() for m in _WEEK_OF_MONTH_RE.finditer(text)]


def _first_appearance_sources(stibee_items: list) -> List[str]:
    """오늘 이전 output_*.txt에 한 번도 등장한 적 없는 stibee source 이름 목록"""
    if not stibee_items:
        return []
    candidates = []
    seen_in_candidates = set()
    for item in stibee_items:
        src = getattr(item, "source", "")
        if src and src not in seen_in_candidates:
            candidates.append(src)
            seen_in_candidates.add(src)
    if not candidates:
        return []

    today_str = now_kst().strftime("%Y%m%d")
    past_files = [
        f for f in _OUTPUT_DIR.glob("output_*.txt") if today_str not in f.name
    ]
    appeared = set()
    for f in past_files:
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        for src in candidates:
            if src in appeared:
                continue
            if src in text:
                appeared.add(src)
    return [src for src in candidates if src not in appeared]


def _load_recent_greetings(n: int = 4) -> List[str]:
    """오늘 이전 최근 N개 output_*.txt에서 인사말 블록 추출"""
    today_str = now_kst().strftime("%Y%m%d")
    files = sorted(
        f for f in _OUTPUT_DIR.glob("output_*.txt") if today_str not in f.name
    )
    greetings: List[str] = []
    for f in files[-n:]:
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        m = _re.search(r"(안녕하세요![\s\S]*?)(?=\n\n🔗|$)", text)
        if m:
            greetings.append(m.group(1).strip())
    return greetings


def build_message(
    iboss_items: List[NewsItem],
    neusral_categories: List[CategoryNews],
    email_newsletters: dict,
    heypop_items: List[HeypopItem],
    api_key: str,
    model: str = "claude-sonnet-4-6",
) -> str:
    today = now_kst()
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
    recent_greetings: Optional[List[str]] = None,
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

    today = now_kst()
    time_label, time_rule = _time_of_day_hint(today.hour)

    notes: List[str] = []
    if today.day == 1:
        notes.append(
            f"오늘은 {today.month}월의 첫날입니다. 첫 문단에서 자연스럽게 언급해줘 "
            f"(예: \"{today.month}월의 첫날\", \"{today.month}월이 시작됐습니다\" 등 — 억지스럽지 않게)."
        )

    gap_days = _days_since_last_newsletter(today.date())
    off_after = _consecutive_off_days_after(today.date())

    # 직전 발송과 오늘 사이의 '쉬는 날'(주말+공휴일) 수.
    # 평범한 주말(금→월, 2일)은 연휴가 아니므로, 공휴일이 낀 3일 이상일 때만
    # '연휴'로 본다. 달력상 일수(gap_days)로 판단하면 매주 월요일이 오인된다.
    rest_days_before = 0
    if gap_days > 0:
        last_date = today.date() - timedelta(days=gap_days)
        d = last_date + timedelta(days=1)
        while d < today.date():
            if _is_off_day(d):
                rest_days_before += 1
            d += timedelta(days=1)

    if rest_days_before >= 3:
        notes.append(
            f"직전 발송 이후 {rest_days_before}일간의 연휴/공백 끝에 보내는 인사입니다. "
            "첫 문단에서 자연스럽게 반영해줘 — 예: \"연휴 잘 보내셨나요?\", "
            "\"연휴 끝에 오랜만에 인사드립니다\". 식상한 \"잘 쉬셨나요\" 반복이나 "
            "어색한 호들갑은 피하고, 차분하고 따뜻한 톤으로."
        )

    if off_after >= 3:
        notes.append(
            f"내일부터 {off_after}일 연속 휴일/주말이 이어집니다 (긴 연휴 직전 마지막 발송). "
            "첫 문단에서 \"긴 연휴 앞두고\", \"연휴 전 마지막 마케팅 소식\" 같은 맥락을 자연스럽게 드러내고, "
            "마지막 문장은 \"좋은 연휴 보내세요\" 분위기로 마무리해줘 (이모지 1개 포함)."
        )

    new_sources = _first_appearance_sources(stibee_items or [])
    if new_sources:
        sources_str = ", ".join(new_sources)
        notes.append(
            f"오늘부터 [{sources_str}] 코너가 뉴스레터에 처음 추가됩니다. "
            f"이번 회차의 중심 소재로 {sources_str}에서 다룬 주제를 활용해 인사말을 구성하고, "
            f"\"오늘부터 {sources_str} 소식도 함께 전해드립니다\" 같은 식으로 첫 추가 사실을 한 문장 정도 자연스럽게 녹여줘. "
            "공지처럼 딱딱하게 별도 문단으로 빼지 말고, 본문 흐름에 자연스럽게 포함시킬 것."
        )

    special_date_note = ""
    if notes:
        special_date_note = "\n- " + "\n- ".join(notes)

    recent_block = ""
    if recent_greetings:
        joined = "\n\n---\n\n".join(recent_greetings)
        recent_block = (
            "\n\n## 최근 인사말 (주제·표현·중심 소재·문장 구조가 겹치지 않게 작성)\n"
            "---\n"
            f"{joined}\n"
            "---"
        )

    return f"""아래 오늘의 마케팅 뉴스를 바탕으로 카카오톡 오픈채팅방 인사말을 작성해줘.

## 발송 컨텍스트 (가장 중요)
- 현재 시각: {today.strftime("%Y-%m-%d %H:%M")} ({weekday_name}, {time_label})
- 시간대 규칙: {time_rule}

## 참고 예시 (형식·길이 참고용)
---
안녕하세요! 월요일 마케팅 소식 전해드립니다 😊 오늘은 플랫폼 구조 변화와 글로벌 커머스 확장이 눈길을 끄는 하루입니다. 다음의 실시간 트렌드 도입처럼 콘텐츠 탐색 방식이 다시 변화하고 있고, 카페24의 아마존 API 연동은 국내 브랜드의 해외 판매 장벽을 낮추며 D2C 글로벌 진출 흐름을 강화하고 있습니다.

한편 이커머스 시장에서는 쿠팡·네이버처럼 물류·광고·핀테크를 결합한 플랫폼은 성장하는 반면, 단순 중개 중심 모델은 한계를 드러내며 수익 구조의 차별화가 더욱 중요해지고 있습니다. 동시에 그린워싱 적발 사례처럼 브랜드 메시지에서도 신뢰와 근거가 점점 더 중요한 기준이 되고 있습니다.

월요일 힘차게 시작하시고, 이번 주도 좋은 인사이트 많이 얻으시길 바랍니다! 🚀
---

## 작성 조건
- {weekday_name} 인사로 시작 (예: "안녕하세요! {weekday_name} 마케팅 소식 전해드립니다 😊"){special_date_note}
- 콘텐츠(마케팅 뉴스·롱블랙·헤이팝·풋풋레터·캐릿·까탈로그) 중 가장 흥미로운 1-2개를 중심 소재로. 매번 마케팅 뉴스만 다루지 말 것.
- 총 3문단, 예시와 비슷한 길이, 존댓말·따뜻하고 전문적인 톤
- 마지막 문장은 "{weekday_msg}" 분위기 + 이모지 1개. 단, 발송 시간대 규칙과 충돌하면 시간대 규칙이 우선.

## 표기 규칙 (엄격 준수)
- 한국어 본문을 기본으로 작성. 단, 잘 알려진 영문 브랜드·제품·약어는 영문 표기를 그대로 사용할 것.
- 고유명사 표기:
  - OpenAI → "오픈AI" (절대 금지: "오픈아이", "오픈에이아이")
  - ChatGPT → "챗GPT" (절대 금지: "챗지피티", "챗 지피티")
  - GPT / AI / CPC / MAU / API / SEO / D2C 등 영문 약어는 영문 그대로
  - Anthropic → "앤트로픽", Claude → "클로드", Gemini → "제미나이"
  - Meta → "메타", Google → "구글", YouTube → "유튜브", TikTok → "틱톡"
- 외래어를 한글로 음차(한국어 발음 그대로 옮기기) 하지 말 것. 영문 브랜드는 위 규칙대로 표기.

## 날짜·주차 규칙 (엄격 준수)
- 위에 제공된 요일({weekday_name})과 발송 시각 외의 달력 정보를 임의로 만들어내지 말 것.
- 특히 "몇째 주"(첫째 주·둘째 주·셋째 주…), "N주차" 같은 **월 기준 주차 표현은 절대 사용 금지**. 계산 근거가 주어지지 않아 사실 오류(예: 실제로 첫째 주인데 둘째 주로 표기)가 발생함.
- "이번 주", "한 주", "주말", "월초·월말" 같은 상대적·대략적 표현은 사용해도 됨.

## 출처·신규성 규칙 (엄격 준수)
- 특정 뉴스레터·코너(빌더조쉬·까탈로그·헤이팝·풋풋레터·캐릿·롱블랙 등)를 "오늘부터", "새로 시작", "처음", "첫 회차", "이제부터 함께" 같은 **신규 도입·최초 등장으로 단정하지 말 것**. 각 소스는 요일별로 정기 수록되며 오늘이 첫 등장이라는 근거가 없음(사실 오류 발생).
- 콘텐츠는 "오늘의 ○○ 소식", "○○에서는" 처럼 중립적으로 소개할 것.

## 금지 표현 (AI 티가 나는 상투어 — 절대 사용 금지)
- "마음에 걸리는", "눈에 띄는", "주목된다", "주목할 만", "엿볼 수 있는"
- "~한 모습입니다", "~는 모습입니다"
- "낯설지 않다", "사뭇 다르다", "새삼 느끼다", "다시 한번 실감"
- 이런 표현이 떠오르면 반드시 다른 구체적 동사·명사로 바꿔 쓸 것.{recent_block}

## 오늘의 뉴스
{news_context}

인사말만 작성 (다른 설명·머리말 없이 본문만):"""


def _build_critique_prompt(
    original: str,
    time_label: str,
    time_rule: str,
    banned_found: Optional[List[str]] = None,
    week_found: Optional[List[str]] = None,
) -> str:
    """생성된 인사말을 검토·교정하는 프롬프트"""
    extra = ""
    if banned_found:
        bullets = "\n".join(f"  - {p}" for p in banned_found)
        extra += (
            "\n\n## 특히 다음 표현이 원문에 남아 있습니다. 반드시 다른 자연스러운 표현으로 교체하세요.\n"
            f"{bullets}"
        )
    if week_found:
        bullets = "\n".join(f"  - {p}" for p in week_found)
        extra += (
            "\n\n## 다음은 근거 없이 지어낸 월 기준 주차 표현입니다. 반드시 삭제하거나 "
            '"이번 주" 등 상대 표현으로 교체하세요 (요일은 유지).\n'
            f"{bullets}"
        )
    return f"""다음은 카카오톡 오픈채팅방용 마케팅 뉴스레터 인사말입니다. 아래 기준으로 검토하고 문제가 있으면 자연스럽게 고쳐 재작성해주세요. 문제가 없으면 원문 그대로 출력하세요. 설명은 일절 덧붙이지 말고 인사말 본문만 출력.

## 검토 기준
1. **시간대 정합성**: 현재 발송 시각은 "{time_label}". {time_rule} 위반이 있으면 해당 문장을 시간대에 맞게 수정.
2. **고유명사 표기**: "오픈아이"→"오픈AI", "오픈에이아이"→"오픈AI", "챗지피티"→"챗GPT", "지피티"→"GPT" 등 한글 음역을 일반 표기로 교정. OpenAI·GPT·Meta·Google 같은 영문 브랜드·약어는 영문 그대로 두기.
3. **AI 클리셰 제거 (필수)**: "마음에 걸리는", "눈에 띄는", "주목된다", "주목할 만", "엿볼 수 있는", "~한 모습입니다", "~는 모습입니다", "낯설지 않다", "사뭇 다르다", "새삼 느끼다", "다시 한번 실감" 같은 표현이 있으면 반드시 다른 구체적 표현으로 교체.
4. **어색한 한국어**: 번역체, 일본어·중국어식 표현, 외국어 음차가 있으면 자연스러운 한국어로 교정.
5. **허위 날짜·주차 (필수)**: "첫째 주", "둘째 주", "셋째 주", "N주차" 등 월 기준 주차 표현이 있으면 근거 없이 지어낸 정보이므로 삭제하거나 "이번 주" 등 상대 표현으로 교체. 요일은 그대로 유지. ("이번 주", "한 주", "주말"은 허용.)
6. **허위 신규성 (필수)**: 빌더조쉬·까탈로그·헤이팝·풋풋레터·캐릿·롱블랙 등 코너를 "오늘부터", "새로 시작", "처음", "첫 회차", "이제부터 함께" 식으로 신규 도입처럼 단정한 표현이 있으면 근거 없는 사실 오류이므로 삭제하거나 "오늘의 ○○ 소식" 같은 중립 표현으로 교체.
7. **문체 유지**: 원문의 전체 구조(3문단, 따뜻한 존댓말, 마지막 이모지)는 유지.{extra}

원문:
---
{original}
---

수정본 (설명 없이 인사말 본문만):"""



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
                "max_tokens": 2000,
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
                "generationConfig": {"maxOutputTokens": 2000},
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
                "max_tokens": 2000,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
    r.raise_for_status()
    return r.json()["content"][0]["text"].strip()


def _call_with_fallback(
    prompt: str,
    api_key: str,
    model: str,
    groq_api_key: str,
    groq_model: str,
    gemini_api_key: str,
    gemini_model: str,
) -> Tuple[Optional[str], str]:
    """Claude → Groq → Gemini 순 폴백. (텍스트, 사용 모델명) 반환. 실패 시 (None, '')."""
    if api_key:
        try:
            return _call_claude(api_key, model, prompt), "Claude"
        except Exception as e:
            print(f"  [WARN] Claude 호출 실패: {e}")
    if groq_api_key:
        try:
            return _call_groq(groq_api_key, groq_model, prompt), "Groq"
        except Exception as e:
            print(f"  [WARN] Groq 호출 실패: {e}")
    if gemini_api_key:
        try:
            return _call_gemini(gemini_api_key, gemini_model, prompt), "Gemini"
        except Exception as e:
            print(f"  [WARN] Gemini 호출 실패: {e}")
    return None, ""


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
    """오늘의 뉴스 기반 인사말 생성.

    파이프라인:
      1) 1차 생성 (Claude 우선, Groq·Gemini 폴백) — 최근 인사말 회피 컨텍스트 포함
      2) 고유명사 표기 정규화 (오픈아이→오픈AI 등)
      3) 셀프 비평 패스 — 시간대·표기·클리셰 교정
      4) 금지 표현 잔류 시 1회 추가 재교정
    """
    recent_greetings = _load_recent_greetings(n=4)
    prompt = _build_greeting_prompt(
        iboss_items=iboss_items,
        weekday_name=weekday_name,
        weekday_msg=weekday_msg,
        longblack_item=longblack_item,
        stibee_items=stibee_items,
        heypop_items=heypop_items,
        recent_greetings=recent_greetings,
    )

    # 1) 1차 생성
    initial, used = _call_with_fallback(
        prompt, api_key, model, groq_api_key, groq_model, gemini_api_key, gemini_model
    )
    if initial is None:
        return f"안녕하세요! {weekday_name} 마케팅 소식 전해드립니다 😊 {weekday_msg}"
    print(f"  [OK] {used}로 인사말 1차 생성 완료")

    # 2) 고유명사 표기 정규화
    text = _normalize_proper_nouns(initial)

    # 3) 셀프 비평 패스
    today = now_kst()
    time_label, time_rule = _time_of_day_hint(today.hour)
    critique_prompt = _build_critique_prompt(text, time_label, time_rule)
    critiqued, critic_used = _call_with_fallback(
        critique_prompt, api_key, model, groq_api_key, groq_model, gemini_api_key, gemini_model
    )
    if critiqued:
        text = _normalize_proper_nouns(critiqued)
        print(f"  [OK] 셀프 비평 완료 ({critic_used})")
    else:
        print("  [WARN] 셀프 비평 건너뜀 (API 호출 실패)")

    # 4) 금지 표현 / 허위 주차 표현 잔류 시 추가 재교정
    banned = _find_banned_phrases(text)
    week = _find_week_of_month(text)
    if banned or week:
        detected = ", ".join(p for p in (
            f"금지 표현 {banned}" if banned else "",
            f"주차 표현 {week}" if week else "",
        ) if p)
        print(f"  [INFO] {detected} 감지 → 재교정 시도")
        retry_prompt = _build_critique_prompt(
            text, time_label, time_rule,
            banned_found=banned or None,
            week_found=week or None,
        )
        retried, _ = _call_with_fallback(
            retry_prompt, api_key, model, groq_api_key, groq_model, gemini_api_key, gemini_model
        )
        if retried:
            text = _normalize_proper_nouns(retried)
            still = _find_banned_phrases(text) + _find_week_of_month(text)
            if still:
                print(f"  [WARN] 잔류 표현: {still}")
            else:
                print("  [OK] 금지·주차 표현 제거 완료")

    return text


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
    today = now_kst()
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
        if "빌더조쉬" in item.source:
            lines.append(f"📌 {item.title}")
            if item.topic:
                lines.append(item.topic)
            lines.append("")
            for idx, s in enumerate(item.summary_items, 1):
                lines.append(f"{idx}. {s}")
            if item.summary_items:
                lines.append("")
            lines.append(item.url)
            lines.append("")
        elif "풋풋" in item.source:
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
