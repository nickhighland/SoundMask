from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import requests
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from icalendar import Calendar
from recurring_ical_events import of as recurring_ical_events
from tzlocal import get_localzone

from app.config import AppConfig
from app.models import TitleMatchRule, TriggerBlock
from app.trigger_rules import matches_title

FREEBUSY_SCOPE = "https://www.googleapis.com/auth/calendar.freebusy"
TITLE_MATCH_SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
]
FREEBUSY_SCOPES = [FREEBUSY_SCOPE, *TITLE_MATCH_SCOPES]
ICS_REQUEST_TIMEOUT_SECONDS = 15


def hash_value(raw_value: str) -> str:
    return hashlib.sha256(raw_value.encode("utf-8")).hexdigest()


class GoogleCalendarClient:
    def __init__(self, config: AppConfig):
        self.config = config
        self.token_path = self.config.paths.tokens / "google-token.json"

    def scopes_for_mode(self, trigger_mode: str) -> list[str]:
        if trigger_mode == "freebusy":
            return FREEBUSY_SCOPES
        return TITLE_MATCH_SCOPES

    def client_secret_path(self) -> Path:
        if self.config.google_client_secret:
            return Path(self.config.google_client_secret).expanduser()
        return self.config.paths.tokens / "client_secret.json"

    def oauth_configured(self) -> bool:
        return self.client_secret_path().exists()

    def build_flow(self, redirect_uri: str, trigger_mode: str) -> Flow:
        return Flow.from_client_secrets_file(
            str(self.client_secret_path()),
            scopes=self.scopes_for_mode(trigger_mode),
            redirect_uri=redirect_uri,
        )

    def save_credentials(self, credentials: Credentials) -> None:
        self.token_path.write_text(credentials.to_json(), encoding="utf-8")

    def disconnect(self) -> None:
        if self.token_path.exists():
            self.token_path.unlink()

    def credentials(self, trigger_mode: str) -> Credentials:
        if not self.token_path.exists():
            raise RuntimeError("Google Calendar is not connected.")
        payload = json.loads(self.token_path.read_text(encoding="utf-8"))
        credentials = Credentials.from_authorized_user_info(
            payload,
            scopes=self.scopes_for_mode(trigger_mode),
        )
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(GoogleRequest())
            self.save_credentials(credentials)
        return credentials

    def list_calendars(self, trigger_mode: str) -> list[dict[str, Any]]:
        service = build(
            "calendar",
            "v3",
            credentials=self.credentials(trigger_mode),
            cache_discovery=False,
        )
        response = service.calendarList().list().execute()
        items = response.get("items", [])
        return [
            {
                "calendar_id": item.get("id"),
                "display_name": item.get("summary") or item.get("id"),
                "primary": bool(item.get("primary")),
            }
            for item in items
        ]

    def fetch_freebusy_blocks(
        self,
        calendar_ids: list[str],
        time_min: datetime,
        time_max: datetime,
    ) -> list[TriggerBlock]:
        service = build(
            "calendar",
            "v3",
            credentials=self.credentials("freebusy"),
            cache_discovery=False,
        )
        response = service.freebusy().query(
            body={
                "timeMin": time_min.isoformat(),
                "timeMax": time_max.isoformat(),
                "items": [{"id": calendar_id} for calendar_id in calendar_ids],
            }
        ).execute()
        blocks: list[TriggerBlock] = []
        calendars = response.get("calendars", {})
        for calendar_id, payload in calendars.items():
            for busy in payload.get("busy", []):
                blocks.append(
                    TriggerBlock(
                        start_time=datetime.fromisoformat(busy["start"]),
                        end_time=datetime.fromisoformat(busy["end"]),
                        source="freebusy",
                        calendar_id=calendar_id,
                    )
                )
        return blocks

    def fetch_display_blocks(
        self,
        calendar_ids: list[str],
        time_min: datetime,
        time_max: datetime,
    ) -> list[TriggerBlock]:
        service = build(
            "calendar",
            "v3",
            credentials=self.credentials("title_match"),
            cache_discovery=False,
        )
        fields = "nextPageToken,items(id,summary,start,end,status,transparency)"
        blocks: list[TriggerBlock] = []
        for calendar_id in calendar_ids:
            page_token: str | None = None
            while True:
                response = service.events().list(
                    calendarId=calendar_id,
                    timeMin=time_min.isoformat(),
                    timeMax=time_max.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                    pageToken=page_token,
                    fields=fields,
                ).execute()
                for event in response.get("items", []):
                    if event.get("status") == "cancelled":
                        continue
                    if event.get("transparency") == "transparent":
                        continue
                    start_value = event.get("start", {}).get("dateTime")
                    end_value = event.get("end", {}).get("dateTime")
                    if not start_value or not end_value:
                        continue
                    blocks.append(
                        TriggerBlock(
                            start_time=datetime.fromisoformat(start_value),
                            end_time=datetime.fromisoformat(end_value),
                            source="freebusy",
                            calendar_id=calendar_id,
                            event_id_hash=self._hash_value(event.get("id", "")),
                            summary_hash=(
                                self._hash_value(event.get("summary", ""))
                                if event.get("summary")
                                else None
                            ),
                        )
                    )
                page_token = response.get("nextPageToken")
                if not page_token:
                    break
        return blocks

    def fetch_title_match_blocks(
        self,
        calendar_ids: list[str],
        time_min: datetime,
        time_max: datetime,
        rules: list[TitleMatchRule],
        debug_store_event_summaries: bool,
    ) -> list[TriggerBlock]:
        service = build(
            "calendar",
            "v3",
            credentials=self.credentials("title_match"),
            cache_discovery=False,
        )
        fields = (
            "nextPageToken,items(id,summary,start,end,status,transparency)"
        )
        blocks: list[TriggerBlock] = []
        for calendar_id in calendar_ids:
            page_token: str | None = None
            while True:
                response = service.events().list(
                    calendarId=calendar_id,
                    timeMin=time_min.isoformat(),
                    timeMax=time_max.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                    pageToken=page_token,
                    fields=fields,
                ).execute()
                for event in response.get("items", []):
                    summary = event.get("summary", "")
                    matched_rule = next(
                        (rule for rule in rules if self._event_matches(summary, event, rule)),
                        None,
                    )
                    if matched_rule is None:
                        continue
                    start_value = event.get("start", {}).get("dateTime")
                    end_value = event.get("end", {}).get("dateTime")
                    if not start_value or not end_value:
                        continue
                    blocks.append(
                        TriggerBlock(
                            start_time=datetime.fromisoformat(start_value),
                            end_time=datetime.fromisoformat(end_value),
                            source="title_match",
                            calendar_id=calendar_id,
                            event_id_hash=self._hash_value(event.get("id", "")),
                            summary_hash=(
                                self._hash_value(summary)
                                if summary or debug_store_event_summaries
                                else None
                            ),
                            matched_rule_id=matched_rule.id,
                        )
                    )
                page_token = response.get("nextPageToken")
                if not page_token:
                    break
        return blocks

    def _event_matches(
        self,
        summary: str,
        event: dict[str, Any],
        rule: TitleMatchRule,
    ) -> bool:
        if rule.ignore_cancelled and event.get("status") == "cancelled":
            return False
        if rule.ignore_transparent and event.get("transparency") == "transparent":
            return False
        return matches_title(summary, rule)

    def _hash_value(self, raw_value: str) -> str:
        return hash_value(raw_value)

    def query_window(self) -> tuple[datetime, datetime]:
        now = datetime.now(timezone.utc)
        return (now.replace(microsecond=0), now.replace(microsecond=0))


