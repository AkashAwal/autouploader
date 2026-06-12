"""Delete all videos from the YouTube channel configured in channels.json."""
import json
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/youtube",
]


def get_credentials(token_env: str) -> Credentials:
    token_data = os.environ.get(token_env)
    if not token_data:
        raise RuntimeError(f"Environment variable '{token_env}' is not set.")
    creds = Credentials.from_authorized_user_info(json.loads(token_data.lstrip("\xef\xbb\xbf")), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def get_all_video_ids(youtube) -> list[str]:
    # Get the channel's uploads playlist ID
    ch_resp = youtube.channels().list(part="contentDetails", mine=True).execute()
    uploads_playlist = ch_resp["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    video_ids = []
    next_page = None
    while True:
        resp = youtube.playlistItems().list(
            part="contentDetails",
            playlistId=uploads_playlist,
            maxResults=50,
            pageToken=next_page,
        ).execute()
        for item in resp["items"]:
            video_ids.append(item["contentDetails"]["videoId"])
        next_page = resp.get("nextPageToken")
        if not next_page:
            break
    return video_ids


def main():
    channels = json.loads(Path("channels.json").read_text())
    channel = channels[0]
    token_env = channel["token_env"]

    creds = get_credentials(token_env)
    youtube = build("youtube", "v3", credentials=creds)

    print("Fetching uploaded videos...")
    video_ids = get_all_video_ids(youtube)
    print(f"Found {len(video_ids)} video(s).")

    if not video_ids:
        print("Nothing to delete.")
        return

    confirm = input(f"Delete all {len(video_ids)} videos? [y/N] ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        return

    for i, vid_id in enumerate(video_ids, 1):
        youtube.videos().delete(id=vid_id).execute()
        print(f"  [{i}/{len(video_ids)}] Deleted {vid_id}")

    print("Done. All videos deleted.")


if __name__ == "__main__":
    main()
