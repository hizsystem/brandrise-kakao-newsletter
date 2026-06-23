# 데일리 뉴스레터 업무 핸드오프 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 로컬에서만 도는 뉴스레터 관리 패널을 비밀번호 보호된 공유 링크(Render 무료 호스팅)로 올리고, 모든 API 키를 회사 계정 키로 교체해 비용을 회사 계정으로 청구되게 한다. 운영 프로세스는 현재와 동일.

**Architecture:** 비밀 값은 코드 저장소 밖(Render 환경변수)에 둔다. 서버 시작 시 `bootstrap.py`가 `config.base.yaml`(비밀 아닌 기본값) + 환경변수를 합쳐 `config.yaml`을 생성하므로 기존 `load_config()`/`main.py`/`admin.py`는 거의 그대로 동작한다. GitHub Pages 발행은 환경변수 토큰으로 인증된 remote에 push. gunicorn으로 `admin:app`을 서비스한다.

**Tech Stack:** Python 3.12, Flask(기존), gunicorn, PyYAML, Render(무료 Web Service), GitHub fine-grained PAT.

## Global Constraints

- 저장소(`hizsystem/brandrise-kakao-newsletter`)에 **비밀 값을 절대 커밋하지 않는다**. 비밀은 환경변수 전용. `config.yaml`·`.env`는 이미 `.gitignore`에 있음.
- Windows 파일 I/O는 `encoding="utf-8"` 명시(기존 규칙).
- 기존 `admin.py`/`main.py`의 동작·UI를 바꾸지 않는다. 운영 프로세스 유지(사람이 링크 열고 URL 붙여넣고 생성 후 카톡 복사).
- 환경변수 표준 이름: `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `ADMIN_PASSWORD`, `FLASK_SECRET_KEY`, `GH_TOKEN`, (선택) `GIT_USER_NAME`, `GIT_USER_EMAIL`, `GH_REMOTE`.
- 새 테스트는 `tests/` 아래 pytest로 작성.

## 파일 구조 (생성/수정)

- Create `config.base.yaml` — 비밀 아닌 운영 기본값(수집 소스·포맷·github pages_url·schedule). 커밋됨.
- Create `bootstrap_config.py` — `build_config()`/`ensure_config()`/`authenticated_remote_url()`/`setup_git_auth()`/`require_auth_or_die()`. 순수 로직 + git/파일 글루.
- Create `bootstrap.py` — Render 시작 시 1회 실행 엔트리포인트(`ensure_config` + `setup_git_auth`).
- Create `render.yaml` — Render Blueprint(서비스 정의, 자동배포 끔, 환경변수 키 목록).
- Create `.python-version` — `3.12.7`.
- Create `docs/HANDOFF.md` — 새 담당자 운영 가이드.
- Modify `requirements.txt` — `gunicorn` 추가.
- Modify `admin.py` — 시작 시 `ensure_config()` + 호스팅 무비번 차단 가드.
- Modify `main.py` — 시작 시 `ensure_config()` 호출(직접 실행 견고성).
- Create `tests/test_bootstrap_config.py` — 부트스트랩 단위 테스트.

---

### Task 1: `bootstrap_config.py` 핵심 로직 + 테스트

비밀 아닌 base 설정과 환경변수를 합쳐 config dict를 만들고, `config.yaml`이 없을 때만 생성한다. 인증 remote URL 생성과 호스팅 무비번 가드도 여기 둔다.

**Files:**
- Create: `bootstrap_config.py`
- Test: `tests/test_bootstrap_config.py`

**Interfaces:**
- Produces:
  - `build_config(base_path: Path, env: Mapping[str, str]) -> dict`
  - `ensure_config(config_path: Path = CONFIG_PATH, base_path: Path = BASE_PATH, env: Mapping[str, str] | None = None) -> Path`
  - `authenticated_remote_url(token: str, remote: str) -> str`
  - `require_auth_or_die(is_hosted: bool, password: str) -> None` (호스팅+빈 비번이면 `RuntimeError`)
  - 상수 `ENV_SECRETS: dict[str, tuple[str, str]]`, `CONFIG_PATH`, `BASE_PATH`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bootstrap_config.py
from pathlib import Path
import pytest
import yaml
import bootstrap_config as bc


def _write_base(tmp_path: Path) -> Path:
    base = tmp_path / "config.base.yaml"
    base.write_text(
        yaml.dump(
            {"anthropic": {"model": "claude-sonnet-4-6"},
             "gemini": {"model": "gemini-2.0-flash"},
             "github": {"enabled": True, "pages_url": "https://x.github.io/y"}},
            allow_unicode=True, sort_keys=False),
        encoding="utf-8")
    return base


def test_build_config_injects_secrets(tmp_path):
    base = _write_base(tmp_path)
    env = {"ANTHROPIC_API_KEY": "sk-ant-COMPANY",
           "GEMINI_API_KEY": "gm-COMPANY",
           "ADMIN_PASSWORD": "pw123",
           "FLASK_SECRET_KEY": "flask-secret"}
    cfg = bc.build_config(base, env)
    assert cfg["anthropic"]["api_key"] == "sk-ant-COMPANY"
    assert cfg["anthropic"]["model"] == "claude-sonnet-4-6"  # base 보존
    assert cfg["gemini"]["api_key"] == "gm-COMPANY"
    assert cfg["admin"]["password"] == "pw123"
    assert cfg["admin"]["secret_key"] == "flask-secret"


def test_build_config_skips_empty_env(tmp_path):
    base = _write_base(tmp_path)
    cfg = bc.build_config(base, {"ANTHROPIC_API_KEY": "  "})
    assert "api_key" not in cfg["anthropic"]


def test_ensure_config_creates_when_missing(tmp_path):
    base = _write_base(tmp_path)
    target = tmp_path / "config.yaml"
    bc.ensure_config(config_path=target, base_path=base,
                     env={"ANTHROPIC_API_KEY": "sk-ant-COMPANY"})
    assert target.exists()
    cfg = yaml.safe_load(target.read_text(encoding="utf-8"))
    assert cfg["anthropic"]["api_key"] == "sk-ant-COMPANY"


def test_ensure_config_preserves_existing(tmp_path):
    base = _write_base(tmp_path)
    target = tmp_path / "config.yaml"
    target.write_text("anthropic:\n  api_key: LOCAL_KEEP\n", encoding="utf-8")
    bc.ensure_config(config_path=target, base_path=base,
                     env={"ANTHROPIC_API_KEY": "sk-ant-COMPANY"})
    cfg = yaml.safe_load(target.read_text(encoding="utf-8"))
    assert cfg["anthropic"]["api_key"] == "LOCAL_KEEP"  # 덮어쓰지 않음


def test_authenticated_remote_url():
    assert bc.authenticated_remote_url("TOK", "github.com/o/r.git") == \
        "https://x-access-token:TOK@github.com/o/r.git"


def test_require_auth_or_die_blocks_hosted_without_password():
    with pytest.raises(RuntimeError):
        bc.require_auth_or_die(is_hosted=True, password="")


def test_require_auth_or_die_allows_local_without_password():
    bc.require_auth_or_die(is_hosted=False, password="")  # 예외 없음
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "G:/-업무/히즈/.claude/0. 데일리 뉴스레터" && python -m pytest tests/test_bootstrap_config.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'bootstrap_config'`)

