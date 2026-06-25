"""
HIZ 뉴스레터 관리자 페이지
실행: python admin.py
브라우저: http://localhost:5001
"""
import hmac
import io
import os
import secrets as pysecrets
import subprocess
import sys
import threading
import time
from datetime import datetime
from functools import wraps
from pathlib import Path

import yaml
from flask import Flask, redirect, render_template_string, request, session, url_for

import bootstrap_config

# 호스팅/로컬 모두: config.yaml이 없으면 환경변수로 생성
bootstrap_config.ensure_config()

app = Flask(__name__)
CONFIG_PATH = Path(__file__).parent / "config.yaml"
DOCS_DIR = Path(__file__).parent / "docs"
PYTHON = sys.executable

# 마지막 실행 로그 (메모리)
_last_log = {"text": "", "running": False}

WEEKDAY_KO = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_config(config: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _init_auth():
    """config.yaml의 admin 섹션에서 비밀번호·세션 키 로드 (없으면 세션 키 자동 생성)"""
    config = load_config()
    admin_cfg = config.get("admin", {})
    password = admin_cfg.get("password", "")
    secret_key = admin_cfg.get("secret_key", "")
    if not secret_key:
        secret_key = pysecrets.token_hex(32)
        config.setdefault("admin", {})["secret_key"] = secret_key
        save_config(config)
    return password, secret_key


ADMIN_PASSWORD, app.secret_key = _init_auth()

# Render 등 호스팅 환경에서 비밀번호 미설정 시 공개 노출 방지
_IS_HOSTED = bool(os.environ.get("RENDER"))
bootstrap_config.require_auth_or_die(_IS_HOSTED, ADMIN_PASSWORD)


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not ADMIN_PASSWORD:
            # 비밀번호 미설정 시 인증 생략 (로컬 전용 사용)
            return f(*args, **kwargs)
        if not session.get("authed"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


LOGIN_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>HIZ 뉴스레터 관리자 — 로그인</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Noto Sans KR', sans-serif; background: #f0f2f5; color: #1a1a2e;
        display: flex; align-items: center; justify-content: center; min-height: 100vh; }
.login-card { background: white; border-radius: 20px; padding: 40px 36px; width: 100%;
               max-width: 380px; margin: 16px;
               box-shadow: 0 1px 4px rgba(0,0,0,0.06), 0 4px 16px rgba(0,0,0,0.04); }
.login-label { font-size: 11px; letter-spacing: 3px; color: #9ca3af; margin-bottom: 8px; }
.login-title { font-size: 22px; font-weight: 700; margin-bottom: 28px; }
.login-input { width: 100%; padding: 12px 16px; border: 1px solid #e5e7eb; border-radius: 10px;
                font-size: 15px; outline: none; margin-bottom: 16px;
                font-family: 'Noto Sans KR', sans-serif; }
.login-input:focus { border-color: #6366f1; box-shadow: 0 0 0 3px rgba(99,102,241,0.1); }
.login-btn { width: 100%; padding: 13px; border-radius: 10px; font-size: 15px; font-weight: 600;
              border: none; cursor: pointer; background: #0f172a; color: white;
              font-family: 'Noto Sans KR', sans-serif; }
.login-btn:hover { background: #1e1b4b; }
.login-error { background: #fef2f2; border: 1px solid #fecaca; color: #dc2626;
                border-radius: 10px; padding: 10px 14px; margin-bottom: 16px; font-size: 13px; }
</style>
</head>
<body>
<form class="login-card" method="post" action="/login">
  <div class="login-label">BRANDRISE NEWSLETTER · ADMIN</div>
  <div class="login-title">관리자 로그인</div>
  {% if error %}<div class="login-error">비밀번호가 올바르지 않습니다</div>{% endif %}
  <input class="login-input" type="password" name="password" placeholder="비밀번호" autofocus>
  <button class="login-btn" type="submit">로그인</button>
</form>
</body>
</html>"""


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        entered = request.form.get("password", "")
        if ADMIN_PASSWORD and hmac.compare_digest(entered, ADMIN_PASSWORD):
            session["authed"] = True
            session.permanent = True
            return redirect(url_for("index"))
        time.sleep(1)  # 무차별 대입 지연
        return render_template_string(LOGIN_HTML, error=True)
    return render_template_string(LOGIN_HTML, error=False)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>HIZ 뉴스레터 관리자</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Noto Sans KR', sans-serif; background: #f0f2f5; color: #1a1a2e; }
.wrapper { max-width: 720px; margin: 0 auto; padding: 40px 16px 80px; }

/* 헤더 */
.header { background: linear-gradient(135deg, #0f172a, #1e1b4b);
           color: white; padding: 32px 36px; border-radius: 20px; margin-bottom: 24px; }
.header-label { font-size: 11px; letter-spacing: 3px; opacity: 0.5; margin-bottom: 8px; }
.header-title { font-size: 24px; font-weight: 700; margin-bottom: 4px; }
.header-date { font-size: 14px; opacity: 0.6; }

/* 카드 */
.card { background: white; border-radius: 16px; padding: 28px; margin-bottom: 16px;
         box-shadow: 0 1px 4px rgba(0,0,0,0.06), 0 4px 16px rgba(0,0,0,0.04); }
.card-title { font-size: 13px; font-weight: 600; color: #374151; margin-bottom: 20px;
               display: flex; align-items: center; gap: 8px; padding-bottom: 14px;
               border-bottom: 1px solid #f3f4f6; }

/* 폼 필드 */
.field { margin-bottom: 20px; }
.field:last-child { margin-bottom: 0; }
.field-label { font-size: 13px; font-weight: 600; color: #374151; margin-bottom: 6px;
                display: flex; align-items: center; gap: 8px; }
.field-badge { font-size: 10px; padding: 2px 8px; border-radius: 20px; font-weight: 600; }
.badge-daily  { background: #eef2ff; color: #6366f1; }
.badge-tue    { background: #ecfdf5; color: #059669; }
.badge-wed    { background: #fef2f2; color: #dc2626; }
.badge-fri    { background: #fff7ed; color: #d97706; }
.badge-wedfri { background: #faf5ff; color: #7c3aed; }
.field-hint { font-size: 12px; color: #9ca3af; margin-bottom: 8px; }
.field input { width: 100%; padding: 10px 14px; border: 1px solid #e5e7eb; border-radius: 10px;
                font-size: 13px; font-family: monospace; color: #374151; outline: none;
                transition: border-color 0.15s; }
.field input:focus { border-color: #6366f1; box-shadow: 0 0 0 3px rgba(99,102,241,0.1); }
.field input::placeholder { color: #d1d5db; }

/* 버튼 */
.actions { display: flex; gap: 12px; flex-wrap: wrap; }
.btn { padding: 12px 24px; border-radius: 10px; font-size: 14px; font-weight: 600;
        border: none; cursor: pointer; font-family: 'Noto Sans KR', sans-serif;
        transition: all 0.15s; }
.btn-primary { background: #6366f1; color: white; }
.btn-primary:hover { background: #4f46e5; }
.btn-dark { background: #0f172a; color: white; }
.btn-dark:hover { background: #1e1b4b; }
.btn-secondary { background: #f3f4f6; color: #374151; }
.btn-secondary:hover { background: #e5e7eb; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }

/* 로그 */
.log-box { background: #0f172a; color: #e2e8f0; border-radius: 12px; padding: 20px;
            font-family: monospace; font-size: 13px; line-height: 1.8; white-space: pre-wrap;
            max-height: 400px; overflow-y: auto; }
.log-empty { color: #475569; }
.log-ok    { color: #4ade80; }
.log-warn  { color: #fbbf24; }
.log-error { color: #f87171; }

/* 알림 */
.toast { background: #ecfdf5; border: 1px solid #bbf7d0; color: #166534;
          border-radius: 10px; padding: 12px 16px; margin-bottom: 16px; font-size: 14px; }

/* 링크 */
.site-link { display: inline-flex; align-items: center; gap: 6px; font-size: 13px;
               color: #6366f1; border: 1px solid #e0e7ff; padding: 7px 16px;
               border-radius: 20px; text-decoration: none; }
.site-link:hover { background: #eef2ff; }

/* 필드 옆 "찾으러 가기" 링크 */
.find-link { display: inline-flex; align-items: center; gap: 4px; margin-left: 8px;
              font-size: 12px; font-weight: 600; color: #6366f1; text-decoration: none;
              white-space: nowrap; }
.find-link:hover { text-decoration: underline; }

/* 안내 박스 */
.manual-note { font-size: 12.5px; color: #6b7280; line-height: 1.7;
                background: #f9fafb; border: 1px solid #f0f1f3; border-radius: 10px;
                padding: 12px 16px; margin-bottom: 20px; }
.manual-note b { color: #374151; }

/* 아카이브 */
.archive-item { display: flex; align-items: center; justify-content: space-between;
                 padding: 12px 0; border-bottom: 1px solid #f3f4f6;
                 text-decoration: none; color: #374151; font-size: 14px; }
.archive-item:last-child { border-bottom: none; padding-bottom: 0; }
.archive-item:hover { color: #6366f1; }
.archive-arrow { color: #9ca3af; font-size: 13px; }
</style>
</head>
<body>
<div class="wrapper">

  <!-- 헤더 -->
  <div class="header">
    <div class="header-label">BRANDRISE NEWSLETTER · ADMIN</div>
    <div class="header-title">뉴스레터 관리자</div>
    <div class="header-date">{{ today }}</div>
  </div>

  {% if saved %}
  <div class="toast">✓ 저장 완료</div>
  {% endif %}

  <!-- 수동 URL 입력 폼 -->
  <form method="post" action="/save">
    <div class="card">
      <div class="card-title">📖 수동 입력 URL</div>

      <div class="manual-note">
        <b>요일별로 필요한 것만 채우면 됩니다.</b> 각 항목의 <b>찾으러 가기</b> 링크를 누르면 출처로 바로 이동합니다.<br>
        · <b>매일</b>: 롱블랙 &nbsp; · <b>화</b>: 풋풋레터·캐릿 &nbsp; · <b>수·금</b>: 빌더조쉬 &nbsp; · <b>금</b>: 까탈로그<br>
        이메일로 오는 항목은 Gmail에서 해당 뉴스레터를 연 뒤 <b>"웹으로 보기"</b> 링크를 복사하세요.
      </div>

      <!-- 롱블랙 -->
      <div class="field">
        <div class="field-label">
          롱블랙 티켓 URL
          <span class="field-badge badge-daily">매일</span>
        </div>
        <div class="field-hint">롱블랙 이메일 → "아티클 읽기" 링크 복사 (ticket= 포함된 URL)
          <a class="find-link" href="https://mail.google.com/mail/u/0/#search/롱블랙" target="_blank">↗ Gmail에서 찾기</a>
          <a class="find-link" href="https://longblack.co" target="_blank">↗ longblack.co</a>
        </div>
        <input type="url" name="longblack_ticket_url"
               value="{{ longblack_url }}"
               placeholder="https://longblack.co/note/xxxx?ticket=NT...">
      </div>

      <!-- 풋풋레터 -->
      <div class="field">
        <div class="field-label">
          풋풋레터 URL
          <span class="field-badge badge-tue">화요일</span>
        </div>
        <div class="field-hint">풋풋레터 이메일 → "웹으로 보기" 링크 복사
          <a class="find-link" href="https://mail.google.com/mail/u/0/#search/풋풋레터" target="_blank">↗ Gmail에서 찾기</a>
        </div>
        <input type="url" name="putput_url"
               value="{{ putput_url }}"
               placeholder="https://stibee.com/api/v1.0/emails/share/...">
      </div>

      <!-- 캐릿 -->
      <div class="field">
        <div class="field-label">
          캐릿 URL
          <span class="field-badge badge-tue">화요일</span>
        </div>
        <div class="field-hint">캐릿 이메일 → "웹으로 보기" 링크 복사
          <a class="find-link" href="https://mail.google.com/mail/u/0/#search/캐릿" target="_blank">↗ Gmail에서 찾기</a>
        </div>
        <input type="url" name="careet_url"
               value="{{ careet_url }}"
               placeholder="https://stibee.com/api/v1.0/emails/share/...">
      </div>

      <!-- 빌더조쉬 (수/금 공용 단일 슬롯) -->
      <div class="field">
        <div class="field-label">
          빌더조쉬 URL
          <span class="field-badge badge-wedfri">수·금 공용</span>
        </div>
        <div class="field-hint">maily.so/josh 에서 이번 주 글 URL 복사 (수요일·금요일 발송 직전 각각 새 URL로 덮어쓰기)
          <a class="find-link" href="https://maily.so/josh" target="_blank">↗ maily.so/josh 열기</a>
        </div>
        <input type="url" name="builder_josh_url"
               value="{{ builder_josh_url }}"
               placeholder="https://maily.so/josh/posts/...">
      </div>

      <!-- 까탈로그 -->
      <div class="field">
        <div class="field-label">
          까탈로그 URL
          <span class="field-badge badge-fri">금요일</span>
        </div>
        <div class="field-hint">까탈로그 이메일 → "웹으로 보기" 링크 복사
          <a class="find-link" href="https://mail.google.com/mail/u/0/#search/까탈로그" target="_blank">↗ Gmail에서 찾기</a>
        </div>
        <input type="url" name="catalogue_url"
               value="{{ catalogue_url }}"
               placeholder="https://stibee.com/api/v1.0/emails/share/...">
      </div>
    </div>

    <div class="actions" style="margin-bottom: 24px;">
      <button type="submit" class="btn btn-secondary">저장만 하기</button>
      <button type="submit" form="generate-form" class="btn btn-dark" id="gen-btn">
        ⚡ 저장 + 뉴스레터 지금 생성
      </button>
    </div>
  </form>

  <!-- 생성 버튼 (별도 폼 — 숨김) -->
  <form id="generate-form" method="post" action="/generate"
        onsubmit="document.getElementById('gen-btn').disabled=true;
                  document.getElementById('gen-btn').textContent='⏳ 생성 중...';
                  return true;">
    <input type="hidden" name="longblack_ticket_url" id="hid-lb">
    <input type="hidden" name="putput_url" id="hid-pp">
    <input type="hidden" name="careet_url" id="hid-ca">
    <input type="hidden" name="builder_josh_url" id="hid-bj">
    <input type="hidden" name="catalogue_url" id="hid-ct">
  </form>
  <script>
    // 생성 버튼 클릭 시 현재 입력값을 hidden 폼에 복사
    document.getElementById('generate-form').addEventListener('submit', function() {
      document.getElementById('hid-lb').value = document.querySelector('[name=longblack_ticket_url]').value;
      document.getElementById('hid-pp').value = document.querySelector('[name=putput_url]').value;
      document.getElementById('hid-ca').value = document.querySelector('[name=careet_url]').value;
      document.getElementById('hid-bj').value = document.querySelector('[name=builder_josh_url]').value;
      document.getElementById('hid-ct').value = document.querySelector('[name=catalogue_url]').value;
    });
  </script>

  <!-- GitHub Pages 링크 -->
  <div class="card">
    <div class="card-title">🌐 웹사이트</div>
    <a class="site-link" href="{{ pages_url }}" target="_blank">Brandrise 뉴스레터 열기 →</a>
  </div>

  <!-- 아카이브 -->
  {% if archive %}
  <div class="card">
    <div class="card-title">📁 지난 뉴스레터</div>
    {% for item in archive %}
    <a class="archive-item" href="{{ pages_base }}v2/newsletters/{{ item.date }}.html" target="_blank">
      <span class="archive-date">{{ item.display }}</span>
      <span class="archive-arrow">↗</span>
    </a>
    {% endfor %}
  </div>
  {% endif %}

  <!-- 정부지원사업 공고 발행 -->
  <div class="card" style="margin-top:32px; border-top: 2px solid #f3f4f6; padding-top:28px;">
    <div class="card-title">📋 정부지원사업 공고 발행</div>
    <form method="post" action="/publish-grants">
      <div class="field">
        <div class="field-label">상단 공지 문구</div>
        <div class="field-hint">공고 페이지 상단에 항상 고정 노출되는 안내 문구 (URL은 자동 링크 처리)</div>
        <textarea name="grants_notice" rows="5"
          style="width:100%; padding:10px 14px; border:1px solid #e5e7eb; border-radius:10px;
                 font-size:13px; resize:vertical; outline:none; line-height:1.7;"
          >{{ grants_notice }}</textarea>
      </div>
      <div class="field">
        <div class="field-label">공고 목록 붙여넣기</div>
        <div class="field-hint">공고명 + URL 형식으로 된 텍스트를 그대로 붙여넣으세요</div>
        <textarea name="grants_text" rows="10"
          style="width:100%; padding:10px 14px; border:1px solid #e5e7eb; border-radius:10px;
                 font-size:13px; font-family:monospace; resize:vertical; outline:none;"
          placeholder="[경기] 2026년 물기술 실증화 지원사업 참여기업 모집 공고&#10;https://cafe.naver.com/...&#10;&#10;2026년 XR 기술개발 지원사업 참여기업 모집&#10;https://cafe.naver.com/...">{{ grants_text }}</textarea>
      </div>
      <div class="actions" style="margin-top:12px;">
        <button type="submit" class="btn btn-dark">📤 공고 발행 + GitHub 업로드</button>
      </div>
    </form>
    {% if grants_url %}
    <div style="margin-top:16px;">
      <a class="site-link" href="{{ grants_url }}" target="_blank">오늘 공고 페이지 열기 →</a>
    </div>
    {% endif %}
  </div>

  <!-- 마지막 실행 로그 -->
  {% if log %}
  <div class="card">
    <div class="card-title">📋 마지막 실행 로그</div>
    <div class="log-box">{{ log }}</div>
  </div>
  {% endif %}

</div>
</body>
</html>"""


def get_urls(config: dict) -> dict:
    """config에서 현재 URL 값 추출 (빌더조쉬는 수/금 공용 단일 슬롯)"""
    manual = config.get("manual", {})
    tuesday = config.get("tuesday_newsletters", {})
    friday = config.get("friday_newsletters", {})
    builder_josh = config.get("builder_josh", {})
    return {
        "longblack_url": manual.get("longblack_ticket_url", ""),
        "putput_url": tuesday.get("putput", {}).get("url", ""),
        "careet_url": tuesday.get("careet", {}).get("url", ""),
        "builder_josh_url": builder_josh.get("url", ""),
        "catalogue_url": friday.get("catalogue", {}).get("url", ""),
    }


def update_config_urls(config: dict, form: dict) -> dict:
    """폼 데이터로 config 업데이트 (새 dict 반환).
    빌더조쉬는 top-level builder_josh 단일 슬롯 사용.
    옛 wednesday_newsletters / friday_newsletters.builder_josh 잔존 키는 자동 정리.
    """
    if "manual" not in config:
        config["manual"] = {}
    config["manual"]["longblack_ticket_url"] = form.get("longblack_ticket_url", "").strip()
    config["manual"]["longblack_ticket_date"] = datetime.now().strftime("%Y-%m-%d")

    if "tuesday_newsletters" not in config:
        config["tuesday_newsletters"] = {}
    if "putput" not in config["tuesday_newsletters"]:
        config["tuesday_newsletters"]["putput"] = {"name": "풋풋레터"}
    if "careet" not in config["tuesday_newsletters"]:
        config["tuesday_newsletters"]["careet"] = {"name": "캐릿"}

    config["tuesday_newsletters"]["putput"]["url"] = form.get("putput_url", "").strip()
    config["tuesday_newsletters"]["careet"]["url"] = form.get("careet_url", "").strip()

    # 빌더조쉬: top-level 단일 슬롯
    if "builder_josh" not in config:
        config["builder_josh"] = {"name": "빌더조쉬"}
    config["builder_josh"]["url"] = form.get("builder_josh_url", "").strip()

    # 옛 분리 구조 잔존 키 정리
    if "wednesday_newsletters" in config:
        del config["wednesday_newsletters"]
    if "friday_newsletters" in config and "builder_josh" in config["friday_newsletters"]:
        del config["friday_newsletters"]["builder_josh"]

    if "friday_newsletters" not in config:
        config["friday_newsletters"] = {}
    if "catalogue" not in config["friday_newsletters"]:
        config["friday_newsletters"]["catalogue"] = {"name": "까탈로그"}

    config["friday_newsletters"]["catalogue"]["url"] = form.get("catalogue_url", "").strip()
    return config


def today_str() -> str:
    now = datetime.now()
    wd = WEEKDAY_KO[now.weekday()]
    return f"{now.year}년 {now.month}월 {now.day}일 ({wd})"


def run_newsletter() -> str:
    """main.py --now 실행, 출력 반환"""
    try:
        result = subprocess.run(
            [PYTHON, "main.py", "--now"],
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=900,
        )
        output = result.stdout + result.stderr
    except subprocess.TimeoutExpired as e:
        partial_out = (e.stdout or "") + (e.stderr or "")
        output = (
            f"[ERROR] main.py --now 가 900초 안에 끝나지 않아 종료했습니다.\n"
            f"마지막 stdout/stderr:\n{partial_out}"
        )
    return output


def get_longblack_scraped_url() -> str:
    """롱블랙 공개 URL 실시간 스크래핑 (admin 페이지 표시용)"""
    try:
        from collectors.longblack import fetch as lb_fetch
        item = lb_fetch()
        return item.url if item else ""
    except Exception:
        return ""


def get_archive_items(docs_dir: Path) -> list:
    """docs/v2/newsletters/ 에서 날짜 목록 반환 (최신순)"""
    newsletters_dir = docs_dir / "v2" / "newsletters"
    if not newsletters_dir.exists():
        return []
    files = sorted(newsletters_dir.glob("*.html"), reverse=True)
    items = []
    for f in files:
        date_str = f.stem
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            wd = ["월", "화", "수", "목", "금", "토", "일"][dt.weekday()]
            display = f"{dt.year}년 {dt.month}월 {dt.day}일 ({wd})"
        except ValueError:
            display = date_str
        items.append({"date": date_str, "display": display})
    return items


def _pages_base(config: dict) -> str:
    pages_url = config.get("github", {}).get("pages_url", "").rstrip("/")
    return f"{pages_url}/" if pages_url else ""


@app.route("/", methods=["GET"])
@login_required
def index():
    config = load_config()
    urls = get_urls(config)
    pages_base = _pages_base(config)

    # 롱블랙: 오늘 티켓 URL이 없으면 공개 URL 자동 표시
    today_iso = datetime.now().strftime("%Y-%m-%d")
    manual = config.get("manual", {})
    if not (manual.get("longblack_ticket_url") and manual.get("longblack_ticket_date") == today_iso):
        urls["longblack_url"] = get_longblack_scraped_url()

    docs_dir = Path(__file__).parent / "docs"
    archive = get_archive_items(docs_dir)

    # 오늘 공고 페이지 URL (이미 발행된 경우)
    date_iso = datetime.now().strftime("%Y-%m-%d")
    grants_page = DOCS_DIR / "grants" / f"{date_iso}.html"
    grants_url = f"{pages_base}grants/{date_iso}.html" if grants_page.exists() and pages_base else ""

    grants_notice = config.get("grants_notice", "")

    today_v2_url = f"{pages_base}v2/newsletters/{date_iso}.html" if pages_base else ""
    return render_template_string(
        HTML,
        today=today_str(),
        saved=request.args.get("saved"),
        log=_last_log["text"],
        pages_url=today_v2_url,
        archive=archive,
        pages_base=pages_base,
        grants_text="",
        grants_url=grants_url,
        grants_notice=grants_notice,
        **urls,
    )


@app.route("/save", methods=["POST"])
@login_required
def save():
    config = load_config()
    config = update_config_urls(config, request.form)
    save_config(config)
    return redirect(url_for("index", saved=1))


@app.route("/generate", methods=["POST"])
@login_required
def generate():
    config = load_config()
    config = update_config_urls(config, request.form)
    save_config(config)

    _last_log["running"] = True
    _last_log["text"] = "⏳ 생성 중..."
    log = run_newsletter()
    _last_log["text"] = log
    _last_log["running"] = False

    return redirect(url_for("index", saved=1))


@app.route("/publish-grants", methods=["POST"])
@login_required
def publish_grants():
    from grants_formatter import save_grants
    text = request.form.get("grants_text", "").strip()
    notice = request.form.get("grants_notice", "").strip()
    if not text:
        return redirect(url_for("index"))

    # 공지 문구 config에 저장
    if notice:
        config = load_config()
        config["grants_notice"] = notice
        save_config(config)

    try:
        grant_path = save_grants(text, DOCS_DIR, notice=notice)
        # GitHub 푸시
        from github_push import push_to_github
        date_iso = datetime.now().strftime("%Y-%m-%d")
        push_to_github(Path(__file__).parent, f"grants-{date_iso}")
        _last_log["text"] = f"[OK] 공고 발행 완료: {grant_path.name}\n공고 수: {text.count('http')}건"
    except Exception as e:
        _last_log["text"] = f"[ERROR] 공고 발행 실패: {e}"

    return redirect(url_for("index", saved=1))


if __name__ == "__main__":
    import webbrowser
    print("=" * 50)
    print("  HIZ 뉴스레터 관리자 시작")
    print("  http://localhost:5001")
    print("  종료: Ctrl+C")
    print("=" * 50)
    webbrowser.open("http://localhost:5001")
    app.run(host="localhost", port=5001, debug=False)
