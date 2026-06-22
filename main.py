"""
데일리 뉴스레터 에이전트 메인
실행: python main.py [--now] [--preview] [--test]
  --now     : 즉시 실행
  --preview : 파일 저장 없이 콘솔 미리보기만
  --test    : 각 수집기 동작 확인
"""

import sys
import io
import yaml

# Windows 콘솔 UTF-8 강제 설정 (이모지 출력)
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

import schedule
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path

from collectors import iboss, neusral, heypop
from collectors import longblack as longblack_collector
from collectors import stibee as stibee_collector
from collectors import builder_josh as builder_josh_collector
from collectors.email_reader import MailplugReader
from formatter import build_message_windows_date, generate_greeting, WEEKDAY_GREETINGS
from html_formatter import save_newsletter
from html_formatter_v2 import save_newsletter_v2
from github_push import push_to_github


CONFIG_PATH = Path(__file__).parent / "config.yaml"
OUTPUT_DIR = Path(__file__).parent


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _rebuild_archives(docs_dir: Path, today: datetime = None):
    """전체 아카이브(archive.html) + 주간 아카이브(index.html, 주말만) 재생성"""
    from html_formatter_v2 import build_full_archive_v2, build_weekly_archive_v2
    from html_formatter import build_archive_html, build_weekly_archive_v1

    v2_newsletters_dir = docs_dir / "v2" / "newsletters"
    v1_newsletters_dir = docs_dir / "newsletters"

    # 전체 아카이브 (평일/주말 항상 재생성)
    try:
        (docs_dir / "v2" / "archive.html").write_text(
            build_full_archive_v2(v2_newsletters_dir), encoding="utf-8"
        )
        print("  [OK] v2 전체 아카이브 재생성")
    except Exception as e:
        print(f"  [WARN] v2 전체 아카이브 실패: {e}")

    try:
        (docs_dir / "archive.html").write_text(
            build_archive_html(v2_newsletters_dir), encoding="utf-8"
        )
        print("  [OK] 전체 아카이브 재생성 (v2 기준)")
    except Exception as e:
        print(f"  [WARN] 전체 아카이브 실패: {e}")

    # 주말 index.html → 주간 아카이브로 교체
    if today and today.weekday() in (5, 6):
        try:
            (docs_dir / "v2" / "index.html").write_text(
                build_weekly_archive_v2(today, v2_newsletters_dir), encoding="utf-8"
            )
            print("  [OK] v2 주간 아카이브 페이지 생성")
        except Exception as e:
            print(f"  [WARN] v2 주간 아카이브 실패: {e}")

        try:
            (docs_dir / "index.html").write_text(
                build_weekly_archive_v1(today, v1_newsletters_dir), encoding="utf-8"
            )
            print("  [OK] v1 주간 아카이브 페이지 생성")
        except Exception as e:
            print(f"  [WARN] v1 주간 아카이브 실패: {e}")


