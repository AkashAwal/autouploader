"""List all YouTube channels accessible with the current token."""
import json
import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/youtube"]


def get_credentials(token_env: str) -> Credentials:
    token_data = os.environ.get(token_env)
    if not token_data:
        raise RuntimeError(f"Environment variable '{token_env}' is not set.")
    creds = Credentials.from_authorized_user_info(json.loads(token_data.lstrip("\xef\xbb\xbf")), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


creds = get_credentials("GOOGLE_TOKEN_CH1")
youtube = build("youtube", "v3", credentials=creds)

resp = youtube.channels().list(part="snippet", mine=True).execute()
for ch in resp.get("items", []):
    print(f"  ID:   {ch['id']}")
    print(f"  Name: {ch['snippet']['title']}")
    print()
