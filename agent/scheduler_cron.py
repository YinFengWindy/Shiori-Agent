"""POSIX cron parsing and next-fire calculation for scheduled jobs."""

from datetime import datetime, timedelta, timezone
from importlib import import_module
from zoneinfo import ZoneInfo


_POSIX_CRON_WEEKDAY_NAMES = ("sun", "mon", "tue", "wed", "thu", "fri", "sat")


def is_cron_expr(value: str) -> bool:
    """Returns whether the expression has five or six cron fields."""
    return len(value.strip().split()) in (5, 6)


def _parse_cron_field(field: str, minimum: int, maximum: int) -> set[int]:
    values: set[int] = set()
    for part in field.split(","):
        part = part.strip()
        if not part:
            continue
        step = 1
        if "/" in part:
            part, step_str = part.split("/", 1)
            step = int(step_str)
            if step <= 0:
                raise ValueError(f"无效 cron step: {field!r}")
        if part == "*":
            start, end = minimum, maximum
        elif "-" in part:
            start_str, end_str = part.split("-", 1)
            start, end = int(start_str), int(end_str)
        else:
            start = end = int(part)
        if start < minimum or end > maximum or start > end:
            raise ValueError(f"无效 cron 字段: {field!r}")
        values.update(range(start, end + 1, step))
    if not values:
        raise ValueError(f"无效 cron 字段: {field!r}")
    return values


def _parse_posix_cron_weekdays(field: str) -> set[int]:
    """Parses cron weekdays with the POSIX convention: 0 and 7 both mean Sunday."""
    return {0 if value == 7 else value for value in _parse_cron_field(field, 0, 7)}


def _next_cron_fire_fallback(cron_expr: str, tz: str, after: datetime) -> datetime:
    parts = cron_expr.strip().split()
    if len(parts) == 5:
        second_values = {0}
        minute_s, hour_s, dom_s, month_s, dow_s = parts
        step = timedelta(minutes=1)
        current = after.astimezone(ZoneInfo(tz)).replace(second=0, microsecond=0)
        if current <= after.astimezone(ZoneInfo(tz)):
            current += step
    elif len(parts) == 6:
        second_s, minute_s, hour_s, dom_s, month_s, dow_s = parts
        second_values = _parse_cron_field(second_s, 0, 59)
        step = timedelta(seconds=1)
        current = after.astimezone(ZoneInfo(tz)).replace(microsecond=0) + step
    else:
        raise ValueError(f"无效的 cron 表达式: {cron_expr!r}")

    minute_values = _parse_cron_field(minute_s, 0, 59)
    hour_values = _parse_cron_field(hour_s, 0, 23)
    dom_values = _parse_cron_field(dom_s, 1, 31)
    month_values = _parse_cron_field(month_s, 1, 12)
    dow_values = _parse_posix_cron_weekdays(dow_s)

    for _ in range(366 * 24 * 60 * (60 if len(parts) == 6 else 1)):
        cron_dow = (current.weekday() + 1) % 7
        if (
            current.second in second_values
            and current.minute in minute_values
            and current.hour in hour_values
            and current.day in dom_values
            and current.month in month_values
            and cron_dow in dow_values
        ):
            return current.astimezone(timezone.utc)
        current += step
    raise ValueError(f"无法在合理范围内解析 cron 表达式: {cron_expr!r}")


def next_cron_fire(cron_expr: str, tz: str, after: datetime) -> datetime:
    """Computes the next fire time with POSIX cron weekday semantics."""
    try:
        from apscheduler.triggers.cron import CronTrigger
    except ModuleNotFoundError:
        return _next_cron_fire_fallback(cron_expr, tz, after)

    try:
        pytz = import_module("pytz")
        tzinfo = pytz.timezone(tz)
    except Exception:
        tzinfo = ZoneInfo(tz)

    parts = cron_expr.strip().split()
    if len(parts) == 5:
        second_s = "0"
        minute_s, hour_s, dom_s, month_s, dow_s = parts
    elif len(parts) == 6:
        second_s, minute_s, hour_s, dom_s, month_s, dow_s = parts
    else:
        raise ValueError(f"无效的 cron 表达式: {cron_expr!r}")
    weekdays = ",".join(
        _POSIX_CRON_WEEKDAY_NAMES[value]
        for value in sorted(_parse_posix_cron_weekdays(dow_s))
    )
    trigger = CronTrigger(
        second=second_s,
        minute=minute_s,
        hour=hour_s,
        day=dom_s,
        month=month_s,
        day_of_week=weekdays,
        timezone=tzinfo,
    )
    result = trigger.get_next_fire_time(None, after)
    if result is None:
        raise ValueError(f"无效的 cron 表达式: {cron_expr!r}")
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result