def run_newsletter(config: dict, preview_only: bool = False):
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 뉴스레터 수집 시작...")

    today = datetime.now()
    weekday = today.weekday()  # 0=월 … 4=금, 5=토, 6=일

    # 주말 — 금요일 파일 복사 후 종료
    if weekday in (5, 6) and not preview_only:
        day_name = "토요일" if weekday == 5 else "일요일"
        print(f"  [{day_name}] 주말은 수집 없이 금요일 뉴스레터를 유지합니다.")
        docs_dir = OUTPUT_DIR / "docs"
        _rebuild_archives(docs_dir, today)
        push_to_github(OUTPUT_DIR, today.strftime("%Y-%m-%d"))
        return

    iboss_items = []
    neusral_cats = []
    heypop_items = []
    longblack_item = None
    stibee_items = []
    email_newsletters = {}

    # 아이보스 (매일)
    try:
        print("  → 아이보스 수집 중...")
        iboss_items = iboss.fetch(config["sites"]["iboss"]["url"])
        print(f"     {len(iboss_items)}개 항목 수집")
    except Exception as e:
        print(f"  [WARN] 아이보스 수집 실패: {e}")

    # 뉴스럴 (매일) — 일시 비활성화 (2026-06-22). 되살리려면 아래 블록 주석 해제.
    # try:
    #     print("  → 뉴스럴 수집 중...")
    #     neusral_cats = neusral.fetch(config["sites"]["neusral"]["url"])
    #     print(f"     {len(neusral_cats)}개 카테고리 수집")
    # except Exception as e:
    #     print(f"  [WARN] 뉴스럴 수집 실패: {e}")

    # 롱블랙 (매일 - 웹 스크래핑 + 관리자 페이지 티켓 URL 적용)
    try:
        print("  → 롱블랙 수집 중...")
        longblack_item = longblack_collector.fetch()
        if longblack_item:
            today_iso = datetime.now().strftime("%Y-%m-%d")
            manual = config.get("manual", {})
            ticket_url = manual.get("longblack_ticket_url", "")
            ticket_date = manual.get("longblack_ticket_date", "")
            if ticket_url and ticket_date == today_iso:
                longblack_item = longblack_collector.LongblackItem(
                    title=longblack_item.title,
                    subtitle=longblack_item.subtitle,
                    url=ticket_url,
                )
                print(f"     {longblack_item.title[:40]} (티켓 URL 적용)")
            else:
                print(f"     {longblack_item.title[:40]}")
    except Exception as e:
        print(f"  [WARN] 롱블랙 수집 실패: {e}")

    # 화요일 뉴스레터 (풋풋레터, 캐릿) - Gmail 자동 → 수동 URL 순서
    if weekday == 1:
        email_cfg = config.get("email", {})
        tuesday_cfg = config.get("tuesday_newsletters", {})
        for key, cfg in tuesday_cfg.items():
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
                        # 자동 추출한 URL이면 config에 저장
                        tuesday_cfg[key]["url"] = url
                        print(f"     {item.title[:40]}")
                except Exception as e:
                    print(f"  [WARN] {name} 수집 실패: {e}")

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

    # 헤이팝 (목요일)
    if weekday == 3:
        try:
            print("  → 헤이팝 수집 중...")
            heypop_items = heypop.fetch(config["sites"]["heypop"]["url"])
            print(f"     {len(heypop_items)}개 항목 수집")
        except Exception as e:
            print(f"  [WARN] 헤이팝 수집 실패: {e}")

    # === 인사말 생성 (1회 — txt/HTML 공유) ===
    print("  → 인사말 생성 중...")
    weekday = datetime.now().weekday()
    weekday_name, weekday_msg = WEEKDAY_GREETINGS.get(weekday, ("", ""))
    api_key = config["anthropic"]["api_key"]
    model = config["anthropic"].get("model", "claude-sonnet-4-6")
    groq_key = config.get("groq", {}).get("api_key", "")
    groq_model = config.get("groq", {}).get("model", "llama-3.3-70b-versatile")
    gemini_key = config.get("gemini", {}).get("api_key", "")
    gemini_model = config.get("gemini", {}).get("model", "gemini-2.0-flash")

    try:
        greeting = generate_greeting(
            api_key=api_key,
            model=model,
            iboss_items=iboss_items,
            weekday_name=weekday_name,
            weekday_msg=weekday_msg,
            longblack_item=longblack_item,
            stibee_items=stibee_items,
            heypop_items=heypop_items,
            groq_api_key=groq_key,
            groq_model=groq_model,
            gemini_api_key=gemini_key,
            gemini_model=gemini_model,
        )
    except Exception as e:
        print(f"  [WARN] 인사말 생성 실패: {e}")
        greeting = f"안녕하세요! {weekday_name} 마케팅 소식 전해드립니다 😊 {weekday_msg}"

    # === 텍스트 메시지 포맷팅 ===
    try:
        message = build_message_windows_date(
            iboss_items=iboss_items,
            neusral_categories=neusral_cats,
            email_newsletters=email_newsletters,
            heypop_items=heypop_items,
            longblack_item=longblack_item,
            stibee_items=stibee_items,
            api_key=api_key,
            model=model,
            greeting=greeting,
        )
    except Exception as e:
        print(f"  [ERROR] 메시지 생성 실패: {e}")
        traceback.print_exc()
        return

    # === 미리보기 ===
    if preview_only:
        print("\n" + "=" * 60)
        print(message)
        print("=" * 60)
        return

    # === txt 파일 저장 ===
    today = datetime.now()
    today_str = today.strftime('%Y%m%d')
    date_iso = today.strftime("%Y-%m-%d")
    pages_url = config.get("github", {}).get("pages_url", "").rstrip("/")
    permalink = f"{pages_url}/v2/newsletters/{date_iso}.html" if pages_url else ""
    if permalink:
        message = message + f"\n\n🔗 오늘 뉴스레터 링크\n{permalink}"
    save_path = OUTPUT_DIR / f"output_{today_str}.txt"
    save_path.write_text(message, encoding="utf-8")
    print(f"\n  [OK] txt 저장 완료: {save_path.name}")

    # === HTML 생성 + GitHub Pages 푸시 ===
    if config.get("github", {}).get("enabled", True):
        try:
            docs_dir = OUTPUT_DIR / "docs"
            html_path = save_newsletter(
                iboss_items=iboss_items,
                neusral_categories=neusral_cats,
                heypop_items=heypop_items,
                longblack_item=longblack_item,
                stibee_items=stibee_items or [],
                greeting=greeting,
                docs_dir=docs_dir,
            )
            print(f"  [OK] HTML 생성 완료: {html_path.name}")
            save_newsletter_v2(
                iboss_items=iboss_items,
                neusral_categories=neusral_cats,
                heypop_items=heypop_items,
                longblack_item=longblack_item,
                stibee_items=stibee_items or [],
                greeting=greeting,
                docs_dir=docs_dir,
                anthropic_api_key=api_key,
                gemini_api_key=gemini_key,
            )
            print(f"  [OK] HTML v2 생성 완료")
            _rebuild_archives(docs_dir)
            pushed = push_to_github(OUTPUT_DIR, today.strftime("%Y-%m-%d"))
            pages_url = config.get("github", {}).get("pages_url", "").rstrip("/")
            if pushed and pages_url:
                date_iso = today.strftime("%Y-%m-%d")
                permalink = f"{pages_url}/v2/newsletters/{date_iso}.html"
                print(f"\n  📎 오늘 뉴스레터 고정 링크:")
                print(f"     {permalink}\n")
        except Exception as e:
            print(f"  [WARN] HTML/GitHub 처리 실패: {e}")
            traceback.print_exc()

    print("=" * 60)
    print(message)
    print("=" * 60)


