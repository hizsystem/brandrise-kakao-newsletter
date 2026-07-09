# -*- coding: utf-8 -*-
import formatter as F


def test_kakao_footer_new_tone_keeps_kakao_utm():
    foot = F.BRANDRISE_FOOTER
    assert "혼자 고민하지 마세요" in foot
    assert "30분 무료 상담" in foot
    assert "utm_source=kakao" in foot   # 카톡은 kakao 유지
    assert "utm_source=web" not in foot
