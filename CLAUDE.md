# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 실행 명령어

```bash
# 즉시 실행 (파일 저장)
python main.py --now

# 미리보기 (파일 저장 없이 콘솔 출력)
python main.py --preview

# 수집기 동작 테스트
python main.py --test

# 스케줄러 모드 (config.yaml의 send_time에 매일 자동 실행)
python main.py

# 개별 수집기 직접 테스트 (Windows 인코딩 처리 필요)
python -c "import sys,io; sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8'); from collectors.heypop import fetch; [print(i.title,i.url) for i in fetch('https://heypop.kr/')]"
```

## 아키텍처

### 전체 흐름
`main.py` → 수집기들(collectors/) → `formatter.py` → `output_YYYYMMDD.txt`

1. **main.py**: 요일 기반으로 수집기 선택 실행 → `build_message_windows_date()` 호출 → 파일 저장
2. **collectors/**: 각 소스별 독립 스크래퍼 (dataclass 반환)
3. **formatter.py**: 수집 데이터를 카카오톡 오픈채팅 전송용 텍스트로 조립 + Claude API로 인사말 생성

### 요일별 수집 소스
- **매일**: 아이보스(iboss), 뉴스럴(neusral), 롱블랙(longblack)
- **화요일(weekday=1)**: 풋풋레터, 캐릿 (stibee 공유 URL → `config.yaml`의 `tuesday_newsletters`에 매주 수동 업데이트 필요)
- **수요일(weekday=2)**: 빌더조쉬 (maily.so/josh — `builder_josh.url` 발송 직전 수동 갱신)
- **목요일(weekday=3)**: 헤이팝(heypop)
- **금요일(weekday=4)**: 빌더조쉬, 까탈로그 (빌더조쉬는 `builder_josh.url` 동일 슬롯 재갱신, 까탈로그는 `friday_newsletters` Gmail 자동→수동 폴백)

### 각 수집기 특성
| 파일 | 반환 타입 | 소스 |
|------|----------|------|
| `iboss.py` | `List[NewsItem]` | 아이보스 마케팅 뉴스 (번호 매긴 메인 기사) |
| `neusral.py` | `List[CategoryNews]` | 뉴스럴 카테고리별 헤드라인 |
| `heypop.py` | `List[HeypopItem]` | heypop.kr 메인 `.card-item` 최신 2개 |
| `longblack.py` | `LongblackItem` | 롱블랙 TODAY 섹션 아티클 |
| `stibee.py` | `StibeeNewsletter` | 스티비 공유 링크 파싱 (풋풋레터/캐릿/까탈로그) |
| `builder_josh.py` | `StibeeNewsletter` | maily.so/josh 글 (og 메타 + LLM 3줄 요약 자동 생성) |
| `email_reader.py` | `EmailNewsletter` | 메일플러그 IMAP (까탈로그 등) |

### 포맷 구조 (출력 순서)
1. `📌날짜 마케팅 뉴스` 헤더
2. 아이보스 번호 기사 (1~7개)
3. 뉴스럴 카테고리 헤드라인 (`🏷️카테고리`)
4. 헤이팝 (목요일만): `📌전시/팝업/공간 추천 [헤이팝 레터]` → `✅ 제목 / 설명 / URL` (2개)
5. 스티비/maily 뉴스레터 (요일별): 빌더조쉬(수/금) → 풋풋레터·캐릿(화) → 까탈로그(금) 순으로 `stibee_items` 리스트 처리
6. 롱블랙 `📌 제목`
7. Claude API 생성 인사말 (3문단)

### config.yaml 주요 설정
- `anthropic.api_key`: Claude API 키
- `tuesday_newsletters`: 화요일마다 풋풋레터·캐릿의 스티비 공유 URL을 **매주 수동 업데이트** 필요
- `builder_josh.url`: 빌더조쉬 maily.so 글 URL. **수/금 발송 직전 각각 수동 갱신** (단일 슬롯, 수→금 순서로 덮어쓰기)
- `friday_newsletters.catalogue`: 금요일 까탈로그 (Gmail 자동 추출 우선, 실패 시 수동 URL)
- `email`: 메일플러그 IMAP 정보 (현재 미설정 — 까탈로그 등 이메일 뉴스레터 사용 시 필요)
- `schedule.send_time`: 스케줄러 모드 실행 시각

### Windows 주의사항
- `main.py` 상단에서 `sys.stdout`을 UTF-8로 강제 설정 (이모지 출력)
- 개별 스크립트 직접 실행 시 동일 처리 필요
- 날짜 포맷은 `%-m` 미지원 → `str(today.month)` 사용 (`build_message_windows_date` 사용이 이유)
