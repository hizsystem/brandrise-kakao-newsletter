"""
메일플러그 IMAP 이메일 뉴스레터 파서
롱블랙, 풋풋레터, 캐릿, 까탈로그 등 이메일 구독 뉴스레터 수신
"""

import base64
import imaplib
import email
import re
import requests
from email.header import decode_header
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import Optional
from datetime import datetime, timedelta
from timeutil import now_kst


@dataclass
class EmailNewsletter:
    source: str          # 뉴스레터 출처
    subject: str         # 제목
    summary: str         # 요약 또는 주요 내용
    link: str            # 원문 링크 (있는 경우)
    received_at: datetime


class MailplugReader:
    def __init__(self, host: str, port: int, username: str, password: str):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self._conn: Optional[imaplib.IMAP4_SSL] = None

    def connect(self):
        self._conn = imaplib.IMAP4_SSL(self.host, self.port)
        self._conn.login(self.username, self.password)

    def disconnect(self):
        if self._conn:
            try:
                self._conn.logout()
            except Exception:
                pass

    def fetch_newsletter(self, sender_keyword: str, days_back: int = 1) -> Optional[EmailNewsletter]:
        """특정 발신자 키워드로 최근 이메일 수집"""
        if not self._conn:
            self.connect()

        self._conn.select("INBOX")

        # 날짜 기준으로 검색 (오늘 또는 어제 이후)
        since_date = (now_kst() - timedelta(days=days_back)).strftime("%d-%b-%Y")

        try:
            _, msg_ids = self._conn.search(None, f'(SINCE "{since_date}" FROM "{sender_keyword}")')
        except Exception:
            msg_ids = [b""]
        if not msg_ids or not msg_ids[0]:
            _, msg_ids = self._conn.search(None, f'SINCE "{since_date}"')

        if not msg_ids or not msg_ids[0]:
            return None

        # 가장 최근 메일
        ids = msg_ids[0].split()
        latest_id = ids[-1]

        _, msg_data = self._conn.fetch(latest_id, "(RFC822)")
        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)

        subject = _decode_str(msg.get("Subject", ""))
        sender = _decode_str(msg.get("From", ""))

        # 발신자 키워드 확인
        if sender_keyword.lower() not in sender.lower() and sender_keyword.lower() not in subject.lower():
            return None

        body_html, body_text = _extract_body(msg)
        link = _extract_main_link(body_html or body_text or "")
        summary = _extract_summary(body_html, body_text, subject)

        return EmailNewsletter(
            source=sender_keyword,
            subject=subject,
            summary=summary,
            link=link,
            received_at=now_kst(),
        )

    def fetch_stibee_url(self, sender_keyword: str, days_back: int = 2) -> Optional[str]:
        """이메일 본문에서 스티비 공유 URL 자동 추출"""
        if not self._conn:
            self.connect()

        self._conn.select("INBOX")
        since_date = (now_kst() - timedelta(days=days_back)).strftime("%d-%b-%Y")

        # FROM 검색은 한국어 키워드에서 예외 없이 빈 결과를 반환하는 경우가 있음
        # → 항상 SINCE 검색 후 Python에서 필터링
        try:
            _, msg_ids = self._conn.search(None, f'(SINCE "{since_date}" FROM "{sender_keyword}")')
        except Exception:
            msg_ids = [b""]
        if not msg_ids or not msg_ids[0]:
            _, msg_ids = self._conn.search(None, f'SINCE "{since_date}"')

        if not msg_ids or not msg_ids[0]:
            return None

        ids = msg_ids[0].split()

        # 최신부터 역순으로 검색
        for latest_id in reversed(ids):
            _, msg_data = self._conn.fetch(latest_id, "(RFC822)")
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            sender = _decode_str(msg.get("From", ""))
            subject = _decode_str(msg.get("Subject", ""))

            if sender_keyword.lower() not in sender.lower() and sender_keyword.lower() not in subject.lower():
                continue

            html_body, _ = _extract_body(msg)
            if not html_body:
                continue

            soup = BeautifulSoup(html_body, "html.parser")

            # 1순위: 직접 share URL
            for a in soup.select("a[href*='stibee.com']"):
                href = a.get("href", "")
                if "/api/v1.0/emails/share/" in href:
                    return href

            # 2순위: event.stibee.com/v2/click/…/{base64} → stib.ee → share URL
            for a in soup.select("a[href*='event.stibee.com/v2/click']"):
                href = a.get("href", "")
                decoded = _decode_stibee_event_href(href)
                if decoded.startswith("https://stib.ee/"):
                    share_url = _follow_to_share_url(decoded)
                    if share_url:
                        return share_url

        return None

    def fetch_all_newsletters(self, newsletter_configs: dict) -> dict:
        """모든 뉴스레터 수집"""
        results = {}
        weekday = now_kst().weekday()  # 0=월, 1=화, 4=목, 5=금

        schedule_map = {
            "daily": list(range(7)),
            "tuesday": [1],
            "thursday": [3],
            "friday": [4],
        }

        try:
            self.connect()
            for name, cfg in newsletter_configs.items():
                allowed_days = schedule_map.get(cfg.get("schedule", "daily"), list(range(7)))
                if weekday not in allowed_days:
                    continue
                newsletter = self.fetch_newsletter(cfg["sender_keyword"])
                if newsletter:
                    results[name] = newsletter
        finally:
            self.disconnect()

        return results


