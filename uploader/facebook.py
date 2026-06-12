import os

import requests


class FacebookUploadError(Exception):
    pass


def upload_video(page_id: str, access_token: str, file_path: str, title: str, defaults: dict) -> str:
    description = defaults.get("description", "")
    file_size = os.path.getsize(file_path)

    # Step 1: start resumable upload session
    start_resp = requests.post(
        f"https://graph-video.facebook.com/v19.0/{page_id}/videos",
        data={
            "upload_phase": "start",
            "file_size": file_size,
            "access_token": access_token,
        },
    )
    _check(start_resp)
    session = start_resp.json()
    upload_session_id = session["upload_session_id"]
    start_offset = int(session["start_offset"])
    end_offset = int(session["end_offset"])

    # Step 2: transfer chunks
    with open(file_path, "rb") as f:
        while start_offset < file_size:
            chunk_size = end_offset - start_offset
            f.seek(start_offset)
            chunk = f.read(chunk_size)

            transfer_resp = requests.post(
                f"https://graph-video.facebook.com/v19.0/{page_id}/videos",
                data={
                    "upload_phase": "transfer",
                    "upload_session_id": upload_session_id,
                    "start_offset": start_offset,
                    "access_token": access_token,
                },
                files={"video_file_chunk": ("chunk", chunk, "application/octet-stream")},
            )
            _check(transfer_resp)
            offsets = transfer_resp.json()
            start_offset = int(offsets["start_offset"])
            end_offset = int(offsets["end_offset"])
            print(f"  Upload {int(start_offset / file_size * 100)}%")

    # Step 3: finish and publish
    finish_resp = requests.post(
        f"https://graph-video.facebook.com/v19.0/{page_id}/videos",
        data={
            "upload_phase": "finish",
            "upload_session_id": upload_session_id,
            "title": title,
            "description": description,
            "access_token": access_token,
        },
    )
    _check(finish_resp)
    return finish_resp.json().get("video_id") or finish_resp.json().get("id", "unknown")


def _check(resp: requests.Response) -> None:
    if not resp.ok:
        try:
            err = resp.json().get("error", {})
            msg = err.get("message", resp.text)
        except Exception:
            msg = resp.text
        raise FacebookUploadError(msg)
