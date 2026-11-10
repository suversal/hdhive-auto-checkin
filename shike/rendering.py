from datetime import UTC, datetime
from zoneinfo import ZoneInfo


def render_message(text: str, task: dict, timestamp: float) -> str:
    """Replace only documented tokens; ordinary braces are always literal text."""
    local = datetime.fromtimestamp(timestamp, UTC).astimezone(ZoneInfo(task["timezone"]))
    values = {
        "{{date}}": local.strftime("%Y-%m-%d"),
        "{{time}}": local.strftime("%H:%M"),
        "{{weekday}}": "星期" + "一二三四五六日"[local.weekday()],
    }
    for token, value in values.items():
        text = text.replace(token, value)
    return text
