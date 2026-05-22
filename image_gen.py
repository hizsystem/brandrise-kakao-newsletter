"""
뉴스 썸네일 이미지 생성 (Gemini 우선, Pollinations.ai 폴백) + OG 이미지 스크래핑
Claude Sonnet으로 뉴스 본문 기반 맞춤 프롬프트 생성, 월클락 예산 기반 순차 생성
"""
from pathlib import Path
from urllib.parse import quote
import json
import threading
import time
import requests


def _run_with_deadline(fn, timeout: float, label: str = ""):
    """fn()을 daemon 스레드에서 실행하고 timeout 안에 끝나면 결과 반환, 아니면 None.
    SDK 자체 timeout이 신뢰가 안 되는 환경(오늘 LLM API 행 등)에서 메인 스레드를
    무한 대기시키지 않기 위한 안전장치. daemon 스레드는 main이 끝나면 함께 종료.
    """
    box = {"result": None, "exc": None}

    def _runner():
        try:
            box["result"] = fn()
        except BaseException as e:
            box["exc"] = e

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    t.join(timeout=timeout)
    if t.is_alive():
        if label:
            print(f"  [WARN] {label} 시간 초과 ({timeout:.0f}s) — 진행 계속")
        return None
    if box["exc"] is not None:
        raise box["exc"]
    return box["result"]
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

STYLE_PREFIX = "Editorial illustration with soft pastel palette centered on pink (#FFB5C8) and mint (#B8E8D0): "

STYLE_SUFFIX = (
    ". Rounded forms, friendly and modern feel, warm lighting, gentle shadows. "
    "Keep pink/mint as dominant hues but allow small accent colors when the subject demands. "
    "No people, no faces, no text, no letters, no logos, no dark moody tones, no photorealism."
)

MAX_WORKERS = 4


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _date_seed(date_iso: str) -> int:
    digits = "".join(ch for ch in date_iso if ch.isdigit())
    return int(digits) if digits else 42


# ── Claude로 맞춤 프롬프트 생성 ───────────────────────────────────────────────

