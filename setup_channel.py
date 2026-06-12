"""Update YouTube channel name, description, keywords, and country."""
import json
import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/youtube"]

CHANNEL_NAME = "Neural Feed"

CHANNEL_DESCRIPTION = """Neural Feed is your go-to destination for everything AI and technology. We cover the latest AI tools, tech innovations, and digital strategies reshaping how people work, learn, and build businesses in 2026 and beyond.

Whether you are a student, freelancer, or entrepreneur, Neural Feed breaks down complex AI tools into simple actionable videos so you can start using them right away.

From content generation and automation to launching businesses and growing income streams online, we cover it all.

Artificial intelligence is not just a trend. It is the foundation of the next era of work. Subscribe and stay ahead.

#AITools #ArtificialIntelligence #TechChannel #AIForBeginners #FutureOfWork #OnlineBusiness #AITrends #TechIndia #LearnAI #DigitalFuture"""

CHANNEL_KEYWORDS = "ai tools artificial intelligence tech channel ai for beginners future of work online business ai trends learn ai digital future ai automation make money online ai business startup tools ai productivity tech india ai education"


def get_credentials(token_env: str) -> Credentials:
    token_data = os.environ.get(token_env)
    if not token_data:
        raise RuntimeError(f"Environment variable '{token_env}' is not set.")
    creds = Credentials.from_authorized_user_info(json.loads(token_data[token_data.index('{'):]), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def main():
    token_data = os.environ.get("GOOGLE_TOKEN_CH1")
    if not token_data:
        raise RuntimeError("GOOGLE_TOKEN_CH1 not set.")

    creds = get_credentials("GOOGLE_TOKEN_CH1")
    youtube = build("youtube", "v3", credentials=creds)

    channel_id = youtube.channels().list(part="id", mine=True).execute()["items"][0]["id"]

    youtube.channels().update(
        part="brandingSettings",
        body={
            "id": channel_id,
            "brandingSettings": {
                "channel": {
                    "description": CHANNEL_DESCRIPTION,
                    "keywords": CHANNEL_KEYWORDS,
                    "country": "IN",
                }
            },
        },
    ).execute()

    print(f"Channel updated successfully.")
    print(f"  Name:    {CHANNEL_NAME}")
    print(f"  Country: India (IN)")


if __name__ == "__main__":
    main()
