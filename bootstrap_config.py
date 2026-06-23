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
