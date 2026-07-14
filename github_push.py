"""
GitHub Pages 자동 푸시
docs/ 폴더 변경사항을 git commit + push
"""
import subprocess
from pathlib import Path


def push_to_github(repo_dir: Path, date_str: str) -> bool:
    """
    docs/ 변경사항을 GitHub에 커밋·푸시.
    성공 여부 반환.

    push 직전에 아카이브 동기화 가드를 자동 실행한다. v1/v2 아카이브 목록이
    어긋나 있으면(2026-05-27/28 병합충돌 누락 같은 사고) push 자체를 막는다.
    """
    # --- 아카이브 동기화 가드 (사람 기억 대신 자동 차단) ---
    from archive_sync import check_archive_sync

    ok_sync, sync_msg = check_archive_sync(repo_dir / "docs")
    if not ok_sync:
        print(f"  [BLOCK] 아카이브 동기화 검증 실패 — push 중단:\n  {sync_msg}")
        return False
    print(f"  [OK] {sync_msg}")

    def run(cmd: list, timeout: int = 60) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                cmd, cwd=repo_dir,
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=timeout,
            )
            return result.returncode == 0, (result.stdout + result.stderr).strip()
        except subprocess.TimeoutExpired as e:
            partial = ((e.stdout or "") + (e.stderr or "")).strip()
            return False, f"timeout {timeout}s: {' '.join(cmd)}\n{partial}"

    # git add docs/
    ok, out = run(["git", "add", "docs/"])
    if not ok:
        print(f"  [WARN] git add 실패: {out}")
        return False

    # git commit
    ok, out = run(["git", "commit", "-m", f"newsletter: {date_str}"])
    if not ok:
        if "nothing to commit" in out:
            print("  [INFO] 변경 없음, 푸시 생략")
            return True
        print(f"  [WARN] git commit 실패: {out}")
        return False

    # 스테일 체크아웃(Render 등 호스팅 스냅샷) 대비: push 전에 원격 최신화.
    # 충돌 시 방금 생성한 산출물 우선(-X theirs = 리베이스되는 우리 커밋 쪽).
    ok, out = run(["git", "fetch", "origin", "main"], timeout=60)
    if ok:
        ok_rb, out_rb = run(["git", "rebase", "-X", "theirs", "origin/main"], timeout=60)
        if not ok_rb:
            run(["git", "rebase", "--abort"])
            print(f"  [WARN] rebase 실패 — 기존 HEAD로 푸시 시도: {out_rb.splitlines()[-1] if out_rb else ''}")
    else:
        print(f"  [WARN] fetch 실패 — 기존 HEAD로 푸시 시도: {out}")

    # git push (네트워크 지연/자격증명 대기 등으로 멈추는 것 방지: 120초)
    # 호스팅 체크아웃은 detached HEAD일 수 있어 HEAD:main으로 명시 푸시.
    ok, out = run(["git", "push", "origin", "HEAD:main"], timeout=120)
    if not ok:
        print(f"  [WARN] git push 실패: {out}")
        print("         수동으로 실행: git push")
        return False

    print(f"  [OK] GitHub Pages 업데이트 완료 ({date_str})")
    return True