class IcsCalendarClient:
    def __init__(self, config: AppConfig):
        self.config = config
        self.local_timezone = get_localzone()

    def fetch_freebusy_blocks(
        self,
        feeds: list[dict[str, Any]],
        time_min: datetime,
        time_max: datetime,
        ignore_all_day_events: bool,
    ) -> list[TriggerBlock]:
        return self._fetch_blocks(
            feeds,
            time_min,
            time_max,
            trigger_mode="freebusy",
            rules=[],
            debug_store_event_summaries=False,
            ignore_all_day_events=ignore_all_day_events,
        )

    def fetch_title_match_blocks(
        self,
        feeds: list[dict[str, Any]],
        time_min: datetime,
        time_max: datetime,
        rules: list[TitleMatchRule],
        debug_store_event_summaries: bool,
        ignore_all_day_events: bool,
    ) -> list[TriggerBlock]:
        return self._fetch_blocks(
            feeds,
            time_min,
            time_max,
            trigger_mode="title_match",
            rules=rules,
            debug_store_event_summaries=debug_store_event_summaries,
            ignore_all_day_events=ignore_all_day_events,
        )

    def _fetch_blocks(
        self,
        feeds: list[dict[str, Any]],
        time_min: datetime,
        time_max: datetime,
        trigger_mode: str,
        rules: list[TitleMatchRule],
        debug_store_event_summaries: bool,
        ignore_all_day_events: bool,
    ) -> list[TriggerBlock]:
        blocks: list[TriggerBlock] = []
        for feed in feeds:
            calendar = Calendar.from_ical(self._load_feed_bytes(str(feed.get("location", ""))))
            events = recurring_ical_events(calendar).between(time_min, time_max)
            for event in events:
                block = self._event_to_block(
                    event,
                    feed,
                    trigger_mode=trigger_mode,
                    rules=rules,
                    debug_store_event_summaries=debug_store_event_summaries,
                    ignore_all_day_events=ignore_all_day_events,
                )
                if block is not None:
                    blocks.append(block)
        return blocks

    def _event_to_block(
        self,
        event: Any,
        feed: dict[str, Any],
        trigger_mode: str,
        rules: list[TitleMatchRule],
        debug_store_event_summaries: bool,
        ignore_all_day_events: bool,
    ) -> TriggerBlock | None:
        if str(getattr(event, "name", "")).upper() != "VEVENT":
            return None

        summary = str(event.get("SUMMARY", ""))
        status = str(event.get("STATUS", "")).lower()
        transparency = str(event.get("TRANSP", "")).lower()

        if trigger_mode == "freebusy" and status == "cancelled":
            return None
        if trigger_mode == "freebusy" and transparency == "transparent":
            return None

        matched_rule: TitleMatchRule | None = None
        if trigger_mode == "title_match":
            matched_rule = next(
                (
                    rule
                    for rule in rules
                    if self._matches_title_rule(summary, status, transparency, rule)
                ),
                None,
            )
            if matched_rule is None:
                return None

        start_time, end_time, is_all_day = self._event_window(event)
        if start_time is None or end_time is None:
            return None
        if is_all_day and ignore_all_day_events:
            return None

        uid = str(event.get("UID", ""))
        recurrence_id = event.decoded("RECURRENCE-ID") if "RECURRENCE-ID" in event else start_time
        event_key = f"{uid}:{recurrence_id}"
        return TriggerBlock(
            start_time=start_time,
            end_time=end_time,
            source=f"ics_{trigger_mode}",
            is_all_day=is_all_day,
            calendar_id=str(feed.get("id") or feed.get("location") or ""),
            event_id_hash=hash_value(event_key),
            summary_hash=(
                hash_value(summary)
                if summary or debug_store_event_summaries
                else None
            ),
            matched_rule_id=matched_rule.id if matched_rule else None,
        )

    def _matches_title_rule(
        self,
        summary: str,
        status: str,
        transparency: str,
        rule: TitleMatchRule,
    ) -> bool:
        if rule.ignore_cancelled and status == "cancelled":
            return False
        if rule.ignore_transparent and transparency == "transparent":
            return False
        return matches_title(summary, rule)

    def _event_window(
        self,
        event: Any,
    ) -> tuple[datetime | None, datetime | None, bool]:
        if "DTSTART" not in event:
            return (None, None, False)

        start_raw = event.decoded("DTSTART")
        end_raw = event.decoded("DTEND") if "DTEND" in event else None
        duration = event.decoded("DURATION") if "DURATION" in event else None
        is_all_day = isinstance(start_raw, date) and not isinstance(start_raw, datetime)

        if end_raw is None:
            if duration is not None:
                end_raw = start_raw + duration
            elif is_all_day:
                end_raw = start_raw + timedelta(days=1)
            else:
                end_raw = start_raw

        start_time = self._to_utc_datetime(start_raw)
        end_time = self._to_utc_datetime(end_raw)
        return (start_time, end_time, is_all_day)

    def _to_utc_datetime(self, value: date | datetime) -> datetime:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=self.local_timezone)
            return value.astimezone(timezone.utc)
        return datetime.combine(value, time.min, tzinfo=timezone.utc)

    def _load_feed_bytes(self, location: str) -> bytes:
        parsed = urlparse(location)
        if parsed.scheme in {"http", "https"}:
            response = requests.get(location, timeout=ICS_REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.content
        if parsed.scheme == "webcal":
            https_location = parsed._replace(scheme="https").geturl()
            response = requests.get(https_location, timeout=ICS_REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.content
        if parsed.scheme == "file":
            path = Path(unquote(parsed.path)).expanduser()
            return path.read_bytes()
        return Path(location).expanduser().read_bytes()
