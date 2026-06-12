import json
import os
import tempfile
import urllib.request
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from uploader.drive import download_video as drive_download, list_videos as drive_list
from uploader.mega_source import download_video as mega_download, list_videos as mega_list
from uploader.state import (
    get_channel_count,
    is_uploaded,
    load_state,
    mark_uploaded,
    save_state,
)
from uploader.facebook import FacebookUploadError, upload_video as fb_upload_video
from uploader.youtube import QuotaExceededError, upload_video as yt_upload_video


def notify(subject: str, body: str) -> None:
    import smtplib
    from email.mime.text import MIMEText

    app_password = os.environ.get("GMAIL_APP_PASSWORD")
    if not app_password:
        return

    email = "akash.awal.07@gmail.com"
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = email
    msg["To"] = email

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(email, app_password)
            smtp.send_message(msg)
    except Exception as e:
        print(f"  [Email] Failed to send notification: {e}")

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
    defaults = channel["defaults"]
    platform = channel.get("platform", "youtube")
    source = channel.get("source", "drive")
    max_uploads = channel.get("max_uploads_per_run")
    uploads_this_run = 0

    print(f"\n=== {name} ({platform}) ===")

    # Source: how we get videos
    if source == "mega":
        mega_email = os.environ.get("MEGA_EMAIL")
        mega_password = os.environ.get("MEGA_PASSWORD")
        if not mega_email or not mega_password:
            raise RuntimeError("MEGA_EMAIL or MEGA_PASSWORD environment variable is not set.")
        folder_url = channel["mega_folder_url"]
        all_videos = mega_list(mega_email, mega_password, folder_url)
    else:
        creds = get_credentials(channel["token_env"])
        drive = build("drive", "v3", credentials=creds)
        all_videos = drive_list(drive, channel["drive_folder_id"])

    # Destination: where we upload
    if platform == "facebook":
        fb_token = os.environ.get(channel["fb_token_env"])
        if not fb_token:
            raise RuntimeError(f"Environment variable '{channel['fb_token_env']}' is not set.")
        fb_page_id = channel["fb_page_id"]
    else:
        if source != "mega":
            youtube = build("youtube", "v3", credentials=creds)
        else:
            yt_creds = get_credentials(channel["token_env"])
            youtube = build("youtube", "v3", credentials=yt_creds)

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
            if source == "mega":
                mega_download(mega_email, mega_password, file_id, dest)
            else:
                drive_download(drive, file_id, dest)

            print(f"  [{file_name}] Uploading as '{title}'...")
            try:
                if platform == "facebook":
                    vid_id = fb_upload_video(fb_page_id, fb_token, dest, title, defaults)
                    url = f"https://www.facebook.com/{fb_page_id}/videos/{vid_id}"
                else:
                    vid_id = yt_upload_video(youtube, dest, title, defaults)
                    url = f"https://youtu.be/{vid_id}"
            except QuotaExceededError:
                print("  YouTube daily quota reached. Stopping for today — will resume tomorrow.")
                notify(
                    f"[{name}] YouTube quota reached",
                    f"Daily upload quota exceeded for channel: {name}\n\nWill resume tomorrow.",
                )
                return state
            except Exception as e:
                print(f"  [{file_name}] Upload failed: {e}")
                notify(
                    f"[{name}] Upload failed: {file_name}",
                    f"Channel: {name}\nPlatform: {platform}\nFile: {file_name}\nTitle: {title}\n\nReason:\n{e}",
                )
                raise
            print(f"  [{file_name}] Done -> {url}")
            notify(
                f"[{name}] Uploaded: {title}",
                f"Channel: {name}\nPlatform: {platform}\nTitle: {title}\nURL: {url}",
            )

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
