import json
import os
import tempfile
import urllib.request
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from uploader.drive import download_video, list_videos
from uploader.state import (
    get_channel_count,
    is_uploaded,
    load_state,
    mark_uploaded,
    save_state,
)
from uploader.youtube import QuotaExceededError, upload_video


def notify(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"  [Telegram] Failed to send notification: {e}")

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/youtube",
]


def load_channels() -> list:
    path = Path("channels.json")
    if not path.exists():
        raise RuntimeError("channels.json not found.")
    return json.loads(path.read_text())


def get_credentials(token_env: str) -> Credentials:
    token_data = os.environ.get(token_env)
    if not token_data:
        raise RuntimeError(f"Environment variable '{token_env}' is not set.")
    creds = Credentials.from_authorized_user_info(json.loads(token_data[token_data.index('{'):]), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def build_title(defaults: dict, n: int, filename_stem: str) -> str:
    titles = defaults.get("titles")
    if titles:
        return titles[(n - 1) % len(titles)]
    prefix = defaults.get("title_prefix", "").strip()
    if prefix:
        return f"{prefix} #{n}"
    return filename_stem


def process_channel(channel: dict, state: dict) -> dict:
    name = channel["name"]
    folder_id = channel["drive_folder_id"]
    token_env = channel["token_env"]
    defaults = channel["defaults"]
    max_uploads = channel.get("max_uploads_per_run")
    uploads_this_run = 0

    print(f"\n=== {name} ===")

    creds = get_credentials(token_env)
    drive = build("drive", "v3", credentials=creds)
    youtube = build("youtube", "v3", credentials=creds)

    all_videos = list_videos(drive, folder_id)
    new_videos = [v for v in all_videos if not is_uploaded(state, v["id"])]

    if not new_videos:
        print("No new videos.")
        return state

    print(f"Found {len(new_videos)} new video(s).")

    with tempfile.TemporaryDirectory() as tmp:
        for video in new_videos:
            if max_uploads is not None and uploads_this_run >= max_uploads:
                print(f"  Reached limit of {max_uploads} upload(s) per run. Stopping.")
                return state

            file_name = video["name"]
            file_id = video["id"]
            n = get_channel_count(state, name) + 1
            title = build_title(defaults, n, Path(file_name).stem)
            dest = os.path.join(tmp, file_name)

            print(f"\n  [{file_name}] Downloading...")
            download_video(drive, file_id, dest)

            print(f"  [{file_name}] Uploading as '{title}'...")
            try:
                yt_id = upload_video(youtube, dest, title, defaults)
            except QuotaExceededError:
                print("  YouTube daily quota reached. Stopping for today — will resume tomorrow.")
                notify(f"⏸ <b>{name}</b>: YouTube daily quota reached. Will resume tomorrow.")
                return state
            except Exception as e:
                print(f"  [{file_name}] Upload failed: {e}")
                notify(f"❌ <b>{name}</b>: Failed to upload <b>{file_name}</b>\n\n<b>Reason:</b> {e}")
                raise
            print(f"  [{file_name}] Done -> https://youtu.be/{yt_id}")
            notify(f"✅ <b>{name}</b>: Uploaded <b>{title}</b>\nhttps://youtu.be/{yt_id}")

            state = mark_uploaded(state, file_id, name)
            save_state(state)
            uploads_this_run += 1

    return state


def main():
    channels = load_channels()
    state = load_state()

    for channel in channels:
        state = process_channel(channel, state)

    print("\nAll channels processed.")


if __name__ == "__main__":
    main()
