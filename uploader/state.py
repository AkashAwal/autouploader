import json
from pathlib import Path

STATE_FILE = Path("uploaded.json")


def load_state() -> dict:
    if STATE_FILE.exists():
        data = json.loads(STATE_FILE.read_text())
        # migrate old flat-list format
        if isinstance(data, list):
            data = {"uploaded_ids": data, "channel_counts": {}}
        data.setdefault("uploaded_ids", [])
        data.setdefault("channel_counts", {})
        data.setdefault("youtube_videos", [])
        data.setdefault("daily_slots", {})
        return data
    return {"uploaded_ids": [], "channel_counts": {}, "youtube_videos": [], "daily_slots": {}}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def is_uploaded(state: dict, file_id: str) -> bool:
    return file_id in state["uploaded_ids"]


def mark_uploaded(state: dict, file_id: str, channel_name: str, youtube_id: str = None, title: str = None) -> dict:
    state["uploaded_ids"].append(file_id)
    state["channel_counts"][channel_name] = state["channel_counts"].get(channel_name, 0) + 1
    if youtube_id:
        state["youtube_videos"].append({"youtube_id": youtube_id, "channel": channel_name, "title": title or ""})
    return state


def get_channel_count(state: dict, channel_name: str) -> int:
    return state["channel_counts"].get(channel_name, 0)


def slot_filled(state: dict, channel_name: str, date: str, slot: str) -> bool:
    return slot in state["daily_slots"].get(channel_name, {}).get(date, [])


def mark_slot(state: dict, channel_name: str, date: str, slot: str) -> dict:
    by_channel = state["daily_slots"].setdefault(channel_name, {})
    filled = by_channel.setdefault(date, [])
    if slot not in filled:
        filled.append(slot)
    return state


def prune_slots(state: dict, keep_dates: set) -> dict:
    """Drop slot records for days we no longer need, keeping the file small."""
    for channel_name, by_date in list(state["daily_slots"].items()):
        for date in list(by_date.keys()):
            if date not in keep_dates:
                del by_date[date]
    return state
