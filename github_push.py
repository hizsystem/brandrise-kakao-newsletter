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
    """
    def run(cmd: list) -> tuple[bool, str]:
        result = subprocess.run(
            cmd, cwd=repo_dir,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        return result.returncode == 0, (result.stdout + result.stderr).strip()

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

    # git push
    ok, out = run(["git", "push", "--set-upstream", "origin", "main"])
    if not ok:
        print(f"  [WARN] git push 실패: {out}")
        print("         수동으로 실행: git push")
        return False

    print(f"  [OK] GitHub Pages 업데이트 완료 ({date_str})")
    return True