- [ ] **Step 3: Write minimal implementation**

```python
# bootstrap_config.py
"""환경변수 기반 config.yaml 부트스트랩 + GitHub 인증 + 호스팅 가드.

호스팅 환경에서는 비밀 값을 환경변수로 주입하고 config.base.yaml(비밀 아닌 기본값)과
합쳐 config.yaml을 생성한다. 로컬 개발에서는 기존 config.yaml이 있으면 그대로 둔다.
"""
import os
import subprocess
from pathlib import Path
from typing import Mapping

import yaml

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.yaml"
BASE_PATH = BASE_DIR / "config.base.yaml"

# 환경변수 이름 -> config 내 (섹션, 키)
ENV_SECRETS: dict[str, tuple[str, str]] = {
    "ANTHROPIC_API_KEY": ("anthropic", "api_key"),
    "GEMINI_API_KEY": ("gemini", "api_key"),
    "ADMIN_PASSWORD": ("admin", "password"),
    "FLASK_SECRET_KEY": ("admin", "secret_key"),
}


def build_config(base_path: Path, env: Mapping[str, str]) -> dict:
    """base yaml을 읽고 환경변수의 비밀 값을 주입한 새 dict 반환."""
    with open(base_path, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    for env_name, (section, key) in ENV_SECRETS.items():
        value = (env.get(env_name) or "").strip()
        if value:
            config.setdefault(section, {})[key] = value
    return config


def ensure_config(config_path: Path = CONFIG_PATH, base_path: Path = BASE_PATH,
                  env: Mapping[str, str] | None = None) -> Path:
    """config.yaml이 없으면 base + 환경변수로 생성. 있으면 그대로 둠."""
    env = os.environ if env is None else env
    if config_path.exists():
        return config_path
    config = build_config(base_path, env)
    config_path.write_text(
        yaml.dump(config, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8")
    return config_path


def authenticated_remote_url(token: str, remote: str) -> str:
    """토큰을 박은 https git remote URL. remote 예: 'github.com/o/r.git'."""
    return f"https://x-access-token:{token}@{remote}"


def setup_git_auth(repo_dir: Path, env: Mapping[str, str] | None = None) -> bool:
    """GH_TOKEN이 있으면 origin remote URL과 git user를 설정. 성공 시 True."""
    env = os.environ if env is None else env
    token = (env.get("GH_TOKEN") or "").strip()
    if not token:
        return False
    remote = (env.get("GH_REMOTE")
              or "github.com/hizsystem/brandrise-kakao-newsletter.git").strip()
    url = authenticated_remote_url(token, remote)
    subprocess.run(["git", "remote", "set-url", "origin", url], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.name",
                    env.get("GIT_USER_NAME", "brandrise-bot")], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email",
                    env.get("GIT_USER_EMAIL", "bot@brandrise.local")], cwd=repo_dir, check=True)
    return True


def require_auth_or_die(is_hosted: bool, password: str) -> None:
    """호스팅 환경인데 관리자 비밀번호가 비어 있으면 기동을 막는다."""
    if is_hosted and not (password or "").strip():
        raise RuntimeError(
            "호스팅 환경에서 ADMIN_PASSWORD가 설정되지 않았습니다. "
            "공개 접근을 막기 위해 비밀번호를 환경변수로 설정하세요.")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "G:/-업무/히즈/.claude/0. 데일리 뉴스레터" && python -m pytest tests/test_bootstrap_config.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add bootstrap_config.py tests/test_bootstrap_config.py
git commit -m "feat: 환경변수 기반 config 부트스트랩 + git 인증 헬퍼"
```

