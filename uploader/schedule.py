"""Timezone-aware daily upload slots.

Each channel uploads exactly two videos per day, tied to fixed wall-clock
slots in India Standard Time (IST has no daylight saving, so a fixed offset
is always correct):

    morning -> 11:00 IST
    evening -> 17:00 IST

The workflow runs frequently (every 30 min). On each run we ask which slots
are "due" (their time has passed today) and let the uploader fill any slot
that has not been filled yet today. This makes the system self-healing: if a
scheduled run is delayed or dropped by GitHub Actions, the next run fills the
missed slot. Because filled slots are recorded per (channel, date, slot), it
is impossible to upload more than two videos per channel per day no matter how
many times the workflow runs.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Kolkata")

# slot name -> (hour, minute) in IST. Order matters: morning before evening.
SLOTS = [
    ("morning", (11, 0)),
    ("evening", (17, 0)),
]


def now_ist() -> datetime:
    return datetime.now(TZ)


def today_str(now: datetime = None) -> str:
    return (now or now_ist()).date().isoformat()


def due_slots(now: datetime = None) -> list:
    """Return the ordered list of slot names whose time has passed today."""
    now = now or now_ist()
    due = []
    for name, (hour, minute) in SLOTS:
        slot_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if now >= slot_time:
            due.append(name)
    return due
