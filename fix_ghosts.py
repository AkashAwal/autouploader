"""One-off script: reconcile ghost uploads caused by the June 16-18 push
race condition.

Each race produced a second upload run that completed successfully on YouTube
but failed to commit its state. This script finds the source file IDs for
those specific filenames, adds them to uploaded_ids, and records the known
YouTube video IDs so the monitor tracks them too.

Run once via the fix-ghosts workflow, then delete this file.
"""
import json
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from uploader.drive import list_videos as drive_list
from uploader.mega_source import list_videos as mega_list
from uploader.state import load_state, save_state

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/youtube",
]

# Source filenames whose uploads completed but never committed.
GHOST_DRIVE_NAMES = {
    "ai tech reels (369).mp4",
    "ai tech reels (370).mp4",
    "ai tech reels (373).mp4",
    "ai tech reels (381).mp4",
}

GHOST_MEGA_NAMES = {
    "12303.mp4",
    "11856.mp4",
    "10682.mp4",
    "11325.mp4",
}

# YouTube video IDs created by those ghost runs (confirmed from run logs).
GHOST_YOUTUBE = [
    {"youtube_id": "f5bjOHQEMvg", "channel": "AI Tools",              "title": "How to Make Money Online Using AI"},
    {"youtube_id": "GaJC1v5wl8o", "channel": "AI Tools",              "title": "AI Tools to Work Smarter Not Harder in 2026"},
    {"youtube_id": "27IcxtMorUo", "channel": "AI Tools",              "title": "Free AI Tools to Grow Your Business Fast"},
    {"youtube_id": "hwqEYNZgDjs", "channel": "AI Tools",              "title": "Top AI Tools Every Entrepreneur Must Use"},
    {"youtube_id": "19EvAR83cbM", "channel": "Sigma Mindset Shorts",  "title": "Rich People Think Like This and Poor People Do Not"},
    {"youtube_id": "WYR5OuXpvoI", "channel": "Sigma Mindset Shorts",  "title": "Cut Off Low Value People and Watch Your Life Change"},
    {"youtube_id": "lLQHL6eEFwo", "channel": "Sigma Mindset Shorts",  "title": "Focus on Yourself and the Money Will Follow"},
    {"youtube_id": "eaV7ai0bnVo", "channel": "Sigma Mindset Shorts",  "title": "Why Most People Will Never Be Wealthy"},
]


def get_credentials(token_env: str) -> Credentials:
    token_data = os.environ[token_env]
    creds = Credentials.from_authorized_user_info(
        json.loads(token_data[token_data.index("{"):]), SCOPES
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def main():
    channels = json.loads(Path("channels.json").read_text())
    state = load_state()
    already = set(state["uploaded_ids"])
    found_drive = {}
    found_mega = {}

    for channel in channels:
        name = channel["name"]
        source = channel.get("source", "drive")
        if source == "drive" and GHOST_DRIVE_NAMES:
            creds = get_credentials(channel["token_env"])
            drive = build("drive", "v3", credentials=creds)
            for v in drive_list(drive, channel["drive_folder_id"]):
                if v["name"] in GHOST_DRIVE_NAMES:
                    found_drive[v["name"]] = v["id"]
            print(f"Drive scan for '{name}': found {len(found_drive)} ghost file(s).")

        elif source == "mega" and GHOST_MEGA_NAMES:
            for v in mega_list(channel["mega_folder_url"]):
                if v["name"] in GHOST_MEGA_NAMES:
                    found_mega[v["name"]] = v["id"]
            print(f"Mega scan for '{name}': found {len(found_mega)} ghost file(s).")

    added_ids = []
    for name, fid in {**found_drive, **found_mega}.items():
        if fid not in already:
            state["uploaded_ids"].append(fid)
            added_ids.append(f"{name} -> {fid}")

    known_yt_ids = {v["youtube_id"] for v in state.get("youtube_videos", [])}
    added_yt = []
    for entry in GHOST_YOUTUBE:
        if entry["youtube_id"] not in known_yt_ids:
            state["youtube_videos"].append(entry)
            added_yt.append(entry["youtube_id"])

    save_state(state)

    print("\n=== Ghost reconciliation complete ===")
    print(f"Source IDs added to uploaded_ids ({len(added_ids)}):")
    for s in added_ids:
        print(f"  {s}")
    print(f"YouTube IDs added to youtube_videos ({len(added_yt)}): {added_yt}")

    if len(added_ids) < 8:
        missing = (GHOST_DRIVE_NAMES | GHOST_MEGA_NAMES) - set(found_drive) - set(found_mega)
        if missing:
            print(f"\nWARNING: could not find source files for: {missing}")
            print("They may have been deleted from the source folder already.")


if __name__ == "__main__":
    main()