---

### Task 2: `config.base.yaml` 생성 (비밀 제거)

현재 로컬 `config.yaml`의 운영 값은 그대로 쓰되 비밀 값만 비운 base 파일을 만든다. 실제 운영 값(neusral URL·pages_url·schedule·sites·format)은 로컬 `config.yaml`에서 그대로 복사한다.

**Files:**
- Create: `config.base.yaml`

**Interfaces:**
- Consumes: `bootstrap_config.build_config()`가 이 파일을 읽는다.
- Produces: 없음(데이터 파일).

- [ ] **Step 1: 현재 config.yaml에서 비밀 아닌 값 확인**

Run: `cd "G:/-업무/히즈/.claude/0. 데일리 뉴스레터" && python -c "import yaml,io,sys; sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8'); c=yaml.safe_load(open('config.yaml',encoding='utf-8')); print({k:(list(v.keys()) if isinstance(v,dict) else v) for k,v in c.items()})"`
Expected: 최상위 키 목록과 각 섹션 구조 출력(neusral URL·pages_url 등 확인용).

- [ ] **Step 2: `config.base.yaml` 작성**

다음 규칙으로 작성한다. **비밀 키는 넣지 않는다**(부트스트랩이 환경변수로 주입):
- `anthropic`: `model`만. `api_key` 제외.
- `gemini`: `model`만. `api_key` 제외.
- `admin`: 섹션 자체 생략(`password`·`secret_key`는 환경변수로 주입).
- `groq`/`openai`: 생략(폴백 미사용).
- `email`: 비밀(`password`) 제외하고 host/port/username만 두거나, 미사용이면 생략.
- `sites`/`neusral`/`tuesday_newsletters`/`builder_josh`/`friday_newsletters`/`email_newsletters`/`format`/`schedule`/`github`: 로컬 config.yaml의 실제 값을 그대로 복사.

