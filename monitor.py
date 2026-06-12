import json
import os
import smtplib
from email.mime.text import MIMEText
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/youtube",
]
STATUS_FILE = Path("video_status.json")


def notify(subject: str, body: str):
    app_password = os.environ.get("GMAIL_APP_PASSWORD")
    if not app_password:
        return
    email = "akash.awal.07@gmail.com"
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = email
    msg["To"] = email
    msg["X-AutoUploader"] = "true"
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(email, app_password)
            smtp.send_message(msg)
    except Exception as e:
        print(f"  [Email] Failed: {e}")


def get_credentials(token_env: str) -> Credentials:
    token_data = os.environ.get(token_env)
    if not token_data:
        return None
    creds = Credentials.from_authorized_user_info(
        json.loads(token_data[token_data.index("{"):]), SCOPES
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def load_status() -> dict:
    if STATUS_FILE.exists():
        return json.loads(STATUS_FILE.read_text())
    return {}


def save_status(status: dict):
    STATUS_FILE.write_text(json.dumps(status, indent=2))


def _summarise(s: dict) -> str:
    parts = []
    if s.get("uploadStatus") and s["uploadStatus"] != "processed":
        parts.append(f"uploadStatus={s['uploadStatus']}")
    if s.get("privacyStatus"):
        parts.append(f"privacy={s['privacyStatus']}")
    if s.get("rejectionReason"):
        parts.append(f"rejectionReason={s['rejectionReason']}")
    if s.get("madeForKids"):
        parts.append("madeForKids=true")
    return ", ".join(parts) if parts else str(s)


def check_channel(channel: dict, videos: list, known: dict):
    name = channel["name"]
    creds = get_credentials(channel.get("token_env", ""))
    if not creds:
        return known, []

    youtube = build("youtube", "v3", credentials=creds)
    channel_videos = [v for v in videos if v["channel"] == name]
    if not channel_videos:
        return known, []

    id_to_title = {v["youtube_id"]: v["title"] for v in channel_videos}
    video_ids = list(id_to_title.keys())
    found_ids = set()
    changes = []

    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        resp = youtube.videos().list(part="status", id=",".join(batch)).execute()
        for item in resp.get("items", []):
            vid_id = item["id"]
            found_ids.add(vid_id)
            s = item["status"]
            current = {
                "uploadStatus": s.get("uploadStatus"),
                "privacyStatus": s.get("privacyStatus"),
                "rejectionReason": s.get("rejectionReason"),
                "madeForKids": s.get("madeForKids"),
            }
            prev = known.get(vid_id)
            if prev is None:
                known[vid_id] = current
            elif prev != current:
                changes.append({"id": vid_id, "title": id_to_title[vid_id], "prev": prev, "curr": current})
                known[vid_id] = current

    for vid_id in video_ids:
        if vid_id not in found_ids:
            prev = known.get(vid_id, {})
            if prev.get("uploadStatus") != "deleted":
                changes.append({"id": vid_id, "title": id_to_title[vid_id], "prev": prev, "curr": {"uploadStatus": "deleted"}})
                known[vid_id] = {"uploadStatus": "deleted"}

    return known, changes


def main():
    channels = json.loads(Path("channels.json").read_text())
    uploaded_data = json.loads(Path("uploaded.json").read_text()) if Path("uploaded.json").exists() else {}
    videos = uploaded_data.get("youtube_videos", [])

    if not videos:
        print("No uploaded videos to monitor yet.")
        return

    known = load_status()
    all_changes = {}

    for channel in channels:
        if channel.get("platform", "youtube") != "youtube":
            continue
        print(f"Checking {channel['name']}...")
        known, changes = check_channel(channel, videos, known)
        if changes:
            all_changes[channel["name"]] = changes

    save_status(known)

    if not all_changes:
        print("All videos OK — no status changes.")
        return

    lines = ["YouTube video status changes detected:\n"]
    for ch_name, changes in all_changes.items():
        lines.append(f"Channel: {ch_name}")
        for c in changes:
            lines.append(f"  {c['title']}  https://youtu.be/{c['id']}")
            lines.append(f"    Before: {_summarise(c['prev'])}")
            lines.append(f"    After:  {_summarise(c['curr'])}")
        lines.append("")

    body = "\n".join(lines)
    print(body)
    notify("[AutoUploader] YouTube video status changes", body)


if __name__ == "__main__":
    main()
