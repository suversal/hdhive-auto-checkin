from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from croniter import croniter

from .errors import AppError


def next_time(task: dict, after: float, *, anchor: float | None = None) -> float | None:
    mode = task["schedule"]
    zone = ZoneInfo(task["timezone"])
    base = datetime.fromtimestamp(after, UTC).astimezone(zone)
    if mode == "interval":
        seconds = task["interval"] * 3600
        start = anchor if anchor is not None else after
        return start + (max(0, int((after - start) // seconds)) + 1) * seconds
    if mode == "once":
        at = datetime.fromisoformat(task["once"])
        if at.tzinfo is None:
            at = at.replace(tzinfo=zone)
        return at.timestamp() if at.timestamp() > after else None
    if mode == "cron":
        try:
            return croniter(task["cron"], base, max_years_between_matches=5).get_next(datetime).timestamp()
        except (ValueError, OverflowError) as exc:
            raise AppError("INVALID_SCHEDULE", "无法计算此 Cron 计划的后续时间。") from exc
    hour, minute = map(int, task["time"].split(":"))
    for i in range(9):
        date = base.date() + timedelta(days=i)
        candidate = datetime(date.year, date.month, date.day, hour, minute, tzinfo=zone)
        # A spring-forward nonexistent local time is skipped instead of shifted silently.
        back = candidate.astimezone(UTC).astimezone(zone)
        if (back.hour, back.minute) != (hour, minute):
            continue
        weekday = (candidate.weekday() + 1) % 7
        if mode == "weekly" and weekday not in task["weekdays"]:
            continue
        if candidate.timestamp() > after:
            return candidate.timestamp()
    return None


def preview(task: dict, now: float, count: int = 3) -> list[str]:
    values = []
    after = now
    for _ in range(count):
        value = next_time(task, after, anchor=now)
        if value is None:
            break
        values.append(datetime.fromtimestamp(value, UTC).isoformat())
        after = value
    return values
