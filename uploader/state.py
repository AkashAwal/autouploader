import json
from pathlib import Path

STATE_FILE = Path("uploaded.json")


def load_state() -> dict:
    if STATE_FILE.exists():
        data = json.loads(STATE_FILE.read_text())
        # migrate old flat-list format
        if isinstance(data, list):
            return {"uploaded_ids": data, "channel_counts": {}, "youtube_videos": []}
        if "youtube_videos" not in data:
            data["youtube_videos"] = []
        return data
    return {"uploaded_ids": [], "channel_counts": {}, "youtube_videos": []}


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
