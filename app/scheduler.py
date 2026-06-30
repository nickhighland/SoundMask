from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler

from app.audio import AudioManager, DEFAULT_VOLUME_PERCENT
from app.calendar_client import GoogleCalendarClient, IcsCalendarClient
from app.db import Database, utcnow_iso
from app.models import ManualState, TriggerBlock
from app.trigger_rules import (
    apply_buffers,
    get_next_block,
    is_now_in_active_block,
    merge_blocks,
    should_play,
)


logger = logging.getLogger(__name__)


class SoundMaskScheduler:
    LOOKAHEAD_HOURS = 72

    def __init__(
        self,
        db: Database,
        audio: AudioManager,
        calendar_client: GoogleCalendarClient,
        ics_calendar_client: IcsCalendarClient,
    ):
        self.db = db
        self.audio = audio
        self.calendar_client = calendar_client
        self.ics_calendar_client = ics_calendar_client
        self.scheduler = BackgroundScheduler(timezone="UTC")
        self.current_blocks: list[TriggerBlock] = []
        self.calendar_blocks: list[TriggerBlock] = []
        self.last_sync_ok = False
        self.last_sync_message = "Not synced yet"
        self.last_sync_at: str | None = None
        self._lock = Lock()

    def start(self) -> None:
        if self.scheduler.running:
            return
        interval = int(self.db.get_setting("calendar_sync_interval_seconds", 60))
        self.scheduler.add_job(
            self.sync_cycle,
            "interval",
            seconds=max(15, interval),
            id="calendar_sync",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self.evaluate_playback,
            "interval",
            seconds=10,
            id="playback_eval",
            replace_existing=True,
        )
        self.scheduler.start()
        self.sync_cycle()
        self.evaluate_playback()

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        self.audio.stop()

    def reload_jobs(self) -> None:
        if not self.scheduler.running:
            return
        interval = int(self.db.get_setting("calendar_sync_interval_seconds", 60))
        self.scheduler.reschedule_job(
            "calendar_sync",
            trigger="interval",
            seconds=max(15, interval),
        )

    def sync_cycle(self) -> None:
        with self._lock:
            settings = self.db.get_settings()
            trigger_mode = settings.get("trigger_mode", "fake")
            calendar_source = settings.get("calendar_source", "google")
            window_start = datetime.now(timezone.utc) - timedelta(minutes=10)
            window_end = datetime.now(timezone.utc) + timedelta(
                hours=self.LOOKAHEAD_HOURS
            )
            source = self._cache_source(str(calendar_source), str(trigger_mode))
            start_buffer_minutes = int(settings.get("start_buffer_minutes", 2))
            end_buffer_minutes = int(settings.get("end_buffer_minutes", 3))
            try:
                calendar_blocks: list[TriggerBlock] | None = None
                if trigger_mode == "fake":
                    blocks = self._load_fake_blocks()
                elif calendar_source == "ics":
                    blocks = self._load_ics_blocks(
                        str(trigger_mode),
                        window_start,
                        window_end,
                        settings,
                    )
                elif trigger_mode == "freebusy":
                    if calendar_source == "google":
                        blocks, calendar_blocks = self._load_google_freebusy_blocks(
                            window_start,
                            window_end,
                            settings,
                        )
                    else:
                        blocks = self.calendar_client.fetch_freebusy_blocks(
                            self.db.enabled_calendar_ids(),
                            window_start,
                            window_end,
                        )
                else:
                    blocks = self.calendar_client.fetch_title_match_blocks(
                        self.db.enabled_calendar_ids(),
                        window_start,
                        window_end,
                        self.db.get_title_rules(),
                        bool(settings.get("debug_store_event_summaries", False)),
                    )
                if calendar_blocks is None:
                    blocks = self._filter_blocks(blocks, settings)
                    calendar_blocks = list(blocks)
                self.calendar_blocks = list(calendar_blocks)
                playback_blocks = apply_buffers(
                    merge_blocks(blocks),
                    start_buffer_minutes,
                    end_buffer_minutes,
                )
                self.current_blocks = playback_blocks
                if trigger_mode != "fake":
                    self.db.replace_trigger_cache(
                        source,
                        blocks,
                        start_buffer_minutes,
                        end_buffer_minutes,
                    )
                self.last_sync_ok = True
                self.last_sync_message = f"Synced {len(self.calendar_blocks)} block(s)"
                self.last_sync_at = utcnow_iso()
                logger.info(
                    "Calendar sync complete: source=%s trigger_mode=%s blocks=%s",
                    calendar_source,
                    trigger_mode,
                    len(self.calendar_blocks),
                )
            except Exception as exc:
                if trigger_mode != "fake":
                    self.current_blocks = merge_blocks(self.db.get_cached_blocks(source))
                    self.calendar_blocks = self.db.get_cached_calendar_blocks(source)
                self.last_sync_ok = False
                self.last_sync_message = f"Sync warning: {exc}"
                self.last_sync_at = utcnow_iso()
                logger.warning(
                    "Calendar sync failed: source=%s trigger_mode=%s error=%s",
                    calendar_source,
                    trigger_mode,
                    exc,
                    exc_info=True,
                )
            self.evaluate_playback()

    def evaluate_playback(self) -> None:
        settings = self.db.get_settings()
        manual_state = self._manual_state()
        now = datetime.now(timezone.utc)
        decision = should_play(now, settings, self.current_blocks, manual_state)
        active_sound = self.db.get_active_sound()
        self.audio.fade_in_seconds = int(settings.get("fade_in_seconds", 0))
        if decision.should_play and active_sound and active_sound.path.exists():
            self.audio.start(
                active_sound.path,
                int(settings.get("volume_percent", DEFAULT_VOLUME_PERCENT)),
            )
            self.audio.set_volume(
                int(settings.get("volume_percent", DEFAULT_VOLUME_PERCENT))
            )
        else:
            self.audio.stop(int(settings.get("fade_out_seconds", 0)))
        self.db.set_state(
            "status_snapshot",
            {
                "reason": decision.reason,
                "playing": self.audio.is_playing(),
                "active_now": is_now_in_active_block(now, self.current_blocks),
                "updated_at": utcnow_iso(),
            },
        )

    def manual_play(self) -> None:
        now = datetime.now(timezone.utc)
        minutes = int(self.db.get_setting("manual_play_duration_minutes", 60))
        self.db.set_state(
            "manual_play_until",
            (now + timedelta(minutes=minutes)).isoformat(),
        )
        self.evaluate_playback()

    def manual_stop(self) -> None:
        self.db.set_state("manual_play_until", None)
        self.audio.stop(int(self.db.get_setting("fade_out_seconds", 0)))
        self.evaluate_playback()

    def mute_for(self, minutes: int) -> None:
        until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        self.db.set_state("mute_until", until.isoformat())
        self.evaluate_playback()

    def clear_mute(self) -> None:
        self.db.set_state("mute_until", None)
        self.evaluate_playback()

    def add_fake_block(self, start_in_minutes: int, duration_minutes: int) -> None:
        start = datetime.now(timezone.utc) + timedelta(minutes=start_in_minutes)
        end = start + timedelta(minutes=duration_minutes)
        payload = self.db.get_state("fake_blocks", [])
        payload.append(
            {
                "start_time": start.isoformat(),
                "end_time": end.isoformat(),
            }
        )
        self.db.set_state("fake_blocks", payload)
        self.sync_cycle()

    def clear_fake_blocks(self) -> None:
        self.db.set_state("fake_blocks", [])
        self.sync_cycle()

    def get_status(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        active_block = next(
            (block for block in self.current_blocks if block.start_time <= now <= block.end_time),
            None,
        )
        next_block = get_next_block(now, self.current_blocks)
        snapshot = self.db.get_state("status_snapshot", {})
        active_sound = self.db.get_active_sound()
        mute_until = self.db.get_state("mute_until")
        return {
            "state": self.audio.status()["state"],
            "detail": snapshot.get("reason", self.last_sync_message),
            "trigger_mode": self.db.get_setting("trigger_mode", "fake"),
            "calendar_source": self.db.get_setting("calendar_source", "google"),
            "active_sound": active_sound.display_name if active_sound else "None selected",
            "volume_percent": self.db.get_setting(
                "volume_percent",
                DEFAULT_VOLUME_PERCENT,
            ),
            "active_block": active_block,
            "next_block": next_block,
            "last_sync_message": self.last_sync_message,
            "last_sync_at": self.last_sync_at,
            "muted": bool(mute_until),
            "mute_until": mute_until,
        }

    def _manual_state(self) -> ManualState:
        manual_play_until = self.db.get_state("manual_play_until")
        mute_until = self.db.get_state("mute_until")
        return ManualState(
            manual_play_until=(
                datetime.fromisoformat(manual_play_until)
                if manual_play_until
                else None
            ),
            mute_until=datetime.fromisoformat(mute_until) if mute_until else None,
        )

    def _load_fake_blocks(self) -> list[TriggerBlock]:
        payload = self.db.get_state("fake_blocks", [])
        now = datetime.now(timezone.utc)
        blocks = []
        retained = []
        for item in payload:
            end_time = datetime.fromisoformat(item["end_time"])
            if end_time < now - timedelta(minutes=1):
                continue
            retained.append(item)
            blocks.append(
                TriggerBlock(
                    start_time=datetime.fromisoformat(item["start_time"]),
                    end_time=end_time,
                    source="fake",
                )
            )
        if retained != payload:
            self.db.set_state("fake_blocks", retained)
        return blocks

    def _filter_blocks(
        self,
        blocks: list[TriggerBlock],
        settings: dict[str, Any],
    ) -> list[TriggerBlock]:
        max_duration = int(settings.get("max_event_duration_minutes", 240))
        filtered: list[TriggerBlock] = []
        for block in blocks:
            if settings.get("ignore_all_day_events", True) and block.is_all_day:
                continue
            duration_minutes = int((block.end_time - block.start_time).total_seconds() / 60)
            if duration_minutes > max_duration:
                continue
            filtered.append(block)
        return filtered

    def _cache_source(self, calendar_source: str, trigger_mode: str) -> str:
        if trigger_mode == "fake":
            return "fake"
        return f"{calendar_source}:{trigger_mode}"

    def _load_google_freebusy_blocks(
        self,
        window_start: datetime,
        window_end: datetime,
        settings: dict[str, Any],
    ) -> tuple[list[TriggerBlock], list[TriggerBlock]]:
        try:
            display_blocks = self.calendar_client.fetch_display_blocks(
                self.db.enabled_calendar_ids(),
                window_start,
                window_end,
            )
            filtered_blocks = self._filter_blocks(display_blocks, settings)
            return (filtered_blocks, list(filtered_blocks))
        except Exception as exc:
            logger.info(
                "Google freebusy detail fetch failed, using merged busy windows: %s",
                exc,
            )
        busy_blocks = self.calendar_client.fetch_freebusy_blocks(
            self.db.enabled_calendar_ids(),
            window_start,
            window_end,
        )
        filtered_blocks = self._filter_blocks(busy_blocks, settings)
        return (filtered_blocks, list(filtered_blocks))

    def _load_ics_blocks(
        self,
        trigger_mode: str,
        window_start: datetime,
        window_end: datetime,
        settings: dict[str, Any],
    ) -> list[TriggerBlock]:
        ignore_all_day_events = bool(settings.get("ignore_all_day_events", True))
        if trigger_mode == "freebusy":
            return self.ics_calendar_client.fetch_freebusy_blocks(
                self.db.enabled_ics_feeds(),
                window_start,
                window_end,
                ignore_all_day_events=ignore_all_day_events,
            )
        return self.ics_calendar_client.fetch_title_match_blocks(
            self.db.enabled_ics_feeds(),
            window_start,
            window_end,
            self.db.get_title_rules(),
            bool(settings.get("debug_store_event_summaries", False)),
            ignore_all_day_events=ignore_all_day_events,
        )