def generate_prompts_batch(
    articles: list,
    anthropic_api_key: str,
) -> list:
    """
    Claude로 한국어 뉴스 기사들에 대한 이미지 프롬프트 일괄 생성.
    articles: [(title, context)] 튜플 리스트.
    Returns: prompt 문자열 리스트 (articles와 동일한 순서)
    """
    titles = [a[0] if isinstance(a, tuple) else a for a in articles]
    contexts = [a[1] if isinstance(a, tuple) and len(a) > 1 else "" for a in articles]

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=anthropic_api_key, timeout=45.0, max_retries=0)

        blocks = []
        for i, (t, c) in enumerate(zip(titles, contexts), 1):
            ctx = (c or "").strip().replace("\n", " ")
            if len(ctx) > 220:
                ctx = ctx[:220] + "…"
            blocks.append(f"{i}. 제목: {t}\n   본문: {ctx}" if ctx else f"{i}. 제목: {t}")
        numbered = "\n".join(blocks)

        _prompt = (
            "다음 한국어 뉴스 각각에 대해 이미지 생성용 영어 프롬프트를 만들어주세요.\n"
            "**제목만 보지 말고 본문에서 가장 구체적이고 시각적인 디테일(브랜드, 제품, 숫자, 장소, 행동, 등장하는 사물)을 뽑아내 장면으로 옮기세요.**\n\n"
            "프롬프트 구성 규칙:\n"
            "- 기사에만 등장하는 고유한 사물 3-4개를 조합해 '한 장면(scene)'을 묘사 (단순 아이콘 나열 금지)\n"
            "- 매 기사마다 **구도(앵글)**를 달리 하세요: 탑다운, 등각투영, 정면, 약간 위에서 내려다보기, 옆에서 바라보기 등\n"
            "- 매 기사마다 **질감 변주**를 주세요: 부드러운 클레이, 종이접기(paper-craft), 플랫 일러스트, 수채화, 미니어처 모형 등\n"
            "- 사물 사이의 관계/배치를 명시 (위에, 옆에, 안에서 나오는, 연결된, 둘러싼 등)\n"
            "- 같은 주제라도 본문이 다르면 사물 조합과 구도가 모두 달라야 함\n\n"
            "좋은 예:\n"
            "- '쿠팡, 와우 멤버십 OTT 강화' (본문: 쿠팡플레이 스포츠 중계 확대) →\n"
            "  'top-down view of a mint TV screen showing a tiny soccer field, pink delivery box with a golden crown beside it, paper-craft remote control, soft watercolor gradient'\n"
            "- '네이버 치지직 광고 도입' (본문: 스트리밍 중 배너 광고 삽입 테스트) →\n"
            "  'isometric clay monitor with glowing play triangle, a thin banner ribbon sliding across the screen, stacked coins and a headset on a mint shelf beside it'\n"
            "- 'GS25, 라면 특화 매장 오픈' (본문: 100여 종 라면 진열, 즉석 조리대) →\n"
            "  'front-view miniature convenience store with shelves of colorful ramen cups, a steaming pink bowl on a counter, chopsticks and a kettle floating in warm light'\n\n"
            "나쁜 예 (절대 이렇게 만들지 말 것):\n"
            "- 'social media engagement icons on gradient' (너무 일반적, 어느 기사든 적용 가능)\n"
            "- 'shopping cart and coins floating' (브랜드/맥락 없음)\n"
            "- 모든 기사에 동일한 'isometric clay diorama' 구도 반복 (변화 없음)\n\n"
            "금지: 사람, 얼굴, 텍스트/글자, 로고 그대로 복제, 어두운 색, 사실적 질감, 추상 도형만 사용\n"
            "각 프롬프트는 30~50단어 영어, 위 규칙을 모두 지킬 것.\n\n"
            f"기사 목록:\n{numbered}\n\n"
            "JSON 배열로만 응답 (다른 텍스트 없이):\n"
            '["prompt1", "prompt2", ...]'
        )

        def _call():
            return client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1536,
                timeout=45.0,
                messages=[{"role": "user", "content": _prompt}],
            )

        message = _run_with_deadline(_call, timeout=50.0, label="Claude 프롬프트")
        if message is None:
            return [_build_fallback_prompt(t) for t in titles]

        text = message.content[0].text.strip()
        start, end = text.find("["), text.rfind("]") + 1
        if start >= 0 and end > start:
            prompts = json.loads(text[start:end])
            if len(prompts) == len(titles):
                return [STYLE_PREFIX + p + STYLE_SUFFIX for p in prompts]
    except Exception as e:
        print(f"  [WARN] Claude 프롬프트 생성 실패: {e}")

    return [_build_fallback_prompt(t) for t in titles]


KEYWORD_MAP = {
    "AI": "artificial intelligence neural network concept",
    "인공지능": "artificial intelligence data visualization",
    "스타트업": "startup growth rocket launch business",
    "네이버": "Korean search engine portal interface",
    "카카오": "Korean messaging app mobile platform",
    "유튜브": "video streaming play button content creator",
    "인스타그램": "social media photo grid smartphone",
    "쿠팡": "e-commerce delivery package Korean retail",
    "광고": "digital advertising creative campaign display",
    "마케팅": "marketing strategy brand growth chart",
    "SNS": "social media network engagement icons",
    "커머스": "e-commerce shopping cart online retail",
    "OTT": "streaming service screen content entertainment",
    "메타": "social media advertising platform data",
    "구글": "search engine technology innovation",
    "애플": "premium technology product design minimal",
    "콘텐츠": "digital content creation media production",
    "브랜드": "brand identity logo design visual",
    "소비자": "consumer shopping behavior trend",
    "트렌드": "trend analysis data chart market",
    "MZ": "young generation lifestyle digital culture",
    "패션": "fashion style clothing industry trend",
    "뷰티": "beauty cosmetics skincare product",
    "게임": "gaming controller screen entertainment",
    "핀테크": "fintech digital payment mobile banking",
    "규제": "legal regulation compliance document shield",
    "ESG": "sustainability environment green energy",
    "웹툰": "webtoon comics digital illustration",
    "롱블랙": "premium business magazine article reading",
}


def _build_fallback_prompt(title: str) -> str:
    for kr, en in KEYWORD_MAP.items():
        if kr in title:
            return STYLE_PREFIX + en + STYLE_SUFFIX
    return STYLE_PREFIX + "business news concept abstract geometric shapes" + STYLE_SUFFIX