def run_test(config: dict):
    print("\n=== 수집기 테스트 ===\n")
    for name, fn, args in [
        ("아이보스", iboss.fetch, [config["sites"]["iboss"]["url"]]),
        ("뉴스럴",  neusral.fetch, [config["sites"]["neusral"]["url"]]),
        ("롱블랙",  longblack_collector.fetch, []),
        ("헤이팝",  heypop.fetch, [config["sites"]["heypop"]["url"]]),
    ]:
        try:
            result = fn(*args)
            count = len(result) if isinstance(result, list) else (1 if result else 0)
            print(f"  ✓ {name}: {count}건")
        except Exception as e:
            print(f"  ✗ {name}: {e}")


def main():
    args = sys.argv[1:]
    preview_only = "--preview" in args
    run_now = "--now" in args or "--preview" in args
    test_mode = "--test" in args

    config = load_config()

    if test_mode:
        run_test(config)
        return

    if run_now:
        run_newsletter(config, preview_only=preview_only)
        return

    # 스케줄 모드
    send_time = config.get("schedule", {}).get("send_time", "08:30")
    print(f"스케줄러 시작 - 매일 {send_time}에 파일 생성")
    print("종료: Ctrl+C\n")
    schedule.every().day.at(send_time).do(run_newsletter, config=config)
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
