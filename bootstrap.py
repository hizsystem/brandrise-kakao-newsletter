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
    ok = bootstrap_config.setup_git_auth(Path(__file__).parent)
    print(f"[bootstrap] git auth set: {ok}")