예시 골격(실제 URL·값은 로컬 config.yaml에서 복사):

```yaml
anthropic:
  model: claude-sonnet-4-6
gemini:
  model: gemini-2.0-flash
schedule:
  send_time: "08:30"
sites:
  iboss:
    url: https://www.i-boss.co.kr/ab-7214
    schedule: daily
  neusral:
    url: "<로컬 config.yaml의 실제 neusral URL>"
    schedule: daily
  heypop:
    url: https://heypop.kr/
    schedule: thursday
tuesday_newsletters:
  putput: { url: "", name: 풋풋레터, sender_keyword: 풋풋 }
  careet: { url: "", name: 캐릿, sender_keyword: 캐릿 }
builder_josh:
  url: ""
  name: 빌더조쉬
friday_newsletters:
  catalogue: { url: "", name: 까탈로그, sender_keyword: 까탈로그 }
format:
  header_emoji: "\U0001F4CC"
  category_emoji: "\U0001F3F7️"
  date_format: "%m월 %d일"
  title_suffix: 마케팅 뉴스
github:
  enabled: true
  pages_url: "<로컬 config.yaml의 실제 pages_url>"
```

- [ ] **Step 3: base만으로 config 생성이 되는지 검증**

Run: `cd "G:/-업무/히즈/.claude/0. 데일리 뉴스레터" && python -c "import bootstrap_config as b; from pathlib import Path; c=b.build_config(Path('config.base.yaml'), {'ANTHROPIC_API_KEY':'X','GEMINI_API_KEY':'Y','ADMIN_PASSWORD':'Z','FLASK_SECRET_KEY':'W'}); print(c['anthropic']['api_key'], c['gemini']['api_key'], c['admin']['password'], c['github']['pages_url'])"`
Expected: `X Y Z <pages_url>` 출력, 예외 없음.

- [ ] **Step 4: base에 비밀이 없는지 확인**

Run: `cd "G:/-업무/히즈/.claude/0. 데일리 뉴스레터" && grep -nE "sk-ant|gsk_|sk-proj|AIza|password|secret_key" config.base.yaml || echo "NO SECRETS"`
Expected: `NO SECRETS`

- [ ] **Step 5: Commit**

```bash
git add config.base.yaml
git commit -m "feat: 비밀 제거한 config.base.yaml 추가"
```

---

### Task 3: `admin.py` — 시작 시 부트스트랩 + 호스팅 무비번 가드

호스팅 환경에서 `config.yaml`을 보장하고, 관리자 비밀번호 없이 공개되는 사고를 막는다. 기존 UI·라우트는 건드리지 않는다.

**Files:**
- Modify: `admin.py:41-54` (`_init_auth` 호출부 주변, `ADMIN_PASSWORD` 결정 지점)

**Interfaces:**
- Consumes: `bootstrap_config.ensure_config`, `bootstrap_config.require_auth_or_die`.

- [ ] **Step 1: import와 부트스트랩 호출 추가**

`admin.py` 상단 import 블록(`import yaml` 다음 줄 부근)에 추가:

```python
import os
import bootstrap_config
```

`app = Flask(__name__)` 직후, `CONFIG_PATH = ...` 정의 위 또는 아래에 추가:

```python
# 호스팅/로컬 모두: config.yaml이 없으면 환경변수로 생성
bootstrap_config.ensure_config()
```

- [ ] **Step 2: 호스팅 무비번 가드 추가**

기존 `ADMIN_PASSWORD, app.secret_key = _init_auth()` (admin.py:54) 바로 다음 줄에 추가:

