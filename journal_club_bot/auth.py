import os
from pathlib import Path
from typing import List
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from .models import Services

SCOPES: List[str] = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar"
]

def _credentials() -> Credentials:
    tokens_dir = Path("tokens")
    token_path = tokens_dir / "token.json"
    client_secret = tokens_dir / "client_secret.json"

    # Cloud-friendly: allow secrets via env vars and write to /tmp
    env_client_secret = os.environ.get("JC_CLIENT_SECRET")
    env_token = os.environ.get("JC_TOKEN")
    tmp_client_secret = Path("/tmp/client_secret.json")
    tmp_token = Path("/tmp/token.json")

    if env_client_secret:
        tmp_client_secret.parent.mkdir(parents=True, exist_ok=True)
        tmp_client_secret.write_text(env_client_secret, encoding="utf-8")
        client_secret = tmp_client_secret

    if env_token:
        tmp_token.parent.mkdir(parents=True, exist_ok=True)
        tmp_token.write_text(env_token, encoding="utf-8")
        token_path = tmp_token

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
            # Persist refreshed token if using local tokens dir
            try:
                token_path.write_text(creds.to_json(), encoding="utf-8")
            except Exception:
                pass
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), SCOPES)
            creds = flow.run_local_server(port=0)
            # Save token only when using local tokens dir
            if not env_token:
                tokens_dir.mkdir(parents=True, exist_ok=True)
                with open(token_path, "w", encoding="utf-8") as f:
                    f.write(creds.to_json())
    return creds

def get_authorized_services() -> Services:
    creds = _credentials()
    gmail = build("gmail", "v1", credentials=creds)
    calendar = build("calendar", "v3", credentials=creds)
    return Services(gmail=gmail, calendar=calendar)