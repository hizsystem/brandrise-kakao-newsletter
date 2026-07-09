# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, str(__file__).rsplit('tests', 1)[0].rstrip('\\'))

import image_gen as G


def test_style_constants_are_toss_flat():
    combined = (G.STYLE_PREFIX + G.STYLE_SUFFIX)
    assert "#3182F6" in combined
    assert "flat" in combined.lower() or "Toss" in combined
    # 기존 핑크/민트 팔레트 잔재 없음
    assert "#FFB5C8" not in combined
    assert "pink" not in combined.lower()
    assert "mint" not in combined.lower()


def test_fallback_prompt_wraps_with_style():
    p = G._build_fallback_prompt("쿠팡 멤버십 확대")
    assert p.startswith(G.STYLE_PREFIX)
    assert p.endswith(G.STYLE_SUFFIX)