```python
# Render 등 호스팅 환경에서 비밀번호 미설정 시 공개 노출 방지
_IS_HOSTED = bool(os.environ.get("RENDER"))
bootstrap_config.require_auth_or_die(_IS_HOSTED, ADMIN_PASSWORD)
```

- [ ] **Step 3: 로컬에서 import가 깨지지 않는지 확인**

Run: `cd "G:/-업무/히즈/.claude/0. 데일리 뉴스레터" && python -c "import admin; print('admin import OK')"`
Expected: `admin import OK` (로컬엔 config.yaml 존재, RENDER 미설정 → 가드 통과)

- [ ] **Step 4: 호스팅+무비번 시 기동 차단 확인**

Run: `cd "G:/-업무/히즈/.claude/0. 데일리 뉴스레터" && RENDER=1 ADMIN_PASSWORD= python -c "import importlib,sys; sys.modules.pop('admin',None); import admin" ; echo "exit=$?"`
Expected: `RuntimeError`로 비정상 종료(`exit=1`). 단 로컬 config.yaml에 admin.password가 이미 있으면 통과할 수 있으므로, 검증 시 로컬 config.yaml의 admin.password가 비어 있는 상태에서 확인하거나 이 단계는 Task 1 단위테스트(`require_auth_or_die`)로 대체 검증한다.

- [ ] **Step 5: Commit**

```bash
git add admin.py
git commit -m "feat: admin 시작 시 config 부트스트랩 + 호스팅 무비번 가드"
```

---

### Task 4: `main.py` — 직접 실행 시 config 보장

`admin.py`가 subprocess로 `main.py --now`를 호출할 때 config.yaml은 이미 존재하지만, 스케줄러/직접 실행 견고성을 위해 main.py 시작 시에도 보장한다.

**Files:**
- Modify: `main.py:32-41` (import 블록과 `load_config` 주변)

**Interfaces:**
- Consumes: `bootstrap_config.ensure_config`.

- [ ] **Step 1: import 추가**

`main.py`의 `from github_push import push_to_github` (main.py:32) 다음 줄에 추가:

```python
import bootstrap_config
```

- [ ] **Step 2: `load_config` 안에서 보장 호출**

기존 (main.py:39-41):

```python
def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)
```

다음으로 교체:

```python
def load_config() -> dict:
    bootstrap_config.ensure_config()
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)
```

- [ ] **Step 3: 동작 확인(수집기 테스트 모드)**

Run: `cd "G:/-업무/히즈/.claude/0. 데일리 뉴스레터" && python main.py --test`
Expected: 예외 없이 수집기 테스트 출력(네트워크 결과는 환경에 따라 다름). config 로딩 오류가 없어야 함.

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat: main.py load_config 시 config 부트스트랩 보장"
```

---

### Task 5: 프로덕션 서버 설정 (gunicorn + Render Blueprint)

gunicorn으로 `admin:app`을 서비스하고, Render Blueprint로 빌드/시작/환경변수를 선언한다. 자동배포는 끈다(콘텐츠 push가 재배포를 일으키지 않도록).

**Files:**
- Modify: `requirements.txt`
- Create: `bootstrap.py`
- Create: `render.yaml`
- Create: `.python-version`

**Interfaces:**
- Consumes: `bootstrap_config.ensure_config`, `bootstrap_config.setup_git_auth`.

- [ ] **Step 1: `requirements.txt`에 gunicorn 추가**

기존 마지막 줄(`flask>=3.0.0`) 다음에 추가:

```
gunicorn>=21.2.0
```

- [ ] **Step 2: `.python-version` 작성**

```
3.12.7
```

- [ ] **Step 3: `bootstrap.py` 작성**

```python
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
```

- [ ] **Step 4: `render.yaml` 작성**

```yaml
services:
  - type: web
    name: brandrise-newsletter-admin
    runtime: python
    plan: free
    autoDeploy: false
    buildCommand: pip install -r requirements.txt
    startCommand: python bootstrap.py && gunicorn admin:app --bind 0.0.0.0:$PORT --workers 1 --timeout 900
    envVars:
      - key: RENDER
        value: "1"
      - key: ANTHROPIC_API_KEY
        sync: false
      - key: GEMINI_API_KEY
        sync: false
      - key: ADMIN_PASSWORD
        sync: false
      - key: FLASK_SECRET_KEY
        sync: false
      - key: GH_TOKEN
        sync: false
      - key: GIT_USER_NAME
        sync: false
      - key: GIT_USER_EMAIL
        sync: false
