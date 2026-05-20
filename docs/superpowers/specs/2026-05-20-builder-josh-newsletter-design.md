# 빌더조쉬 뉴스레터 추가 — 설계 (2026-05-20)

## 배경

- 데일리 뉴스레터 시스템에 빌더조쉬(조쉬의 뉴스레터 — `maily.so/josh/`) 콘텐츠를 **수요일·금요일** 발송분에 추가한다.
- 빌더조쉬는 인터뷰/에세이 1편 형식의 긴 글이라, 카카오톡 메시지에서는 **제목 + 부제 + 3줄 요약 + URL** 포맷으로 노출한다.
- 요약은 본문 스크래핑 후 Claude API로 자동 생성한다.

## 핵심 결정사항

1. **URL 수집**: 매주 사용자가 `config.yaml`에 수동으로 새 글 URL 붙여넣기 (Gmail IMAP 자동 추출 미사용 — maily.so는 stibee와 도메인 다름).
2. **출력 포맷**: 헤더 라벨 없이 `📌 제목` + `부제(og:description)` + `1. 2. 3. 요약` + `URL`.
3. **금요일 출력 순서**: 빌더조쉬 → 까탈로그 → 롱블랙 (빌더조쉬가 가장 위).
4. **수요일**: 빌더조쉬만 추가 (다른 신규 소스 없음).
5. **데이터 모델**: 신규 dataclass 만들지 않고 기존 `StibeeNewsletter` 재사용 — formatter·HTML v2 카드 분기를 그대로 활용.
6. **이름**: `source="빌더조쉬"` 로 통일 (HTML 카드 배지·formatter 분기 식별자).

## 데이터 흐름

```
config.yaml (수동 URL)
    ↓
collectors/builder_josh.py (신규)
    ├─ requests.get → BeautifulSoup
    ├─ og:title / og:description / og:image 추출
    └─ 본문 텍스트 추출 → Claude API → 3줄 요약 생성
    ↓
StibeeNewsletter(source="빌더조쉬", title=og:title, topic=og:description,
                 summary_items=[3줄], url=원본 URL)
    ↓
main.py: 수요일(weekday=2)·금요일(weekday=4)에 fetch → stibee_items 리스트 앞쪽에 insert
    ↓
formatter.py: "빌더조쉬" 분기로 텍스트 포맷팅
html_formatter_v2.py: 기존 _render_stibee_v2 카드 자동 사용
```

## 변경 파일 목록

### 신규 파일

#### `collectors/builder_josh.py`
- 단일 공개 함수 `fetch(url: str, api_key: str, model: str = "claude-sonnet-4-6") -> Optional[StibeeNewsletter]`
- `StibeeNewsletter` 재사용 (`from collectors.stibee import StibeeNewsletter`)
- 동작:
  1. `requests.get(url, headers=HEADERS, timeout=15)` — HEADERS는 stibee.py와 동일한 Chrome UA
  2. BeautifulSoup으로 og 메타 추출 (`og:title`, `og:description`, `og:image`)
  3. 본문 추출: `<article>` 우선, 없으면 `main` 또는 `div[class*="content"]` 폴백. 텍스트만 추출 후 `\n\n` 단위 정리. 길이 캡 ~8,000자(LLM 입력 비용 절감, 3줄 요약 충분).
  4. anthropic SDK로 Claude 호출 → 3문장 요약 생성. 프롬프트는 "아래 마케팅·비즈니스 인터뷰/에세이 본문을 카카오톡 오픈채팅 독자가 읽고 클릭하고 싶게 만드는 3줄 요약으로 정리. 각 줄 한 문장, 60~90자, 핵심 인사이트·숫자·고유명사 보존, 반복 금지." 형태.
  5. 응답 파싱: 줄바꿈 분리 → 번호·기호(`1.`, `-`, `•`) 제거 → 비어 있지 않은 3줄만 채택. 3줄 미만이면 가능한 만큼만.
  6. 반환: `StibeeNewsletter(source="빌더조쉬", issue="", title=og:title, topic=og:description, summary_items=[...], url=url)` — `image_url`은 v2 이미지 스크래퍼가 og:image를 자동으로 다시 찾으므로 별도 저장 불필요.
- 예외 처리: 네트워크/파싱 실패 시 `print("  [WARN] 빌더조쉬 수집 실패: ...")` 후 `None` 반환 (다른 collector 패턴과 동일).
- `if __name__ == "__main__"` 블록: 단독 테스트용으로 `https://maily.so/josh/posts/knrj1pn1rld` 호출 + 결과 출력.

### 수정 파일

#### `config.yaml`
```yaml
wednesday_newsletters:
  builder_josh:
    url: https://maily.so/josh/posts/knrj1pn1rld   # 매주 수동 업데이트
    name: 빌더조쉬

friday_newsletters:
  builder_josh:
    url: ""                                          # 매주 수동 업데이트
    name: 빌더조쉬
  catalogue:
    url: https://event.stibee.com/...               # 기존 값 유지
    name: 까탈로그
    sender_keyword: 까탈로그
```

> `friday_newsletters`는 dict 순서가 유지되도록 builder_josh를 catalogue 위에 명시 (Python 3.7+ dict는 삽입 순서 보존).

