"""
아카이브 동기화 가드 (자동)

docs/archive.html (v1) 와 docs/v2/archive.html (v2) 가 동일한 뉴스레터
엔트리 집합을 갖는지, 그리고 실제 뉴스레터 파일과 일치하는지 검증한다.

배경: 2026-05-27/28 호가 코드 병합 충돌로 한쪽 목록에서 누락된 사고.
"습관적 수동 점검" 대신 push 직전(github_push.py)에 자동 호출되어,
불일치 시 push 자체를 막는다. 사람 기억에 의존하지 않는 것이 핵심.

단독 실행:  python archive_sync.py [docs_dir]   (기본 docs_dir = ./docs)
종료코드 0=정상, 1=불일치/손상.
"""
import re
import sys
from pathlib import Path

# 각 아카이브 엔트리는 newsletters/YYYY-MM-DD.html 형태의 링크를 가진다.
ENTRY_RE = re.compile(r"newsletters/(\d{4}-\d{2}-\d{2})\.html")
DATE_STEM_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _entries_in_html(path: Path) -> set:
    """아카이브 HTML에서 뉴스레터 날짜(엔트리) 집합 추출."""
    if not path.exists():
        return set()
    return set(ENTRY_RE.findall(path.read_text(encoding="utf-8")))


def _newsletter_files(newsletters_dir: Path) -> set:
    """실제 발행된 뉴스레터 파일 날짜 집합 (소스 오브 트루스)."""
    if not newsletters_dir.exists():
        return set()
    return {
        f.stem for f in newsletters_dir.glob("*.html") if DATE_STEM_RE.match(f.stem)
    }


def check_archive_sync(docs_dir) -> tuple[bool, str]:
    """
    (ok, message) 반환.
    - v1 / v2 아카이브 엔트리 집합 불일치 검출
    - 실제 뉴스레터 파일이 두 목록에 모두 들어있는지 교차검증
    - 엔트리가 0개면 파서/파일 손상으로 간주(가드 무력화 방지)
    """
    docs_dir = Path(docs_dir)
    v1 = _entries_in_html(docs_dir / "archive.html")
    v2 = _entries_in_html(docs_dir / "v2" / "archive.html")
    source = _newsletter_files(docs_dir / "v2" / "newsletters")

    if not v1 and not v2:
        return False, "아카이브 엔트리를 하나도 찾지 못함 — 파서 또는 파일 손상 의심"

    problems = []
    only_v1 = sorted(v1 - v2)
    only_v2 = sorted(v2 - v1)
    if only_v1:
        problems.append(f"v1(archive.html)에만 있음: {only_v1}")
    if only_v2:
        problems.append(f"v2(v2/archive.html)에만 있음: {only_v2}")

    if source:
        miss_v1 = sorted(source - v1)
        miss_v2 = sorted(source - v2)
        if miss_v1:
            problems.append(f"실제 뉴스레터가 v1 목록에 누락: {miss_v1}")
        if miss_v2:
            problems.append(f"실제 뉴스레터가 v2 목록에 누락: {miss_v2}")

    if problems:
        summary = (
            f"아카이브 불일치 (v1={len(v1)}개, v2={len(v2)}개, 실제={len(source)}개)\n  - "
            + "\n  - ".join(problems)
            + "\n  → main.py의 _rebuild_archives 로 재생성 후 다시 시도하세요."
        )
        return False, summary

    return True, f"아카이브 동기화 정상 (v1=v2={len(v1)}개, 실제 파일 {len(source)}개)"


def main() -> int:
    docs_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "docs"
    ok, msg = check_archive_sync(docs_dir)
    print(f"{'[OK]' if ok else '[FAIL]'} {msg}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