def _decode_str(s: str) -> str:
    parts = decode_header(s)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return "".join(decoded)


def _extract_body(msg) -> tuple[str, str]:
    html_body = ""
    text_body = ""

    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if "attachment" in cd:
                continue
            if ct == "text/html":
                html_body = part.get_payload(decode=True).decode(
                    part.get_content_charset() or "utf-8", errors="replace"
                )
            elif ct == "text/plain" and not text_body:
                text_body = part.get_payload(decode=True).decode(
                    part.get_content_charset() or "utf-8", errors="replace"
                )
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            content = payload.decode(charset, errors="replace")
            if msg.get_content_type() == "text/html":
                html_body = content
            else:
                text_body = content

    return html_body, text_body


def _extract_main_link(content: str) -> str:
    """본문에서 대표 링크 추출"""
    if not content:
        return ""

    # HTML에서 링크 추출
    if "<a" in content:
        soup = BeautifulSoup(content, "html.parser")
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            if href.startswith("http") and not any(skip in href for skip in [
                "unsubscribe", "수신거부", "mailto:", "utm_source=email"
            ]):
                # 첫 번째 유효한 링크 반환
                return href

    # 텍스트에서 URL 추출
    urls = re.findall(r"https?://[^\s\)\"']+", content)
    for url in urls:
        if not any(skip in url for skip in ["unsubscribe", "pixel", "track"]):
            return url

    return ""


def _decode_stibee_event_href(href: str) -> str:
    """event.stibee.com/v2/click/…/{base64} 마지막 세그먼트를 디코딩해 원본 URL 반환"""
    try:
        last = href.rstrip("/").split("/")[-1]
        pad = last + "=" * (4 - len(last) % 4)
        return base64.b64decode(pad).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _follow_to_share_url(url: str) -> Optional[str]:
    """stib.ee 단축 URL을 따라가 stibee share URL 반환. 실패 시 None."""
    try:
        r = requests.get(url, timeout=10, allow_redirects=True)
        final = r.url
        if "/api/v1.0/emails/share/" in final:
            return final
    except Exception:
        pass
    return None


def _extract_summary(html: str, text: str, subject: str) -> str:
    """이메일 본문에서 요약 추출"""
    if html:
        soup = BeautifulSoup(html, "html.parser")
        # 불필요한 태그 제거
        for tag in soup(["script", "style", "head"]):
            tag.decompose()
        content = soup.get_text(separator=" ").strip()
    elif text:
        content = text.strip()
    else:
        return subject

    # 첫 200자 추출 (의미 있는 내용)
    content = re.sub(r"\s+", " ", content)
    return content[:300].strip() if content else subject
