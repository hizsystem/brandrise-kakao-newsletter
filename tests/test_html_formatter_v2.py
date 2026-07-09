# -*- coding: utf-8 -*-
from collectors.iboss import NewsItem
import html_formatter_v2 as H


def _items():
    return [
        NewsItem(title="네이버 플레이스광고 확대", summary="최대 18개로", url="https://ex.com/a1"),
        NewsItem(title="생성형 AI 검색", summary="챗GPT 4위", url="https://ex.com/a2"),
    ]


def test_iboss_items_are_clickable_links():
    html = H._render_iboss_v2(_items(), post_url="https://iboss.example/post")
    assert 'href="https://ex.com/a1"' in html
    assert 'href="https://ex.com/a2"' in html
    assert html.count('class="v2-item"') == 2
    assert 'v2-item-rank' in html  # 순위 배지


def test_iboss_falls_back_to_post_url_when_item_url_empty():
    items = [NewsItem(title="제목", summary="요약", url="")]
    html = H._render_iboss_v2(items, post_url="https://iboss.example/post")
    assert 'href="https://iboss.example/post"' in html


def test_iboss_uses_thumbnail_when_image_map_given():
    html = H._render_iboss_v2(_items(), image_map={1: "images/x/iboss-1.png"})
    assert 'src="images/x/iboss-1.png"' in html


def test_bottom_cta_copy_and_utm():
    cta = H.BRANDRISE_CTA_HTML
    assert "혼자 고민하지 마세요." in cta
    assert "30분 무료 상담에서 함께 정리해드려요." in cta
    assert "이미 <b>수십 개 브랜드</b>가 상담받았습니다." in cta
    assert "함께 고민하는 팀원의 마음으로 봅니다." in cta
    assert "utm_source=web" in cta
    assert "utm_content=bottom" in cta
    assert "utm_source=kakao" not in cta  # 웹 링크가 kakao로 오집계되던 버그 제거


def test_top_entry_utm_and_copy():
    entry = H.BRANDRISE_ENTRY_HTML
    assert "utm_content=top" in entry
    assert "utm_source=web" in entry
    assert "막막하다면" in entry