# ── Gemini 이미지 생성 (우선) ────────────────────────────────────────────────

def _generate_with_gemini(prompt: str, save_path: Path, gemini_api_key: str) -> bool:
    if save_path.exists():
        return True
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(
            api_key=gemini_api_key,
            http_options=types.HttpOptions(timeout=45_000),
        )

        def _call():
            return client.models.generate_content(
                model="gemini-2.5-flash-image",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE", "TEXT"],
                ),
            )

        response = _run_with_deadline(_call, timeout=50.0, label=f"Gemini ({save_path.name})")
        if response is None:
            return False
        for part in response.candidates[0].content.parts:
            if part.inline_data is not None:
                save_path.parent.mkdir(parents=True, exist_ok=True)
                save_path.write_bytes(part.inline_data.data)
                return True
    except Exception as e:
        print(f"  [WARN] Gemini 이미지 생성 실패: {e}")
    return False


# ── Pollinations.ai 이미지 생성 (폴백) ───────────────────────────────────────

def _generate_with_pollinations(prompt: str, save_path: Path, seed: int = 42, max_retries: int = 2) -> bool:
    if save_path.exists():
        return True
    for attempt in range(max_retries):
        try:
            current_seed = seed + attempt * 10
            url = (
                f"https://image.pollinations.ai/prompt/{quote(prompt)}"
                f"?width=1792&height=1024&nologo=true&nofeed=true&seed={current_seed}"
            )
            r = requests.get(url, timeout=60)
            if r.status_code == 200 and len(r.content) > 1000:
                save_path.parent.mkdir(parents=True, exist_ok=True)
                save_path.write_bytes(r.content)
                return True
            print(f"  [WARN] Pollinations 응답 이상 (시도 {attempt+1}/{max_retries}): status={r.status_code}")
            time.sleep(5)
        except Exception as e:
            print(f"  [WARN] Pollinations 폴백 실패 (시도 {attempt+1}/{max_retries}): {e}")
            time.sleep(3)
    return False


# ── 통합 생성 (Gemini 우선 → Pollinations 폴백) ──────────────────────────────

def _generate_image(
    prompt: str,
    save_path: Path,
    gemini_api_key: str,
    seed: int = 42,
) -> bool:
    if save_path.exists():
        return True
    if gemini_api_key and _generate_with_gemini(prompt, save_path, gemini_api_key):
        return True
    return _generate_with_pollinations(prompt, save_path, seed=seed)


# ── 아이보스 이미지 생성 (병렬) ──────────────────────────────────────────────

def generate_iboss_images(
    iboss_items,
    docs_dir: Path,
    date_iso: str,
    anthropic_api_key: str = "",
    gemini_api_key: str = "",
) -> dict:
    """
    아이보스 뉴스 항목별 AI 이미지 생성 (Gemini 병렬, Pollinations 폴백).
    Returns: {1-based index: relative_path_from_docs/v2/}
    """
    images_dir = docs_dir / "v2" / "images" / date_iso
    articles = [(item.title, getattr(item, "summary", "") or "") for item in iboss_items]

    if anthropic_api_key:
        prompts = generate_prompts_batch(articles, anthropic_api_key)
    else:
        prompts = [_build_fallback_prompt(t) for t, _ in articles]

    date_seed = _date_seed(date_iso)
    result = {}
    engine = "Gemini" if gemini_api_key else "Pollinations"
    print(f"     아이보스 {len(iboss_items)}개 이미지 병렬 생성 중 ({engine})...")

    def _task(i: int, item, prompt: str):
        filename = f"iboss-{i}.png"
        save_path = images_dir / filename
        ok = _generate_image(prompt, save_path, gemini_api_key, seed=date_seed + i * 17)
        return i, item, filename, ok

    deadline = time.monotonic() + 240
    for i, (item, prompt) in enumerate(zip(iboss_items, prompts), 1):
        if time.monotonic() >= deadline:
            print(f"     아이보스 [{i}/{len(iboss_items)}] {item.title[:30]} 시간 초과 건너뜀")
            continue
        i_, item_, filename, ok = _task(i, item, prompt)
        if ok:
            result[i_] = f"images/{date_iso}/{filename}"
            print(f"     아이보스 [{i_}/{len(iboss_items)}] {item_.title[:30]} ✓")
        else:
            print(f"     아이보스 [{i_}/{len(iboss_items)}] {item_.title[:30]} ✗")

    return result


