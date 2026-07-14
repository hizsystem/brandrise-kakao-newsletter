"""발행된 카카오 텍스트를 슬랙으로 전송.

SLACK_WEBHOOK_URL 환경변수(슬랙 Incoming Webhook)가 있으면 오늘자
output_YYYYMMDD.txt 내용을 그대로 전송한다. 미설정이면 조용히 생략 —
발행 파이프라인을 실패시키지 않는다.
"""
import os
import sys
from pathlib import Path

import requests

from timeutil import now_kst

BASE_DIR = Path(__file__).parent


def send_today() -> bool:
    webhook_url = (os.environ.get("SLACK_WEBHOOK_URL") or "").strip()
    if not webhook_url:
        print("[INFO] SLACK_WEBHOOK_URL 미설정 — 슬랙 전송 생략")
        return True

    today = now_kst()
    output_path = BASE_DIR / f"output_{today.strftime('%Y%m%d')}.txt"
    if not output_path.exists():
        print(f"[WARN] {output_path.name} 없음 — 슬랙 전송 생략")
        return False

    text = output_path.read_text(encoding="utf-8")
    try:
        resp = requests.post(webhook_url, json={"text": text}, timeout=15)
    except requests.RequestException as e:
        print(f"[WARN] 슬랙 전송 실패: {e}")
        return False

    if resp.status_code == 200:
        print("[OK] 슬랙 전송 완료")
        return True
    print(f"[WARN] 슬랙 전송 실패: HTTP {resp.status_code} {resp.text[:200]}")
    return False


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    # 전송 실패해도 발행 자체는 성공이므로 종료 코드는 항상 0
    send_today()