#### `main.py`
- 상단 import: `from collectors import builder_josh`
- 수요일 분기 신규 추가 (`weekday == 2`):
  ```python
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
                  item = builder_josh.fetch(url, api_key=config["anthropic"]["api_key"],
                                            model=config["anthropic"].get("model", "claude-sonnet-4-6"))
                  if item:
                      stibee_items.insert(0, item)
                      print(f"     {item.title[:40]}")
              except Exception as e:
                  print(f"  [WARN] {name} 수집 실패: {e}")
  ```
- 금요일 분기 수정: 기존 까탈로그 처리 직후, 동일 패턴으로 builder_josh fetch → `stibee_items.insert(0, item)` 호출 (까탈로그보다 앞).
  - 분기는 `key == "builder_josh"` 인지로 갈라 builder_josh.fetch 호출.
  - 기존 stibee 처리(`"stibee.com" in url`)는 builder_josh에 적용되지 않으므로 자연스럽게 분리됨.

#### `formatter.py`
스티비 루프 (현재 line 588-621) 내부에 빌더조쉬 분기 추가. **풋풋 분기 위**에 두어 빌더조쉬 먼저 매칭:
```python
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
        ... (기존)
```

#### `html_formatter_v2.py`
- 변경 불필요. `_render_stibee_v2`가 `StibeeNewsletter` 모든 항목을 동일 카드로 렌더링하므로 빌더조쉬는 배지 "빌더조쉬"·썸네일(og:image)·"뉴스레터 보기 →" 카드로 자동 노출.
- `fetch_stibee_images`도 `item.url` 기반으로 og:image를 추출하므로 maily.so에서도 동일 동작 예상. 만약 maily.so의 og:image가 다른 호스트(`cdn.maily.so`)라서 다운로드 실패 시, 카드는 텍스트 전용 카드(`v2-stibee-card` non-img variant)로 폴백되어 기능적 문제는 없음.

#### `html_formatter.py` (v1)
- 변경 검토 필요: v1도 stibee_items를 받아 처리. 빠른 점검은 구현 단계에서 진행. v1이 별도 분기 처리하면 비슷한 패턴으로 빌더조쉬 분기 추가, 일반 분기로 떨어지면 자동 처리.

#### `CLAUDE.md` (프로젝트)
- "요일별 수집 소스" 섹션에 수요일·금요일 빌더조쉬 줄 추가.
- "config.yaml 주요 설정" 섹션에 `wednesday_newsletters` / `friday_newsletters` 매주 수동 업데이트 안내 한 줄 추가.

## 인사말 컨텍스트

`_build_greeting_prompt`(formatter.py:253)의 기존 stibee_items 루프가 `item.source`, `item.title`, `item.topic`을 그대로 사용하므로 빌더조쉬 정보(`source="빌더조쉬"`, og:title, og:description)가 자동으로 인사말 생성 컨텍스트에 포함된다. 추가 코드 불필요.

## 예시 출력 (검증용)

```
📌 고객 한 명당 월 5,000달러를 받는 1인 AI 에이전트 사업가
"AI 에이전트가 아니라 'AI 직원'을 파세요"

1. 'AI 에이전트'가 아니라 '24시간 일하는 AI 직원'을 파는 방식으로 월 5,000달러 고정수익을 설계.
2. 타겟은 AI에 익숙하지 않은 전통 업종.
3. 트레로·셜·n8n 조합으로 운영 표준화.

https://maily.so/josh/posts/knrj1pn1rld
```

## 테스트 계획

수동 검증 (자동 테스트 인프라 없음):

1. `python -c "from collectors.builder_josh import fetch; ..."` 단독 호출로 3줄 요약 정상 생성 확인.
2. `python main.py --preview` 를 수요일(weekday=2) 시뮬레이션 또는 강제로 호출 — 메시지 본문에 빌더조쉬 블록 노출 확인.
3. `python main.py --now` 로 실제 출력 → `output_YYYYMMDD.txt` 및 `docs/v2/newsletters/YYYY-MM-DD.html` 검증.
4. URL이 비어 있을 때(`url: ""`) 빌더조쉬 블록이 누락만 되고 다른 콘텐츠는 정상 출력되는지 확인.
5. fetch 네트워크 실패 시 다른 콘텐츠는 정상 출력되는지 확인.

## 비범위 (Out of Scope)

- Gmail IMAP 기반 maily.so URL 자동 추출 (향후 필요 시 별도 작업).
- maily.so 목록 페이지(`maily.so/josh/posts/`) 자동 크롤링.
- 빌더조쉬 외 다른 maily.so 발행자 대응 (현재는 josh 전용 가정 없이 URL 기반으로 동작하므로 자연스럽게 확장 가능).
- 요약 캐싱 (매 발송마다 새 LLM 호출 — 비용 미미).

## 리스크

- **maily.so HTML 구조 변경**: og 메타와 본문 셀렉터에 의존. 변경 시 fetch 실패 → 메시지에서 빌더조쉬 블록만 누락(다른 콘텐츠는 정상). `_parse_putput` 등 기존 스크래퍼도 동일 리스크 보유.
- **LLM 요약 품질**: 본문이 너무 길거나 인터뷰가 산만하면 3줄 요약이 빈약할 수 있음. 프롬프트로 일정 수준 통제, 결과가 부족하면 (`summary_items`가 0~2개) 그대로 메시지에 노출 (텍스트는 짧아도 URL이 있으므로 사용자 클릭 유도 가능).
- **사용자가 config URL 갱신 잊음**: 화요일 스티비와 동일한 운영 리스크. 빈 URL이면 그날 빌더조쉬 블록만 누락.
