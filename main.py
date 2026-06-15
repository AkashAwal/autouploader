import json
import os
import tempfile
import traceback
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from uploader.drive import download_video as drive_download, list_videos as drive_list
from uploader.mega_source import download_video as mega_download, list_videos as mega_list
from uploader.schedule import due_slots, now_ist, today_str
from uploader.state import (
    get_channel_count,
    is_uploaded,
    load_state,
    mark_slot,
    mark_uploaded,
    prune_slots,
    save_state,
    slot_filled,
)
from uploader.facebook import FacebookUploadError, upload_video as fb_upload_video
from uploader.youtube import (
    QuotaExceededError,
    UploadLimitError,
    upload_video as yt_upload_video,
)


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

    msg["X-AutoUploader"] = "true"
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


def process_channel(channel: dict, state: dict, date: str, pending_slots: list) -> dict:
    """Fill any unfilled-but-due upload slots for one channel.

    `pending_slots` is the ordered list of slot names that are due today and
    not yet filled for this channel. We upload exactly one video per pending
    slot, so a channel can never exceed two uploads per day.
    """
    name = channel["name"]
    defaults = channel["defaults"]
    platform = channel.get("platform", "youtube")
    source = channel.get("source", "drive")

    print(f"\n=== {name} ({platform}) ===")
    print(f"  Slots to fill now: {', '.join(pending_slots)}")

    # Source: how we get videos
    if source == "mega":
        folder_url = channel["mega_folder_url"]
        all_videos = mega_list(folder_url)
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
        print("  No new videos available in source.")
        notify(
            f"[{name}] No new videos to upload",
            f"Channel: {name}\nThe source folder has no un-uploaded videos left. "
            f"Add more videos so scheduled slots can be filled.",
        )
        return state

    print(f"  {len(new_videos)} new video(s) available; filling {len(pending_slots)} slot(s).")

    queue = list(new_videos)
    with tempfile.TemporaryDirectory() as tmp:
        for slot in pending_slots:
            if not queue:
                print("  Ran out of source videos before all slots were filled.")
                break

            video = queue.pop(0)
            file_name = video["name"]
            file_id = video["id"]
            n = get_channel_count(state, name) + 1
            title = build_title(defaults, n, Path(file_name).stem)
            dest = os.path.join(tmp, file_name)

            print(f"\n  [{slot}] [{file_name}] Downloading...")
            if source == "mega":
                mega_download(folder_url, file_id, dest)
            else:
                drive_download(drive, file_id, dest)

            print(f"  [{slot}] [{file_name}] Uploading as '{title}'...")
            try:
                if platform == "facebook":
                    vid_id = fb_upload_video(fb_page_id, fb_token, dest, title, defaults)
                    url = f"https://www.facebook.com/{fb_page_id}/videos/{vid_id}"
                else:
                    vid_id = yt_upload_video(youtube, dest, title, defaults)
                    url = f"https://youtu.be/{vid_id}"
            except (QuotaExceededError, UploadLimitError) as e:
                # Soft, self-resolving conditions. Stop THIS channel for now;
                # the slot stays unfilled and a later run/day will retry it.
                print(f"  [{slot}] Paused: {e} Will retry on the next run.")
                notify(
                    f"[{name}] Upload paused: {type(e).__name__}",
                    f"Channel: {name}\nSlot: {slot}\n\n{e}\n\n"
                    f"The slot was left unfilled and will be retried automatically.",
                )
                return state
            except Exception as e:
                # Hard failure for this video: report, but do NOT crash so the
                # other channel still gets processed. Leave the slot unfilled.
                print(f"  [{slot}] [{file_name}] Upload failed: {e}")
                notify(
                    f"[{name}] Upload failed: {file_name}",
                    f"Channel: {name}\nPlatform: {platform}\nSlot: {slot}\n"
                    f"File: {file_name}\nTitle: {title}\n\nReason:\n{e}",
                )
                return state

            print(f"  [{slot}] [{file_name}] Done -> {url}")
            notify(
                f"[{name}] Uploaded ({slot}): {title}",
                f"Channel: {name}\nPlatform: {platform}\nSlot: {slot}\nTitle: {title}\nURL: {url}",
            )

            state = mark_uploaded(
                state, file_id, name,
                youtube_id=vid_id if platform == "youtube" else None,
                title=title,
            )
            state = mark_slot(state, name, date, slot)
            save_state(state)

    return state


def main():
    channels = load_channels()
    state = load_state()

    now = now_ist()
    date = today_str(now)
    due = due_slots(now)
    print(f"Now (IST): {now:%Y-%m-%d %H:%M}  |  Date: {date}  |  Due slots: {due or 'none'}")

    if not due:
        print("No slots are due yet today. Nothing to do.")
        save_state(prune_slots(state, {date}))
        return

    for channel in channels:
        name = channel["name"]
        pending = [s for s in due if not slot_filled(state, name, date, s)]
        if not pending:
            print(f"\n=== {name} === all due slots already filled today. Skipping.")
            continue
        try:
            state = process_channel(channel, state, date, pending)
        except Exception as e:
            # Per-channel isolation: one channel's failure must never block
            # the other channel from being processed.
            print(f"\n[ERROR] Channel '{name}' failed: {e}")
            traceback.print_exc()
            notify(
                f"[{name}] Channel run failed",
                f"Channel: {name}\n\n{e}\n\n{traceback.format_exc()}",
            )

    save_state(prune_slots(state, {date}))
    print("\nAll channels processed.")


if __name__ == "__main__":
    main()
