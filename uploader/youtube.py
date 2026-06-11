import json
from pathlib import Path

from googleapiclient.http import MediaFileUpload


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
        status, response = request.next_chunk()
        if status:
            print(f"  Upload {int(status.progress() * 100)}%")

    return response["id"]