```

(`sync: false` = Render 대시보드에서 수동 입력하는 비밀 값. `RENDER=1`은 호스팅 가드 활성화용.)

- [ ] **Step 5: 로컬에서 gunicorn 기동 스모크 테스트(선택, gunicorn은 Linux 전용 — Windows면 생략하고 Render에서 확인)**

Windows 로컬에서는 gunicorn이 안 도므로 import만 확인:
Run: `cd "G:/-업무/히즈/.claude/0. 데일리 뉴스레터" && python -c "import admin; print(type(admin.app))"`
Expected: `<class 'flask.app.Flask'>`

- [ ] **Step 6: Commit**

```bash
git add requirements.txt bootstrap.py render.yaml .python-version
git commit -m "feat: gunicorn + Render Blueprint 배포 설정"
```

---

### Task 6: 회사 API 키 발급 + Render 배포 (수동 운영 작업)

코드가 아닌 외부 콘솔 작업이다. 테스트 사이클 없음 — 각 항목 완료를 체크한다.

**Files:** 없음(운영).

- [ ] **Step 1: 회사 Anthropic 키 발급**
  - 회사 Anthropic Console → API Keys → 새 키 생성 → 안전한 곳에 복사. (회사 결제수단 청구 확인.)

- [ ] **Step 2: 회사 Gemini 키 발급**
  - 회사 Google 계정 → Google AI Studio(`aistudio.google.com/apikey`)에서 새 키 발급. (코드가 `generativelanguage.googleapis.com`를 쓰므로 AI Studio 키여야 함.)

- [ ] **Step 3: GitHub fine-grained PAT 발급**
  - GitHub → Settings → Developer settings → Fine-grained tokens → 새 토큰.
  - Repository access: `hizsystem/brandrise-kakao-newsletter`만.
  - Permissions: Contents = Read and write.
  - 만료일 설정 후 토큰 복사.

- [ ] **Step 4: Render에 저장소 연결 + Blueprint 배포**
  - Render 대시보드 → New → Blueprint → 저장소 선택 → `render.yaml` 인식 확인.
  - 환경변수(`sync: false` 항목) 값 입력:
    - `ANTHROPIC_API_KEY` = Step 1 키
    - `GEMINI_API_KEY` = Step 2 키
    - `ADMIN_PASSWORD` = 새 강한 비밀번호
    - `FLASK_SECRET_KEY` = 랜덤 64자(예: `python -c "import secrets;print(secrets.token_hex(32))"`)
    - `GH_TOKEN` = Step 3 토큰
    - `GIT_USER_NAME` = `brandrise-bot` (또는 임의)
    - `GIT_USER_EMAIL` = 회사 이메일
  - 배포 실행.

- [ ] **Step 5: 배포 검증**
  - 공개 URL 접속 → 로그인 페이지가 뜨는지(비번 강제) 확인.
  - 로그인 후 URL 붙여넣고 "저장+생성" → 1~2분 후 로그에 성공 출력 확인.
  - GitHub Pages(`pages_url`)에 오늘 뉴스레터가 갱신됐는지 확인.
  - **확인 항목**: Render 런타임에서 `git push`가 성공하는지(로그 `[OK] GitHub Pages 업데이트 완료`). 실패 시 `setup_git_auth`의 remote가 적용됐는지, 토큰 권한이 Contents write인지 점검. `.git`이 없으면 startCommand에 `git clone`/`git init + remote add` 보강이 필요할 수 있음.

- [ ] **Step 6: 개인 키 폐기**
  - 동작 확인 후 기존 **개인 Anthropic 키**·**개인 Gemini 키**를 각 콘솔에서 revoke.
  - 로컬 `config.yaml`의 키도 회사 키 또는 빈 값으로 정리(로컬은 git에 안 올라가므로 선택).

---

### Task 7: 인수인계 문서 `docs/HANDOFF.md`

새 담당자가 코드 없이 매일 운영할 수 있는 한 장짜리 가이드.

**Files:**
- Create: `docs/HANDOFF.md`

- [ ] **Step 1: 문서 작성**

```markdown
# 데일리 뉴스레터 운영 가이드

