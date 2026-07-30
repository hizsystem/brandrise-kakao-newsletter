# -*- coding: utf-8 -*-
"""인사말 컨텍스트(직전 발행일·최근 인사말·신규 코너)의 소스 검증.

output_*.txt는 .gitignore 대상이라 CI 러너·다른 PC에는 존재하지 않는다.
발행 이력은 커밋되는 docs/v2/newsletters/YYYY-MM-DD.html에서 읽어야 한다.
"""
from datetime import date, datetime

import pytest

import formatter as F


TODAY = date(2026, 7, 30)


def _docs(tmp_path, *dates_and_bodies):
    """docs/v2/newsletters 흉내 — (YYYY-MM-DD, 본문) 튜플로 html 생성"""
    d = tmp_path / "docs" / "v2" / "newsletters"
    d.mkdir(parents=True)
    for name, body in dates_and_bodies:
        (d / f"{name}.html").write_text(body, encoding="utf-8")
    return d


def _outputs(tmp_path, *names_and_bodies):
    d = tmp_path / "out"
    d.mkdir()
    for name, body in names_and_bodies:
        (d / name).write_text(body, encoding="utf-8")
    return d


@pytest.fixture
def fixed_today(monkeypatch):
    monkeypatch.setattr(F, "now_kst", lambda: datetime(2026, 7, 30, 10, 0))


def test_gap_read_from_committed_docs(tmp_path, monkeypatch, fixed_today):
    """output_*.txt가 하나도 없어도(=CI 러너) 직전 발행일을 알아야 한다."""
    monkeypatch.setattr(F, "_DOCS_NEWSLETTER_DIR", _docs(tmp_path, ("2026-07-29", "<p>x</p>")))
    monkeypatch.setattr(F, "_OUTPUT_DIR", _outputs(tmp_path))

    assert F._days_since_last_newsletter(TODAY) == 1


def test_stale_output_txt_does_not_fake_a_long_gap(tmp_path, monkeypatch, fixed_today):
    """로컬 output이 2주 밀려 있어도 docs가 최신이면 gap은 1일이다.

    2026-07-30 허위 연휴 인사말의 원인 — gap 16일로 계산돼 연휴 노트가 발동했다.
    """
    docs = _docs(
        tmp_path,
        ("2026-07-27", "<p>x</p>"),
        ("2026-07-28", "<p>x</p>"),
        ("2026-07-29", "<p>x</p>"),
    )
    monkeypatch.setattr(F, "_DOCS_NEWSLETTER_DIR", docs)
    monkeypatch.setattr(F, "_OUTPUT_DIR", _outputs(tmp_path, ("output_20260714.txt", "안녕하세요!")))

    assert F._days_since_last_newsletter(TODAY) == 1


def test_gap_survives_when_only_output_txt_exists(tmp_path, monkeypatch, fixed_today):
    """docs가 없는 환경(신규 클론 전 단계)에서는 output_*.txt를 계속 쓴다."""
    monkeypatch.setattr(F, "_DOCS_NEWSLETTER_DIR", tmp_path / "없음")
    monkeypatch.setattr(F, "_OUTPUT_DIR", _outputs(tmp_path, ("output_20260729.txt", "안녕하세요!")))

    assert F._days_since_last_newsletter(TODAY) == 1


def test_real_holiday_gap_still_detected(tmp_path, monkeypatch, fixed_today):
    """진짜 공백은 여전히 잡혀야 한다 — 무조건 1을 반환하는 구현 방지."""
    monkeypatch.setattr(F, "_DOCS_NEWSLETTER_DIR", _docs(tmp_path, ("2026-07-24", "<p>x</p>")))
    monkeypatch.setattr(F, "_OUTPUT_DIR", _outputs(tmp_path))

    assert F._days_since_last_newsletter(TODAY) == 6


def test_recent_greetings_read_from_committed_docs(tmp_path, monkeypatch, fixed_today):
    """CI에서도 최근 인사말을 읽어 중복 회피 컨텍스트가 살아 있어야 한다."""
    html = (
        '<div class="v2-header"><div class="v2-greeting">'
        "<p>안녕하세요! 수요일 마케팅 소식 전해드립니다 😊 어제의 소재입니다.</p>"
        "<p>두 번째 문단입니다.</p>"
        "</div></div><div class=\"v2-card\">기사 본문은 섞이면 안 된다</div>"
    )
    monkeypatch.setattr(F, "_DOCS_NEWSLETTER_DIR", _docs(tmp_path, ("2026-07-29", html)))
    monkeypatch.setattr(F, "_OUTPUT_DIR", _outputs(tmp_path))

    got = F._load_recent_greetings(n=4)

    assert len(got) == 1
    assert "안녕하세요! 수요일 마케팅 소식" in got[0]
    assert "두 번째 문단입니다." in got[0]
    assert "기사 본문" not in got[0]


def test_recent_greetings_prefers_output_txt_for_same_date(tmp_path, monkeypatch, fixed_today):
    """같은 날짜가 양쪽에 있으면 원문(txt)을 쓰고 중복 적재하지 않는다."""
    html = '<div class="v2-greeting"><p>안녕하세요! HTML 버전</p></div>'
    monkeypatch.setattr(F, "_DOCS_NEWSLETTER_DIR", _docs(tmp_path, ("2026-07-29", html)))
    monkeypatch.setattr(
        F, "_OUTPUT_DIR",
        _outputs(tmp_path, ("output_20260729.txt", "안녕하세요! TXT 버전\n\n🔗 링크\nhttps://x")),
    )

    got = F._load_recent_greetings(n=4)

    assert len(got) == 1
    assert "TXT 버전" in got[0]


def test_first_appearance_checks_committed_docs(tmp_path, monkeypatch, fixed_today):
    """output이 없어도 과거 HTML에 등장한 코너는 '오늘 처음'이 아니다."""
    class _Item:
        source = "빌더조쉬"

    monkeypatch.setattr(
        F, "_DOCS_NEWSLETTER_DIR",
        _docs(tmp_path, ("2026-07-29", "<p>빌더조쉬 소식입니다</p>")),
    )
    monkeypatch.setattr(F, "_OUTPUT_DIR", _outputs(tmp_path))

    assert F._first_appearance_sources([_Item()]) == []


def test_first_appearance_still_reports_genuinely_new_source(tmp_path, monkeypatch, fixed_today):
    class _Item:
        source = "처음보는레터"

    monkeypatch.setattr(
        F, "_DOCS_NEWSLETTER_DIR",
        _docs(tmp_path, ("2026-07-29", "<p>빌더조쉬 소식입니다</p>")),
    )
    monkeypatch.setattr(F, "_OUTPUT_DIR", _outputs(tmp_path))

    assert F._first_appearance_sources([_Item()]) == ["처음보는레터"]
