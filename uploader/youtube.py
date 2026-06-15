import json
from pathlib import Path

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload


class QuotaExceededError(Exception):
    """API request quota for the day was exhausted (HTTP 429 / rateLimitExceeded)."""
    pass


class UploadLimitError(Exception):
    """YouTube's per-account daily video upload limit was hit.

    Returned as HTTP 400 with reason 'uploadLimitExceeded'. This is an
    account-level cap (separate from the API quota) that YouTube applies to
    unverified channels and to channels that upload in large bursts. It is a
    soft, self-resolving condition: we stop uploading for this channel today
    and try again on the next slot/day.
    """
    pass


def upload_video(service, file_path: str, title: str, defaults: dict) -> str:
    meta_path = Path(file_path).with_suffix(".json")
    meta = {}
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())

    body = {
        "snippet": {
            "title": meta.get("title", title),
            "description": meta.get("description", defaults["description"]),
            "tags": meta.get("tags", defaults["tags"]),
            "categoryId": meta.get("category_id", defaults["category_id"]),
        },
        "status": {
            "privacyStatus": meta.get("privacy_status", defaults["privacy_status"]),
        },
    }

    media = MediaFileUpload(file_path, chunksize=50 * 1024 * 1024, resumable=True)
    request = service.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        try:
            status, response = request.next_chunk()
        except HttpError as e:
            msg = str(e)
            if "uploadLimitExceeded" in msg or "exceeded the number of videos" in msg:
                raise UploadLimitError(
                    "YouTube per-account daily upload limit reached."
                )
            if e.status_code == 429 or "rateLimitExceeded" in msg or "quotaExceeded" in msg:
                raise QuotaExceededError("YouTube daily API quota exceeded.")
            raise
        if status:
            print(f"  Upload {int(status.progress() * 100)}%")

    return response["id"]
