"""
오늘 발행분의 아이보스 AI 이미지만 재생성 + 기존 HTML에 주입.
- 텍스트/인사말/뉴스럴/스티비/롱블랙 등 발행 내용은 일절 건드리지 않는다.
- output_YYYYMMDD.txt에서 아이보스 제목+요약을 복원 → Gemini 이미지 생성
- docs/v2/newsletters/{date}.html(서브페이지) + docs/v2/index.html(루트) 의
  아이보스 그라디언트 썸네일을 생성된 이미지 썸네일로 교체.

이미지 생성이 API 한도초과로 깨진 날, 텍스트는 살리고 이미지만 복구하기 위한 외과적 스크립트.
"""
import sys
import io
import re
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

import yaml

from collectors.iboss import NewsItem
from image_gen import generate_iboss_images

BASE = Path(__file__).parent


def load_keys() -> tuple[str, str]:
    cfg = yaml.safe_load((BASE / "config.yaml").read_text(encoding="utf-8"))
    anthropic_key = cfg.get("anthropic", {}).get("api_key", "")
    gemini_key = cfg.get("gemini", {}).get("api_key", "")
    return anthropic_key, gemini_key


def parse_iboss_items(date_iso: str) -> list[NewsItem]:
    """output_YYYYMMDD.txt에서 아이보스 1~7번 (제목 + 요약) 복원."""
    txt_path = BASE / f"output_{date_iso.replace('-', '')}.txt"
    lines = txt_path.read_text(encoding="utf-8").splitlines()

    items: list[NewsItem] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("🏷️"):
            break  # 아이보스 섹션 끝
        m = re.match(r"^(\d+)\.\s+(.*)$", line)
        if m and 1 <= int(m.group(1)) <= 7 and len(m.group(2)) > 5:
            title = m.group(2).strip()
            # 다음 비어있지 않은 줄 = 요약 (다음 번호/카테고리 전까지)
            summary = ""
            j = i + 1
            while j < len(lines):
                nxt = lines[j].strip()
                if not nxt:
                    j += 1
                    continue
                if re.match(r"^\d+\.\s+", nxt) or nxt.startswith("🏷️"):
                    break
                summary = nxt
                break
            items.append(NewsItem(title=title, summary=summary))
        i += 1
    return items


def inject_images(html_path: Path, image_map: dict, is_subpage: bool) -> int:
    """그라디언트 썸네일을 이미지 썸네일로 교체. 교체 건수 반환.

    리디자인(v2-item 리스트) 마크업 기준. 이미지 생성 실패 시 렌더된
    그라디언트 폴백 썸네일(v2-item-thumb-grad)을 재생성 이미지로 외과적 교체.
    """
    html = html_path.read_text(encoding="utf-8")
    prefix = "../" if is_subpage else ""

    replaced = 0
    # 카드 순서대로 1..N. v2-item-rank">{i}</span> 를 anchor로 해당 그라디언트 썸네일 1개만 교체.
    for i in sorted(image_map):
        rel = image_map[i]  # "images/2026-06-09/iboss-i.png"
        new_thumb = (
            f'<span class="v2-item-thumbwrap">'
            f'<img class="v2-item-thumb" src="{prefix}{rel}" alt="" loading="lazy">'
            f'<span class="v2-item-rank">{i}</span></span>'
        )
        # 해당 번호의 그라디언트 폴백 썸네일 1건만 교체 (thumbwrap 내부: grad span + rank span)
        pat = re.compile(
            r'<span class="v2-item-thumbwrap">'
            r'<span class="v2-item-thumb v2-item-thumb-grad"[^>]*>[^<]*</span>'
            r'<span class="v2-item-rank">' + str(i) + r'</span></span>',
            re.DOTALL,
        )
        html, n = pat.subn(new_thumb, html, count=1)
        replaced += n
        if n == 0:
            print(f"  [WARN] {html_path.name}: {i}번 썸네일 패턴 매칭 실패")
    html_path.write_text(html, encoding="utf-8")
    return replaced


def main(date_iso: str):
    print(f"=== {date_iso} 아이보스 이미지 재생성 ===\n")
    anthropic_key, gemini_key = load_keys()
    if not gemini_key:
        print("  [ERROR] gemini 키 없음 — 중단")
        return

    items = parse_iboss_items(date_iso)
    print(f"아이보스 {len(items)}개 복원:")
    for k, it in enumerate(items, 1):
        print(f"  {k}. {it.title[:45]}")
    if not items:
        print("  [ERROR] 아이보스 항목 복원 실패 — 중단")
        return

    docs_dir = BASE / "docs"
    print("\n이미지 생성 중...\n")
    image_map = generate_iboss_images(items, docs_dir, date_iso, anthropic_key, gemini_key)
    print(f"\n생성 완료: {len(image_map)}/{len(items)}개")
    if not image_map:
        print("  [ERROR] 이미지가 하나도 생성되지 않음 — HTML 미수정")
        return

    sub = docs_dir / "v2" / "newsletters" / f"{date_iso}.html"
    idx = docs_dir / "v2" / "index.html"
    n1 = inject_images(sub, image_map, is_subpage=True)
    n2 = inject_images(idx, image_map, is_subpage=False)
    print(f"\nHTML 주입: 서브페이지 {n1}건, 인덱스 {n2}건")
    print("완료.")


if __name__ == "__main__":
    date = sys.argv[1] if len(sys.argv) > 1 else None
    if not date:
        from timeutil import now_kst
        date = now_kst().strftime("%Y-%m-%d")
    main(date)
