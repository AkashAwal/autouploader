"""
Run this ONCE per YouTube channel to generate an OAuth token for that channel.

Steps:
  1. Place client_secrets.json in this directory (from Google Cloud Console).
  2. Run: python auth_setup.py
  3. A browser window opens — log in with your Google account.
     IMPORTANT: If you have multiple YouTube channels, Google will ask which
     channel to authorize. Pick the correct one for this token.
  4. Copy the printed JSON and save it as a GitHub Secret (e.g. GOOGLE_TOKEN_CH1).
  5. Repeat for each additional channel, saving each as a separate secret.

Never commit client_secrets.json or any token JSON to git.
"""
import json

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/youtube.upload",
]

flow = InstalledAppFlow.from_client_secrets_file("client_secrets.json", SCOPES)
creds = flow.run_local_server(port=0)

token = {
    "token": creds.token,
    "refresh_token": creds.refresh_token,
    "token_uri": creds.token_uri,
    "client_id": creds.client_id,
    "client_secret": creds.client_secret,
    "scopes": list(creds.scopes),
}

print("\n--- Copy everything below this line ---\n")
print(json.dumps(token, indent=2))
print("\n--- Copy everything above this line ---")
print("\nPaste this as a GitHub Secret (e.g. GOOGLE_TOKEN_CH1, GOOGLE_TOKEN_CH2, ...).")
print("Match the secret name to the 'token_env' field in channels.json.")