## 매일 아침 루틴
1. 관리 링크 열기: <Render URL> (첫 접속 시 ~50초 로딩될 수 있음)
2. 비밀번호로 로그인
3. 오늘 해당하는 URL 붙여넣기 (아래 요일표 참고)
4. **저장 + 뉴스레터 지금 생성** 클릭
5. 1~2분 후 화면 하단 로그 박스에 생성 결과가 뜨면, 텍스트를 복사
6. 카카오톡 오픈채팅에 붙여넣기

## 요일별 입력 URL
| 요일 | 입력할 것 | 어디서 |
|------|-----------|--------|
| 매일 | 롱블랙 티켓 URL | 롱블랙 이메일 → "아티클 읽기" 링크 (ticket= 포함) |
| 화 | 풋풋레터·캐릿 URL | 각 이메일 → "웹으로 보기" 링크 |
| 수·금 | 빌더조쉬 URL | maily.so/josh 이번 주 글 (수·금 각각 새 URL로 덮어쓰기) |
| 금 | 까탈로그 URL | 까탈로그 이메일 → "웹으로 보기" |
| 목 | (헤이팝) | 자동 — 입력 불필요 |
| 매일 | (아이보스·뉴스럴) | 자동 — 입력 불필요 |

## 정부지원사업 공고 발행
관리 페이지 하단 "정부지원사업 공고 발행"에 공지 문구와 공고 목록을 붙여넣고 발행 버튼 클릭.

## 지난 뉴스레터
관리 페이지의 "지난 뉴스레터" 또는 공개 사이트: <pages_url>

## 막힐 때
- 첫 접속이 느린 건 정상(무료 호스팅 절전). 잠시 기다리면 됨.
- 생성 실패/오류 로그가 뜨면 <담당자 연락처>에 로그 캡처와 함께 문의.
```

`<Render URL>`·`<pages_url>`·`<담당자 연락처>`는 실제 값으로 채운다.

- [ ] **Step 2: Commit**

```bash
git add docs/HANDOFF.md
git commit -m "docs: 새 담당자 운영 가이드 추가"
```

---

## Self-Review

**Spec coverage:**
- 관리 시스템 호스팅 링크 → Task 5(gunicorn/Render) + Task 6(배포). ✅
- 비밀키 환경변수화 → Task 1·2(bootstrap + base) + Task 3·4(wiring). ✅
- API 회사 계정 이전(Anthropic+Gemini) → Task 6 Step 1·2·6. ✅
- GitHub Pages 발행(서버) → Task 1(`setup_git_auth`) + Task 5(bootstrap.py) + Task 6 Step 3·5. ✅
- 보안(비번 필수·FLASK_SECRET_KEY) → Task 1(`require_auth_or_die`) + Task 2(admin 섹션 환경변수) + Task 3(가드). ✅
- 인수인계 문서 → Task 7. ✅
- 자동배포 끄기 → Task 5 render.yaml `autoDeploy: false`. ✅

**Placeholder scan:** `config.base.yaml`·`HANDOFF.md`의 `<...>`는 환경 고유 데이터(실제 URL·연락처)로, 채우는 규칙과 추출 명령을 함께 제시함 — 코드 자리표시자 아님. 그 외 코드 단계는 모두 완전한 코드 포함.

**Type consistency:** `ensure_config`/`build_config`/`authenticated_remote_url`/`setup_git_auth`/`require_auth_or_die` 시그니처가 정의(Task 1)와 호출부(Task 3·4·5)에서 일치. 환경변수 이름이 Global Constraints·`ENV_SECRETS`·`render.yaml`에서 동일.

**미해결(구현 중 확인):** Render 런타임의 `.git` 유지 여부(Task 6 Step 5에 점검 포함). 미유지 시 startCommand에 git 초기화/clone 보강.
