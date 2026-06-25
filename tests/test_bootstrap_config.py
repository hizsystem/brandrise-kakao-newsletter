from pathlib import Path
import subprocess
import sys

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
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


def _git_remote_url(repo: Path) -> str:
    return subprocess.run(["git", "remote", "get-url", "origin"], cwd=repo,
                          capture_output=True, text=True).stdout.strip()


def test_setup_git_auth_adds_origin_when_missing(tmp_path):
    # Render 체크아웃처럼 .git은 있으나 origin remote가 없는 상태
    subprocess.run(["git", "init"], cwd=tmp_path, check=True,
                   capture_output=True)
    env = {"GH_TOKEN": "TOK", "GH_REMOTE": "github.com/o/r.git"}
    assert bc.setup_git_auth(tmp_path, env) is True
    assert _git_remote_url(tmp_path) == "https://x-access-token:TOK@github.com/o/r.git"


def test_setup_git_auth_updates_existing_origin(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", "https://old/x.git"],
                   cwd=tmp_path, check=True, capture_output=True)
    env = {"GH_TOKEN": "TOK", "GH_REMOTE": "github.com/o/r.git"}
    assert bc.setup_git_auth(tmp_path, env) is True
    assert _git_remote_url(tmp_path) == "https://x-access-token:TOK@github.com/o/r.git"


def test_setup_git_auth_inits_when_no_git(tmp_path):
    # .git이 아예 없는 경우 init 후 origin 추가
    env = {"GH_TOKEN": "TOK", "GH_REMOTE": "github.com/o/r.git"}
    assert bc.setup_git_auth(tmp_path, env) is True
    assert (tmp_path / ".git").exists()
    assert _git_remote_url(tmp_path) == "https://x-access-token:TOK@github.com/o/r.git"


def test_setup_git_auth_returns_false_without_token(tmp_path):
    assert bc.setup_git_auth(tmp_path, {}) is False
