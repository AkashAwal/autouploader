"""Merge local uploaded.json with remote origin/main:uploaded.json.

Called by the workflow push-retry loop when a direct push fails due to a
concurrent run. Reads /tmp/local_uploaded.json (our run's state) and the
current remote state, writes a merged result back to uploaded.json.
Exits 0 if there are new entries to push, exits 2 if the remote already
contains everything our run recorded (concurrent run won the race, nothing left to push).
"""
import json
import subprocess
import sys


def load_json(path):
    with open(path) as f:
        return json.load(f)


def dump_json(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)


local = load_json("/tmp/local_uploaded.json")

result = subprocess.run(
    ["git", "show", "origin/main:uploaded.json"],
    capture_output=True,
    text=True,
)
if result.returncode != 0:
    print("No remote state found; using local state as-is.")
    sys.exit(0)

remote = json.loads(result.stdout)
merged = dict(remote)

remote_ids = set(remote["uploaded_ids"])
new_ids = [id for id in local["uploaded_ids"] if id not in remote_ids]
merged["uploaded_ids"] = remote["uploaded_ids"] + new_ids

remote_yt_ids = {v["youtube_id"] for v in remote["youtube_videos"]}
new_videos = [v for v in local["youtube_videos"] if v["youtube_id"] not in remote_yt_ids]
merged["youtube_videos"] = remote["youtube_videos"] + new_videos

for ch, count in local["channel_counts"].items():
    merged["channel_counts"][ch] = max(remote["channel_counts"].get(ch, 0), count)

slot_order = ["morning", "evening"]
for ch, dates in local["daily_slots"].items():
    remote_dates = merged["daily_slots"].setdefault(ch, {})
    for date, slots in dates.items():
        existing = set(remote_dates.get(date, []))
        merged_slots = sorted(
            existing | set(slots),
            key=lambda s: slot_order.index(s) if s in slot_order else 99,
        )
        remote_dates[date] = merged_slots

dump_json("uploaded.json", merged)

if not new_ids and not new_videos:
    print("Remote already contains all our uploads; concurrent run finished first.")
    sys.exit(2)

print(f"Merged {len(new_ids)} new file ID(s) and {len(new_videos)} new video(s) into remote state.")
sys.exit(0)
