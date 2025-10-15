import os
import json
import logging
from pathlib import Path
from typing import List, Optional
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from .models import Services

# Separate scopes for different auth methods
GMAIL_SCOPES: List[str] = ["https://www.googleapis.com/auth/gmail.readonly"]
CALENDAR_SCOPES: List[str] = ["https://www.googleapis.com/auth/calendar"]

def _get_secret_from_gcp(secret_name: str) -> Optional[str]:
    """Fetch secret from Google Secret Manager"""
    try:
        from google.cloud import secretmanager
        client = secretmanager.SecretManagerServiceClient()
        project_id = os.environ.get("GCP_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")
        if not project_id:
            return None
        name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        logging.warning(f"Could not fetch secret {secret_name} from Secret Manager: {e}")
        return None

def _update_secret_in_gcp(secret_name: str, secret_value: str) -> bool:
    """Update secret in Google Secret Manager"""
    try:
        from google.cloud import secretmanager
        client = secretmanager.SecretManagerServiceClient()
        project_id = os.environ.get("GCP_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")
        if not project_id:
            return False
        parent = f"projects/{project_id}/secrets/{secret_name}"
        payload = secret_value.encode("UTF-8")
        response = client.add_secret_version(
            request={"parent": parent, "payload": {"data": payload}}
        )
        logging.info(f"Updated secret {secret_name} in Secret Manager")
        return True
    except Exception as e:
        logging.warning(f"Could not update secret {secret_name} in Secret Manager: {e}")
        return False

def _gmail_credentials() -> Credentials:
    """Get OAuth credentials for Gmail with automatic refresh"""
    tokens_dir = Path("tokens")
    token_path = tokens_dir / "token.json"
    client_secret_path = tokens_dir / "client_secret.json"

    # Try to get credentials from Secret Manager first (Cloud Run)
    token_json = _get_secret_from_gcp("oauth-token")
    client_secret_json = _get_secret_from_gcp("oauth-client-secret")
    
    # Fall back to environment variables
    if not token_json:
        token_json = os.environ.get("JC_TOKEN")
    if not client_secret_json:
        client_secret_json = os.environ.get("JC_CLIENT_SECRET")
    
    # Fall back to local files
    if not token_json and token_path.exists():
        token_json = token_path.read_text(encoding="utf-8")
    if not client_secret_json and client_secret_path.exists():
        client_secret_json = client_secret_path.read_text(encoding="utf-8")
    
    if not client_secret_json:
        raise ValueError("No OAuth client secret found. Please set up OAuth credentials.")
    
    # Write to temp files for use
    tmp_dir = Path("/tmp")
    tmp_client_secret = tmp_dir / "client_secret.json"
    tmp_client_secret.write_text(client_secret_json, encoding="utf-8")
    
    creds = None
    if token_json:
        # Load existing credentials
        creds = Credentials.from_authorized_user_info(json.loads(token_json), GMAIL_SCOPES)
    
    # Refresh or create new credentials
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logging.info("Refreshing expired OAuth token...")
            try:
                creds.refresh(Request())
                # Save refreshed token
                new_token_json = creds.to_json()
                
                # Update in Secret Manager (Cloud Run)
                if not _update_secret_in_gcp("oauth-token", new_token_json):
                    # Fall back to local file
                    if token_path.parent.exists():
                        token_path.write_text(new_token_json, encoding="utf-8")
                        logging.info("Saved refreshed token to local file")
                
                logging.info("Successfully refreshed OAuth token")
            except Exception as e:
                logging.error(f"Failed to refresh token: {e}")
                creds = None
        
        if not creds:
            # Need to do full OAuth flow
            logging.info("Starting OAuth flow...")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(tmp_client_secret), GMAIL_SCOPES
            )
            creds = flow.run_local_server(port=0)
            
            # Save new token
            new_token_json = creds.to_json()
            if not _update_secret_in_gcp("oauth-token", new_token_json):
                if token_path.parent.exists():
                    tokens_dir.mkdir(parents=True, exist_ok=True)
                    token_path.write_text(new_token_json, encoding="utf-8")
    
    return creds

def _calendar_service_account():
    """Get service account credentials for Calendar"""
    # Try Secret Manager first
    sa_key_json = _get_secret_from_gcp("calendar-service-account")
    
    # Fall back to environment variable
    if not sa_key_json:
        sa_key_json = os.environ.get("CALENDAR_SERVICE_ACCOUNT")
    
    # Fall back to local file
    if not sa_key_json:
        sa_key_path = Path("tokens") / "calendar-service-account.json"
        if sa_key_path.exists():
            sa_key_json = sa_key_path.read_text(encoding="utf-8")
    
    if sa_key_json:
        # Use service account
        sa_info = json.loads(sa_key_json)
        creds = service_account.Credentials.from_service_account_info(
            sa_info, scopes=CALENDAR_SCOPES
        )
        logging.info("Using service account for Calendar")
        return creds
    else:
        # Fall back to user OAuth (not recommended)
        logging.warning("No service account found for Calendar, using OAuth (may expire)")
        return _gmail_credentials()

def get_authorized_services() -> Services:
    """Get authorized services for Gmail and Calendar"""
    gmail_creds = _gmail_credentials()
    calendar_creds = _calendar_service_account()
    
    gmail = build("gmail", "v1", credentials=gmail_creds)
    calendar = build("calendar", "v3", credentials=calendar_creds)
    
    return Services(gmail=gmail, calendar=calendar)