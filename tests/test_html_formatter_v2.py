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
