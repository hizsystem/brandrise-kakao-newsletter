# bootstrap.py — Render 시작 시 1회 실행. config 생성 + git 인증 설정.
import io
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import bootstrap_config

if __name__ == "__main__":
    cfg = bootstrap_config.ensure_config()
    print(f"[bootstrap] config ready: {cfg}")
    # git 인증 실패가 웹 서버 기동을 막으면 안 된다 — 실패해도 계속 진행.
    try:
        ok = bootstrap_config.setup_git_auth(Path(__file__).parent)
        print(f"[bootstrap] git auth set: {ok}")
    except Exception as e:  # noqa: BLE001 — 어떤 git 오류든 기동은 막지 않는다
        print(f"[bootstrap] git auth FAILED (web server will still start): {e}")