# ── 뉴스럴 이미지 생성 (병렬) ────────────────────────────────────────────────

def generate_neusral_images(
    neusral_categories,
    docs_dir: Path,
    date_iso: str,
    anthropic_api_key: str = "",
    gemini_api_key: str = "",
) -> dict:
    """
    뉴스럴 카테고리별 AI 이미지 생성 (Gemini 병렬, Pollinations 폴백).
    Returns: {category_name: relative_path_from_docs/v2/}
    """
    images_dir = docs_dir / "v2" / "images" / date_iso
    articles = []
    for cat in neusral_categories:
        title = f"{cat.category}: {cat.headlines[0]}" if cat.headlines else cat.category
        context = " / ".join(cat.headlines[1:]) if len(cat.headlines) > 1 else ""
        articles.append((title, context))

    if anthropic_api_key:
        prompts = generate_prompts_batch(articles, anthropic_api_key)
    else:
        prompts = [_build_fallback_prompt(t) for t, _ in articles]

    date_seed = _date_seed(date_iso)
    result = {}
    engine = "Gemini" if gemini_api_key else "Pollinations"
    print(f"     뉴스럴 {len(neusral_categories)}개 이미지 병렬 생성 중 ({engine})...")

    def _task(i: int, cat, prompt: str):
        filename = f"neusral-{i}.png"
        save_path = images_dir / filename
        ok = _generate_image(prompt, save_path, gemini_api_key, seed=date_seed + 1000 + i * 23)
        return i, cat, filename, ok

    deadline = time.monotonic() + 240
    for i, (cat, prompt) in enumerate(zip(neusral_categories, prompts)):
        if time.monotonic() >= deadline:
            print(f"     뉴스럴 [{i+1}/{len(neusral_categories)}] {cat.category} 시간 초과 건너뜀")
            continue
        i_, cat_, filename, ok = _task(i, cat, prompt)
        if ok:
            result[cat_.category] = f"images/{date_iso}/{filename}"
            print(f"     뉴스럴 [{i_+1}/{len(neusral_categories)}] {cat_.category} ✓")
        else:
            print(f"     뉴스럴 [{i_+1}/{len(neusral_categories)}] {cat_.category} ✗")

    return result


# ── OG 이미지 스크래핑 ────────────────────────────────────────────────────

def fetch_og_image(url: str, save_path: Path) -> bool:
    if save_path.exists():
        return True
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.encoding = "utf-8"
        soup = BeautifulSoup(r.text, "html.parser")

        og_tag = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "og:image"})
        img_url = (og_tag.get("content", "") or "").strip() if og_tag else ""

        if not img_url:
            for img in soup.find_all("img", src=True):
                src = img.get("src", "")
                if src.startswith("http") and any(ext in src for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                    img_url = src
                    break

        if not img_url:
            return False

        img_data = requests.get(img_url, headers=HEADERS, timeout=30).content
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_bytes(img_data)
        return True
    except Exception as e:
        print(f"  [WARN] OG 이미지 스크래핑 실패 ({url[:40]}...): {e}")
        return False


def fetch_longblack_image(longblack_item, docs_dir: Path, date_iso: str) -> str:
    if not longblack_item or not longblack_item.url:
        return ""
    save_path = docs_dir / "v2" / "images" / date_iso / "longblack.jpg"
    print("     롱블랙 OG 이미지 스크래핑...")
    if fetch_og_image(longblack_item.url, save_path):
        return f"images/{date_iso}/longblack.jpg"
    return ""


def fetch_stibee_images(stibee_items, docs_dir: Path, date_iso: str) -> dict:
    result = {}
    for i, item in enumerate(stibee_items or []):
        if not item.url:
            continue
        filename = f"stibee-{i}.jpg"
        save_path = docs_dir / "v2" / "images" / date_iso / filename
        print(f"     {item.source} OG 이미지 스크래핑...")
        if fetch_og_image(item.url, save_path):
            result[item.source] = f"images/{date_iso}/{filename}"
    return result
