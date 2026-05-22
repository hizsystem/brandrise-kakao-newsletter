# 빌더조쉬 뉴스레터 추가 — 구현 계획

> **⚠️ 2026-05-22 업데이트**: 본 구현 계획의 Task 2(config.yaml — wednesday/friday 두 슬롯)와 Task 4(main.py — 수요일·금요일 분기 분리)는 **단일 슬롯 `builder_josh`** 구조로 통합되었습니다. **현재 코드의 실제 상태는 문서 하단 [Addendum (2026-05-22)](#addendum-2026-05-22--수금-단일-슬롯-통합) 참조**. 이 plan은 5/20 시점의 1차 구현 기록으로 남깁니다.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 데일리 뉴스레터 시스템에 빌더조쉬(maily.so/josh) 콘텐츠를 수요일·금요일에 자동 발송 — 제목·부제·LLM 자동 3줄 요약·URL 포맷.

**Architecture:** 신규 `collectors/builder_josh.py`가 maily.so HTML을 스크래핑(og 메타 + `<article>` 본문)하고 Claude API로 3줄 요약 생성 → 기존 `StibeeNewsletter` dataclass로 반환 → `main.py`가 요일별로 fetch하여 `stibee_items` 리스트 앞에 insert → `formatter.py`의 새 "빌더조쉬" 분기로 텍스트 포맷팅 → `html_formatter_v2.py`의 기존 stibee 카드가 자동 처리.

**Tech Stack:** Python 3.10+, requests, BeautifulSoup4, httpx (Claude REST 호출), PyYAML, 기존 newsletter 시스템.

**참조 설계 문서:** `docs/superpowers/specs/2026-05-20-builder-josh-newsletter-design.md`

---

## 파일 구조

| 파일 | 역할 | 동작 |
|------|------|------|
| `collectors/builder_josh.py` | maily.so 글 스크래퍼 + LLM 요약 | 신규 |
| `config.yaml` | 수요일/금요일 뉴스레터 설정 | 수정 |
| `formatter.py` | 카톡 텍스트 포맷팅의 빌더조쉬 분기 | 수정 |
| `main.py` | 요일별 수집기 호출 | 수정 (수요일 신규 + 금요일 확장) |
| `CLAUDE.md` | 프로젝트 문서 | 수정 |

이 프로젝트는 pytest 등 자동 테스트 인프라가 없다. 모든 검증은 (a) collector의 `__main__` 블록 단독 실행, (b) `python main.py --preview` 통합 미리보기로 수행한다.

---

## Task 1: `collectors/builder_josh.py` 신규 작성

**Files:**
- Create: `collectors/builder_josh.py`

- [ ] **Step 1: 파일 생성 — 메타·본문 추출 + LLM 요약 통합 구현**

```python
"""
빌더조쉬(maily.so/josh) 뉴스레터 파서
og 메타 + 본문 추출 → Claude API로 3줄 요약 자동 생성
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

BODY_CHAR_CAP = 8000  # LLM 입력 길이 제한 (긴 인터뷰 글 대응)


def fetch(
    url: str,
    api_key: str,
    model: str = "claude-sonnet-4-6",
    source_name: str = "빌더조쉬",
) -> Optional[StibeeNewsletter]:
    """maily.so 글 URL → StibeeNewsletter (3줄 요약 포함). 실패 시 None."""
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
        print(f"  [WARN] 빌더조쉬 파싱 결과 부족 (title={bool(title)}, body_len={len(body) if body else 0})")
        return None

    summary_items = _summarize(body[:BODY_CHAR_CAP], api_key, model)

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
    tag = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
    return (tag.get("content") if tag else "") or ""


def _summarize(body: str, api_key: str, model: str) -> list[str]:
    """Claude로 3줄 요약 생성. 실패 시 빈 리스트."""
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

    try:
        with httpx.Client(timeout=60) as client:
            r = client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 800,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
        r.raise_for_status()
        text = r.json()["content"][0]["text"].strip()
    except Exception as e:
        print(f"  [WARN] 빌더조쉬 요약 생성 실패: {e}")
        return []

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
    item = fetch(
        test_url,
        api_key=cfg["anthropic"]["api_key"],
        model=cfg["anthropic"].get("model", "claude-sonnet-4-6"),
    )
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
```

- [ ] **Step 2: 단독 실행으로 fetch 정상 동작 확인**

PowerShell에서:
```powershell
python -m collectors.builder_josh
```

Expected:
- `source: 빌더조쉬`
- `title: 고객 한 명당 월 5,000달러를 받는 1인 AI 에이전트 사업가`
- `topic:` 에 `"AI 에이전트가 아니라 'AI 직원'을 파세요"` 비슷한 부제
- `summary_items:` 3줄 출력 (각 줄 한 문장, 60~90자, 핵심 키워드 포함)
- 빈 리스트가 나오면 LLM 호출 실패 — `[WARN]` 로그 확인 (API 키, 모델명, 네트워크)

만약 본문이 비어서 `파싱 결과 부족` 경고가 나오면 maily.so HTML 구조가 바뀐 것. `_parse` 함수의 셀렉터(`article` → `main`)를 조정 후 재시도.

- [ ] **Step 3: 커밋**

```powershell
git add "collectors/builder_josh.py"
git commit -m @'
feat: 빌더조쉬(maily.so) 뉴스레터 collector 추가

- og:title, og:description, <article> 본문 추출
- Claude API로 3줄 요약 자동 생성 (BODY_CHAR_CAP=8000)
- 기존 StibeeNewsletter 재사용으로 formatter/HTML v2 호환
'@
```

---

## Task 2: `config.yaml` — 수요일/금요일 빌더조쉬 설정 추가

**Files:**
- Modify: `config.yaml`

- [ ] **Step 1: `wednesday_newsletters` 키 신규 추가 + `friday_newsletters`에 builder_josh 항목 추가**

기존 `tuesday_newsletters` 블록 **위**에 `wednesday_newsletters`를 두지 말고, `friday_newsletters` 블록 **바로 위**에 추가한다. 그리고 `friday_newsletters` 안의 `catalogue` 항목 **위**에 `builder_josh`를 명시한다 (dict 순서 보존을 위해).

`config.yaml` 변경 후 모습 (해당 블록만):
```yaml
wednesday_newsletters:
  builder_josh:
    url: https://maily.so/josh/posts/knrj1pn1rld
    name: 빌더조쉬
friday_newsletters:
  builder_josh:
    url: ""
    name: 빌더조쉬
  catalogue:
    url: https://event.stibee.com/v2/click/NjYyMTAvMzM4OTcxOC8xODYzNjQv/aHR0cHM6Ly9zdGliLmVlL3RtZE4
    name: 까탈로그
    sender_keyword: 까탈로그
```

> `catalogue` 의 기존 URL 값은 **수정 전 파일에 적힌 값을 그대로 유지**할 것 (위 값은 2026-05-20 기준 예시).

- [ ] **Step 2: YAML 문법 검증**

```powershell
python -c "import yaml; print(yaml.safe_load(open('config.yaml', encoding='utf-8')).get('wednesday_newsletters')); print(list((yaml.safe_load(open('config.yaml', encoding='utf-8')).get('friday_newsletters') or {}).keys()))"
```

Expected:
- 첫 줄: `{'builder_josh': {'url': 'https://maily.so/josh/posts/knrj1pn1rld', 'name': '빌더조쉬'}}`
- 두 번째 줄: `['builder_josh', 'catalogue']` (builder_josh가 첫 번째)

- [ ] **Step 3: 커밋**

```powershell
git add config.yaml
git commit -m @'
config: 수요일/금요일 빌더조쉬 뉴스레터 항목 추가

- wednesday_newsletters 신규 (매주 수동 URL 업데이트)
- friday_newsletters에 builder_josh를 catalogue 위에 추가
'@
```

---

## Task 3: `formatter.py` — 빌더조쉬 텍스트 분기 추가

**Files:**
- Modify: `formatter.py` (스티비 루프 내부, 현재 line 588 부근)

- [ ] **Step 1: 스티비 루프 내부에 빌더조쉬 분기 추가 (풋풋 분기 위)**

수정 대상 코드 (현재 상태):
```python
    # 스티비 뉴스레터 (풋풋레터, 캐릿 등) - 롱블랙보다 앞
    for item in (stibee_items or []):
        if "풋풋" in item.source:
            lines.append("📌 바쁜 현대인을 위한 마케팅·트렌드 뉴스 [풋풋레터]")
```

변경 후:
```python
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
```

> 변경 포인트: 첫 번째 `if`가 `"빌더조쉬"` 분기가 되고, 기존 `"풋풋"` 분기는 `elif`로 강등. 이후 분기(`"캐릿"`, `"까탈"`, `else`)는 그대로 유지.

- [ ] **Step 2: import 후 함수 시그니처 확인 (변경 없음)**

`build_message_windows_date` 시그니처에 이미 `stibee_items: list = None` 이 있으므로 별도 변경 불필요. 빌더조쉬는 `StibeeNewsletter` 객체로 들어와 자동 처리된다.

- [ ] **Step 3: 분기 동작 단위 검증 (가짜 객체로 호출)**

PowerShell에서:
```powershell
python -c "
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from collectors.stibee import StibeeNewsletter
from formatter import build_message_windows_date
fake = StibeeNewsletter(source='빌더조쉬', issue='', title='테스트 제목', topic='테스트 부제', summary_items=['요약1','요약2','요약3'], url='https://maily.so/josh/posts/test')
msg = build_message_windows_date(iboss_items=[], neusral_categories=[], email_newsletters={}, heypop_items=[], stibee_items=[fake], api_key='', greeting='(인사말)')
print(msg)
"
```

Expected: 출력에 다음 블록 포함
```
📌 테스트 제목
테스트 부제

1. 요약1
2. 요약2
3. 요약3

https://maily.so/josh/posts/test
```

- [ ] **Step 4: 커밋**

```powershell
git add formatter.py
git commit -m @'
feat: formatter에 빌더조쉬 텍스트 분기 추가

- 스티비 루프 최상단에 "빌더조쉬" 분기 (풋풋/캐릿/까탈 위)
- 제목 + 부제(topic) + 1~3 요약 + URL 포맷
'@
```

---

## Task 4: `main.py` — 수요일 분기 신규 + 금요일 분기 확장

**Files:**
- Modify: `main.py` (line 24 import, line 185~220 부근)

- [ ] **Step 1: import 추가**

기존 line 24-27:
```python
from collectors import iboss, neusral, heypop
from collectors import longblack as longblack_collector
from collectors import stibee as stibee_collector
from collectors.email_reader import MailplugReader
```

변경 후 (한 줄 추가):
```python
from collectors import iboss, neusral, heypop
from collectors import longblack as longblack_collector
from collectors import stibee as stibee_collector
from collectors import builder_josh as builder_josh_collector
from collectors.email_reader import MailplugReader
```

- [ ] **Step 2: 수요일 분기 신규 추가 (화요일 블록 직후, 금요일 블록 직전)**

기존 line 184-186 (화요일 블록 종료 후 빈 줄, 그 다음 금요일 주석 시작):
```python
                except Exception as e:
                    print(f"  [WARN] {name} 수집 실패: {e}")

    # 금요일 뉴스레터 (까탈로그) - Gmail 자동 → 수동 URL 순서
    if weekday == 4:
```

변경 후 — 두 블록 사이에 수요일 분기 삽입:
```python
                except Exception as e:
                    print(f"  [WARN] {name} 수집 실패: {e}")

    # 수요일 뉴스레터 (빌더조쉬) - config 수동 URL
    if weekday == 2:
        wed_cfg = config.get("wednesday_newsletters", {})
        for key, cfg in wed_cfg.items():
            url = cfg.get("url", "")
            name = cfg.get("name", key)
            if not url:
                continue
            if key == "builder_josh":
                try:
                    print(f"  → {name} 수집 중...")
                    item = builder_josh_collector.fetch(
                        url,
                        api_key=config["anthropic"]["api_key"],
                        model=config["anthropic"].get("model", "claude-sonnet-4-6"),
                    )
                    if item:
                        stibee_items.insert(0, item)
                        print(f"     {item.title[:40]}")
                except Exception as e:
                    print(f"  [WARN] {name} 수집 실패: {e}")

    # 금요일 뉴스레터 (까탈로그) - Gmail 자동 → 수동 URL 순서
    if weekday == 4:
```

- [ ] **Step 3: 금요일 블록 — 까탈로그 루프 안에 빌더조쉬 분기 추가**

기존 line 187-220 금요일 블록은 stibee 도메인 검사로 까탈로그를 처리한다. 빌더조쉬 항목은 URL이 `maily.so`라 기존 `if url and "stibee.com" in url:` 분기에 걸리지 않으므로 별도 분기를 같은 루프 안에 추가한다.

기존 코드:
```python
    # 금요일 뉴스레터 (까탈로그) - Gmail 자동 → 수동 URL 순서
    if weekday == 4:
        email_cfg = config.get("email", {})
        friday_cfg = config.get("friday_newsletters", {})
        for key, cfg in friday_cfg.items():
            name = cfg.get("name", key)
            keyword = cfg.get("sender_keyword", name)
            url = ""

            # 1순위: Gmail에서 스티비 URL 자동 추출
            if email_cfg.get("username"):
                try:
                    reader = MailplugReader(
                        email_cfg["imap_host"], email_cfg["imap_port"],
                        email_cfg["username"], email_cfg["password"],
                    )
                    url = reader.fetch_stibee_url(keyword) or ""
                    reader.disconnect()
                    if url:
                        print(f"  → {name} URL 이메일 자동 추출")
                except Exception:
                    pass

            # 2순위: config에 저장된 수동 URL
            if not url:
                url = cfg.get("url", "")

            if url and "stibee.com" in url:
                try:
                    print(f"  → {name} 수집 중...")
                    item = stibee_collector.fetch(url, source_name=name)
                    if item:
                        stibee_items.append(item)
                        print(f"     {item.title[:40]}")
                except Exception as e:
                    print(f"  [WARN] {name} 수집 실패: {e}")
```

변경 후 — 루프 본문 최상단에서 builder_josh 항목을 먼저 처리하고 continue:
```python
    # 금요일 뉴스레터 (까탈로그 + 빌더조쉬)
    if weekday == 4:
        email_cfg = config.get("email", {})
        friday_cfg = config.get("friday_newsletters", {})
        for key, cfg in friday_cfg.items():
            name = cfg.get("name", key)

            # 빌더조쉬: maily.so URL 직접 수집 + LLM 요약
            if key == "builder_josh":
                url = cfg.get("url", "")
                if not url:
                    continue
                try:
                    print(f"  → {name} 수집 중...")
                    item = builder_josh_collector.fetch(
                        url,
                        api_key=config["anthropic"]["api_key"],
                        model=config["anthropic"].get("model", "claude-sonnet-4-6"),
                    )
                    if item:
                        stibee_items.insert(0, item)
                        print(f"     {item.title[:40]}")
                except Exception as e:
                    print(f"  [WARN] {name} 수집 실패: {e}")
                continue

            # 까탈로그 등 스티비 계열: Gmail 자동 → 수동 URL
            keyword = cfg.get("sender_keyword", name)
            url = ""

            if email_cfg.get("username"):
                try:
                    reader = MailplugReader(
                        email_cfg["imap_host"], email_cfg["imap_port"],
                        email_cfg["username"], email_cfg["password"],
                    )
                    url = reader.fetch_stibee_url(keyword) or ""
                    reader.disconnect()
                    if url:
                        print(f"  → {name} URL 이메일 자동 추출")
                except Exception:
                    pass

            if not url:
                url = cfg.get("url", "")

            if url and "stibee.com" in url:
                try:
                    print(f"  → {name} 수집 중...")
                    item = stibee_collector.fetch(url, source_name=name)
                    if item:
                        stibee_items.append(item)
                        print(f"     {item.title[:40]}")
                except Exception as e:
                    print(f"  [WARN] {name} 수집 실패: {e}")
```

> 핵심: 빌더조쉬는 `stibee_items.insert(0, item)` → 출력 순서가 빌더조쉬 → 까탈로그 → (롱블랙 별도)로 자동 정렬. 까탈로그는 기존대로 `append`.

- [ ] **Step 4: 문법 확인**

```powershell
python -c "import ast; ast.parse(open('main.py', encoding='utf-8').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 5: 커밋**

```powershell
git add main.py
git commit -m @'
feat: main에 수요일·금요일 빌더조쉬 수집 분기 추가

- 수요일(weekday=2) 신규: wednesday_newsletters 순회 → builder_josh 처리
- 금요일(weekday=4) 확장: friday_newsletters 루프에 builder_josh 분기 추가
- 둘 다 stibee_items.insert(0, item)로 출력 순서 최상단 보장
'@
```

---

## Task 5: 통합 미리보기로 빌더조쉬 블록 포함 확인

**Files:** 없음 (실행만)

이 프로젝트의 `main.py`는 `datetime.now().weekday()`로 요일을 판정하므로, 수요일이나 금요일이 아닌 날에는 미리보기에 빌더조쉬 블록이 나오지 않는다. 임시 패치로 시뮬레이션한다.

- [ ] **Step 1: weekday를 강제로 수요일(2)로 만들고 --preview 실행 — 환경변수 패치**

`main.py`를 수정하지 않고 inline Python으로 datetime을 패치:

```powershell
python -c "
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import datetime as _dt
_orig = _dt.datetime
class _W(_orig):
    @classmethod
    def now(cls, tz=None):
        d = _orig.now(tz)
        # 가장 가까운 수요일로 강제
        return d.replace() - _dt.timedelta(days=(d.weekday() - 2) % 7)
_dt.datetime = _W

import main
cfg = main.load_config()
main.run_newsletter(cfg, preview_only=True)
"
```

Expected:
- 콘솔 로그에 `→ 빌더조쉬 수집 중...` 다음 줄에 글 제목 (40자) 노출
- 미리보기 메시지에 다음 형태 블록 포함 (롱블랙 위, 다른 스티비 위):
```
📌 [실제 빌더조쉬 글 제목]
[부제]

1. [요약]
2. [요약]
3. [요약]

https://maily.so/josh/posts/...
```

발생 가능한 문제:
- `→ 빌더조쉬 수집 중...` 다음에 `[WARN] 빌더조쉬 수집 실패` 가 뜨면 Task 1의 LLM 호출 점검.
- 빌더조쉬 블록 자체가 안 나오면 `weekday == 2` 분기 진입 실패 → Step의 datetime 패치가 안 먹는 것. 차선책: 오늘이 수요일/금요일이면 `python main.py --preview` 직접 실행.

- [ ] **Step 2: 금요일(4) 시뮬레이션 — 빌더조쉬가 까탈로그 위에 노출되는지 확인**

위 Step과 동일하나 `(d.weekday() - 2) % 7` → `(d.weekday() - 4) % 7` 로 변경.

```powershell
python -c "
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import datetime as _dt
_orig = _dt.datetime
class _W(_orig):
    @classmethod
    def now(cls, tz=None):
        d = _orig.now(tz)
        return d.replace() - _dt.timedelta(days=(d.weekday() - 4) % 7)
_dt.datetime = _W

import main
cfg = main.load_config()
main.run_newsletter(cfg, preview_only=True)
"
```

> 금요일은 `friday_newsletters.builder_josh.url`이 빈 문자열이라 기본 상태에서는 빌더조쉬 블록이 누락된다. 임시로 `config.yaml`의 friday builder_josh `url`을 수요일과 동일한 테스트 URL로 채워 실행 후, 검증 끝나면 다시 `""`로 되돌린다.

Expected:
- 금요일 블록에 빌더조쉬 블록이 까탈로그 블록보다 **위**에 노출
- 까탈로그 블록은 그대로 유지
- 롱블랙은 그 아래 유지

- [ ] **Step 3: (Step 2에서 임시 변경했다면) config.yaml friday builder_josh url 원복**

```powershell
python -c "
import yaml
with open('config.yaml', encoding='utf-8') as f:
    cfg = yaml.safe_load(f)
print('current friday builder_josh url:', repr(cfg['friday_newsletters']['builder_josh']['url']))
"
```

값이 테스트용 URL이면 직접 편집해 `url: \"\"` 로 되돌린다.

- [ ] **Step 4: 검증 통과면 다음 Task로. 커밋은 변경사항 없으면 생략.**

---

## Task 6: `CLAUDE.md` 프로젝트 문서 업데이트

**Files:**
- Modify: `0. 데일리 뉴스레터/CLAUDE.md`

- [ ] **Step 1: "요일별 수집 소스" 섹션 갱신**

기존 (라인 18-21 부근):
```markdown
### 요일별 수집 소스
- **매일**: 아이보스(iboss), 뉴스럴(neusral), 롱블랙(longblack)
- **화요일(weekday=1)**: 풋풋레터, 캐릿 (stibee 공유 URL → `config.yaml`의 `tuesday_newsletters`에 매주 수동 업데이트 필요)
- **목요일(weekday=3)**: 헤이팝(heypop)
```

변경 후:
```markdown
### 요일별 수집 소스
- **매일**: 아이보스(iboss), 뉴스럴(neusral), 롱블랙(longblack)
- **화요일(weekday=1)**: 풋풋레터, 캐릿 (stibee 공유 URL → `config.yaml`의 `tuesday_newsletters`에 매주 수동 업데이트 필요)
- **수요일(weekday=2)**: 빌더조쉬(builder_josh, maily.so/josh — `wednesday_newsletters`에 매주 수동 업데이트 필요)
- **목요일(weekday=3)**: 헤이팝(heypop)
- **금요일(weekday=4)**: 빌더조쉬, 까탈로그 (`friday_newsletters` 두 항목 모두 수동/자동 URL 가능)
```

- [ ] **Step 2: "각 수집기 특성" 표에 빌더조쉬 행 추가**

기존 표 마지막 행(email_reader) 위 또는 아래에 추가:
```markdown
| `builder_josh.py` | `StibeeNewsletter` | maily.so/josh 글 (og 메타 + Claude 3줄 요약) |
```

- [ ] **Step 3: "포맷 구조 (출력 순서)" 갱신**

기존:
```markdown
5. 스티비 뉴스레터 (화요일만): 풋풋레터, 캐릿
6. 롱블랙 `📌 제목`
```

변경 후:
```markdown
5. 스티비 뉴스레터 (요일별): 빌더조쉬(수/금) → 풋풋레터·캐릿(화) → 까탈로그(금) 순으로 stibee_items 리스트 처리
6. 롱블랙 `📌 제목`
```

- [ ] **Step 4: "config.yaml 주요 설정" 갱신**

기존:
```markdown
- `tuesday_newsletters`: 화요일마다 풋풋레터·캐릿의 스티비 공유 URL을 **매주 수동 업데이트** 필요
```

아래에 두 줄 추가:
```markdown
- `wednesday_newsletters`: 수요일 빌더조쉬 maily.so 글 URL을 **매주 수동 업데이트** 필요
- `friday_newsletters.builder_josh.url`: 금요일 빌더조쉬 URL을 **매주 수동 업데이트** 필요 (까탈로그는 Gmail 자동 추출 우선)
```

- [ ] **Step 5: 커밋**

```powershell
git add "CLAUDE.md"
git commit -m @'
docs: CLAUDE.md에 빌더조쉬 수요일/금요일 추가 반영
'@
```

---

## Task 7: 최종 점검 (run_test + 미리보기)

**Files:** 없음 (실행만)

- [ ] **Step 1: 기존 수집기들이 회귀 없는지 확인**

```powershell
python main.py --test
```

Expected: `✓ 아이보스`, `✓ 뉴스럴`, `✓ 롱블랙`, `✓ 헤이팝` 모두 정상 (빌더조쉬는 `--test` 메뉴에 없으므로 누락이 정상; 별도로 `python -m collectors.builder_josh`).

- [ ] **Step 2: 오늘 요일에 맞는 자연 미리보기**

```powershell
python main.py --preview
```

Expected:
- 에러 없이 완주
- 오늘이 수요일/금요일이면 빌더조쉬 블록 노출
- 오늘이 그 외 요일이면 평소대로 출력 (빌더조쉬 코드가 다른 요일에는 진입하지 않음)

- [ ] **Step 3: 변경 사항 전체 커밋 점검**

```powershell
git status
git log --oneline -10
```

Expected:
- working tree clean (모든 변경 커밋됨)
- 최근 6개 커밋이 위 Task의 메시지와 일치

- [ ] **Step 4: 작업 마무리**

`docs/superpowers/specs/2026-05-20-builder-josh-newsletter-design.md` 와 본 plan 파일도 커밋:

```powershell
git add "docs/superpowers/specs/2026-05-20-builder-josh-newsletter-design.md" "docs/superpowers/plans/2026-05-20-builder-josh-newsletter.md"
git commit -m @'
docs: 빌더조쉬 뉴스레터 추가 설계·구현 계획 문서
'@
```

---

## Self-Review

**1. Spec coverage**

| Spec 항목 | 구현 Task |
|-----------|-----------|
| config.yaml 변경 (wed + fri) | Task 2 |
| collectors/builder_josh.py 신규 | Task 1 |
| formatter.py 빌더조쉬 분기 | Task 3 |
| main.py 수요일·금요일 분기 | Task 4 |
| html_formatter_v2.py 변경 불필요 (자동 처리) | (변경 없음 — `StibeeNewsletter` 재사용으로 자동) |
| html_formatter.py v1 점검 | `v1`은 v2와 동일 `stibee_items` 시그니처 사용. 새 분기는 자동으로 `else` (일반) 처리되어 텍스트 카드로 표시. 별도 분기 불필요. Task 5의 통합 미리보기에서 v1 HTML도 정상 생성됨을 확인. |
| 인사말 컨텍스트 (자동 포함) | 변경 없음 — `_build_greeting_prompt`의 stibee_items 루프가 자동 처리 |
| CLAUDE.md 업데이트 | Task 6 |
| 테스트 계획 (수동 검증) | Task 1 Step 2, Task 3 Step 3, Task 5 전체, Task 7 |

**2. Placeholder scan**

- 모든 코드 블록 완전, 잘림 없음.
- `Task 5 Step 2`의 "테스트 URL"은 Task 2에서 명시한 `https://maily.so/josh/posts/knrj1pn1rld`를 그대로 사용 가능 (별도 URL 불필요).
- "fill in details", "TBD", "implement later" 검색 결과 없음.

**3. Type consistency**

- `fetch(url, api_key, model, source_name)` 시그니처가 Task 1 정의와 Task 4 호출에서 일치.
- `StibeeNewsletter` 필드(source, issue, title, summary_items, url, topic, terms)가 stibee.py 정의와 일치.
- `stibee_items.insert(0, item)` — Task 4 수요일/금요일 두 곳에서 동일 메서드 사용.
- formatter 분기 식별자 `"빌더조쉬" in item.source` — Task 1의 `source_name="빌더조쉬"` 기본값과 일치.

---

## Addendum (2026-05-22) — 수/금 단일 슬롯 통합

5/20 구현 직후 운영 검토에서 "수요일·금요일 URL을 미리 받을 수 없다 → 슬롯을 분리해도 작업량 동일" 결론이 나와 다음과 같이 단순화됨.

### Task 2 (config.yaml) — 실제 적용된 최종 구조

```yaml
# 빌더조쉬 (수/금 공용 단일 슬롯) — 각 발송 직전 URL을 수동으로 덮어쓰기
builder_josh:
  url: https://maily.so/josh/posts/WEEKLY_SLUG
  name: 빌더조쉬
friday_newsletters:
  catalogue:              # 금요일에는 까탈로그만 남음
    url: ...
    name: 까탈로그
    sender_keyword: 까탈로그
```

- `wednesday_newsletters` 키 자체 제거.
- `friday_newsletters.builder_josh` 제거.
- top-level `builder_josh` 신설.
- `config.example.yaml`도 동일 구조로 동기화.

### Task 4 (main.py) — 실제 적용된 최종 분기

```python
# 수/금 빌더조쉬 - 단일 config 슬롯 (수/금 발송 직전 URL 수동 갱신)
if weekday in (2, 4):
    bj_cfg = config.get("builder_josh", {})
    url = bj_cfg.get("url", "")
    name = bj_cfg.get("name", "빌더조쉬")
    if url:
        try:
            print(f"  → {name} 수집 중...")
            item = builder_josh_collector.fetch(url, config=config)
            if item:
                stibee_items.insert(0, item)
                print(f"     {item.title[:40]}")
        except Exception as e:
            print(f"  [WARN] {name} 수집 실패: {e}")

# 금요일 뉴스레터 (까탈로그) - Gmail 자동 → 수동 URL
if weekday == 4:
    email_cfg = config.get("email", {})
    friday_cfg = config.get("friday_newsletters", {})
    for key, cfg in friday_cfg.items():
        # ... 까탈로그만 처리 (Gmail 자동 → 수동 폴백)
```

- 수요일 블록(`if weekday == 2`)과 금요일의 빌더조쉬 분기 모두 제거 → 위 단일 `if weekday in (2, 4)` 블록으로 통합.
- 금요일 까탈로그 처리 블록은 그대로 유지 (Gmail 자동 추출 → 수동 URL 폴백).

### 변하지 않은 Task

- Task 1 (`collectors/builder_josh.py`) — 그대로 유효.
- Task 3 (`formatter.py` 빌더조쉬 텍스트 분기) — 그대로 유효.
- Task 5 (통합 미리보기 검증) — 그대로 유효하나, `weekday == 2` / `weekday == 4` 양쪽 모두 동일 단일 슬롯을 보게 됨.
- Task 6 (`CLAUDE.md` 프로젝트 문서) — 통합 구조로 재갱신.
- Task 7 (최종 점검) — 그대로 유효.

### 새로 추가된 기능 (2026-05-22 동일 세션)

`formatter.py`에 **첫 등장 stibee 소스 자동 감지** 로직 추가:

- `_first_appearance_sources(stibee_items)` 헬퍼: 과거 `output_*.txt`를 스캔해 한 번도 등장한 적 없는 source 이름 목록 반환.
- `_build_greeting_prompt`의 `notes` 배열에 "오늘부터 [소스명] 코너가 처음 추가됩니다" 노트 자동 주입 → LLM이 광고 톤이 아니라 본문 흐름에 자연스럽게 녹임.
- 동작 확인: 2026-05-22 발송분 인사말에 빌더조쉬 닉 바실레스쿠 이야기를 중심 소재로 활용한 자연 소개 한 문장 성공.

### 운영 영향

- 작업량 동일 (주 2회 갱신).
- 갱신 대상이 단일 키 `builder_josh.url`로 단순화.
- 신규 stibee 소스 추가 시 첫 발송 자동 안내가 영구 동작.
