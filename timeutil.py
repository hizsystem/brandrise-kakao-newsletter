"""
시간대 유틸 — 모든 날짜/시각 계산을 한국시간(KST) 기준으로 고정.

배경: Render 등 클라우드 호스팅은 서버 시계가 UTC다. 코드 전반이
`datetime.now()`(로컬 시각)를 쓰면, UTC 서버에서는 날짜·요일·시간대가
9시간 어긋난다. 특히 아침 08:30 KST 발송은 UTC로 전날 23:30이라
날짜·요일이 하루 밀려 요일 기반 수집 소스 선택이 통째로 깨진다.

KST는 1988년 이후 서머타임이 없어 항상 UTC+9 고정이므로,
tzdata 의존성 없이 고정 오프셋으로 안전하게 처리한다.
반환값은 tzinfo 없는 naive datetime(= KST 벽시계 시각)이라
기존 `datetime.now()` 호출부에 그대로 대체 가능하다.
"""
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))


def now_kst() -> datetime:
    """현재 한국시간(KST)을 naive datetime으로 반환. datetime.now() 대체용."""
    return datetime.now(KST).replace(tzinfo=None)
