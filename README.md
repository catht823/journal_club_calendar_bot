# Journal Club Calendar Bot

Automatically extract journal club details from Gmail and create/update Google Calendar events, organized into separate calendars per biological category. Talks can belong to multiple categories and will be added to each category's calendar.

## Features

- **Gmail Integration**: Polls Gmail for messages with a specific label (configurable)
- **Smart Parsing**: Extracts date/time, title, speaker, location, and conferencing links from emails
- **Multi-Category Support**: Categorizes talks into multiple biological fields using keyword rules
- **Separate Calendars**: Creates one Google Calendar per category for easy organization
- **Deduplication**: Prevents duplicate events using Gmail message IDs
- **Cross-Platform**: Works on Windows and macOS
- **Configurable**: Easy customization via YAML config files and environment variables

## Prerequisites

- Python 3.10 or higher
- Google account with Gmail and Calendar access
- Google Cloud project with Gmail API and Calendar API enabled
- OAuth 2.0 Client ID credentials

## Quick Setup

### 1. Download the Project

**Option A: Clone from GitHub**
```bash
git clone https://github.com/YOUR_USERNAME/journal_club_calendar_bot.git
cd journal_club_calendar_bot
```

**Option B: Download ZIP**
- Go to your GitHub repo
- Click "Code" → "Download ZIP"
- Extract to your desired location (e.g., `C:\Zijing_local\calendar_bot`)

### 2. Google Cloud Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable APIs:
   - Gmail API
   - Google Calendar API
4. Create OAuth 2.0 credentials:
   - Go to "Credentials" → "Create Credentials" → "OAuth 2.0 Client ID"
   - Choose "Desktop application"
   - Download the JSON file as `client_secret.json`
5. Place `client_secret.json` in the `tokens/` folder of your project

### 3. Install Dependencies

**Windows (PowerShell)**
```powershell
cd C:\Zijing_local\calendar_bot
python -m venv .venv
. .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**macOS (Terminal)**
```bash
cd /path/to/calendar_bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. First Run

```bash
python main.py --once
```

- A browser window will open for Google OAuth authorization
- Grant permissions for Gmail and Calendar access
- Tokens are saved in `tokens/token.json` for future runs

### 5. Gmail Setup

Create a Gmail filter to automatically label journal club emails:
1. Go to Gmail → Settings → Filters and Blocked Addresses
2. Click "Create a new filter"
3. Add criteria (e.g., "from:journal-club@university.edu" OR "subject:Journal Club")
4. Click "Create filter"
5. Check "Apply the label" and select your label (default: `buffer-label`)
6. Click "Create filter"

## Configuration

### Changing the Gmail Label

**Method 1: Edit config file**
```yaml
# config/settings.yml
source_label: your-custom-label
```

**Method 2: Environment variable**
```bash
# Windows PowerShell
$env:JC_SOURCE_LABEL = "your-custom-label"

# macOS/Linux
export JC_SOURCE_LABEL="your-custom-label"
```

### Changing Timezone

**Method 1: Edit config file**
```yaml
# config/settings.yml
timezone: America/New_York  # or Europe/London, Asia/Tokyo, etc.
```

**Method 2: Environment variable**
```bash
export JC_TIMEZONE="America/New_York"
```

### Other Configurable Settings

Edit `config/settings.yml`:
```yaml
timezone: America/Los_Angeles
source_label: buffer-label          # Gmail label to process
processed_label: jc-processed       # Label for processed emails
calendar_prefix: "Journal Club – "   # Prefix for calendar names
default_duration_minutes: 60        # Default event length
lookback_days: 14                   # How far back to search
max_messages: 50                    # Max emails per run
auto_create_calendars: true         # Auto-create missing calendars
```

### Environment Variable Overrides

You can override any setting without editing files:
```bash
# Windows PowerShell
$env:JC_SOURCE_LABEL = "my-label"
$env:JC_TIMEZONE = "America/New_York"
$env:JC_CAL_PREFIX = "Research Talks – "

# macOS/Linux
export JC_SOURCE_LABEL="my-label"
export JC_TIMEZONE="America/New_York"
export JC_CAL_PREFIX="Research Talks – "
```

## File Structure
calendar_bot/
├── main.py # Main entry point  
├── requirements.txt # Python dependencies  
├── .gitignore # Git ignore rules  
├── config/  
│ ├── settings.yml # General settings  
│ └── categories.yml # Category definitions  
├── journal_club_bot/ # Main package  
│ ├── init.py  
│ ├── auth.py # Google OAuth authentication  
│ ├── gmail_client.py # Gmail API interactions  
│ ├── parser.py # Email parsing logic  
│ ├── categorizer.py # Category classification  
│ ├── calendar_client.py # Calendar API interactions  
│ ├── storage.py # Local state management  
│ └── models.py # Data models  
├── scripts/  
│ ├── setup_windows.ps1 # Windows setup script  
│ └── setup_macos.sh # macOS setup script  
├── tokens/ # OAuth tokens (auto-created)  
│ └── client_secret.json # Your Google OAuth credentials  
└── state/ # Processing state (auto-created)  
├── processed.json # Processed message tracking  
└── calendars.json # Calendar ID mapping  

## Automation & Scheduling

The program does **NOT** run automatically by default. You need to set up periodic execution using your operating system's task scheduler.

### How It Works
- **Manual runs**: `python main.py --once` (runs once and exits)
- **Scheduled runs**: `python main.py --poll` (designed for automated execution)
- **No built-in scheduler**: The program itself doesn't have automatic scheduling

### Windows Task Scheduler Setup

1. Open **Task Scheduler** (search in Start menu)
2. Click **"Create Basic Task"**
3. Configure the task:
   - **Name**: "Journal Club Calendar Bot"
   - **Description**: "Automatically process journal club emails"
   - **Trigger**: Choose frequency (see recommendations below)
   - **Action**: "Start a program"
   - **Program/script**: `C:\Python\python.exe` (or your Python installation path)
   - **Add arguments**: `C:\Zijing_local\calendar_bot\main.py --poll`
   - **Start in**: `C:\Zijing_local\calendar_bot`
4. Click **Finish**

### macOS Scheduling

**Option 1: Using crontab**
```bash
# Edit crontab
crontab -e

# Add this line (runs every 10 minutes)
*/10 * * * * cd /path/to/calendar_bot && python3 main.py --poll
```

**Option 2: Using launchd (more modern)**
Create `~/Library/LaunchAgents/com.journalclub.bot.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.journalclub.bot</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/path/to/calendar_bot/main.py</string>
        <string>--poll</string>
    </array>
    <key>StartInterval</key>
    <integer>600</integer>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
```

### Recommended Frequencies

- **Every 10 minutes**: Good for active journal club lists
- **Every hour**: Sufficient for most use cases
- **Daily**: If you only receive emails once per day

### What Happens Each Run

1. **Checks Gmail** for new emails with your configured label
2. **Processes messages** (up to 50 per run, configurable)
3. **Looks back** 14 days for new messages (configurable)
4. **Skips processed** messages to avoid duplicates
5. **Creates/updates** calendar events in appropriate category calendars

### Safety Features

- **Idempotent**: Safe to run multiple times without creating duplicates
- **Deduplication**: Uses Gmail message IDs to track processed emails
- **Error handling**: Continues processing even if individual emails fail
- **State tracking**: Remembers which emails have been processed

### Configuration for Automation

In `config/settings.yml`:
```yaml
lookback_days: 14        # How far back to search for emails
max_messages: 50         # Maximum emails to process per run
```

### Troubleshooting Automation

- **Check logs**: Set `LOG_LEVEL=DEBUG` environment variable for detailed logs
- **Test manually**: Run `python main.py --once` to test before scheduling
- **Verify Python path**: Ensure Task Scheduler uses the correct Python executable
- **Check permissions**: Ensure the scheduled task has access to your files and internet

## Run Online on Google Cloud (Cloud Run)

This section shows how to run the bot online without a local machine continuously running. Recommended path: Cloud Run + Cloud Scheduler (simple, reliable).

### Overview

- Cloud Run hosts a small HTTP service that triggers one poll cycle.
- Cloud Scheduler hits that HTTP endpoint on a schedule (e.g., every 10 minutes).
- Secrets (OAuth files) are stored in Google Secret Manager.
- The app runs statelessly; prefer Firestore/Cloud Storage if you later move `state/` off disk.

### 1) Add a minimal HTTP entrypoint

Create `server.py`:
```python
from flask import Flask, jsonify
from main import main as run_once

app = Flask(__name__)

@app.get("/healthz")
def health():
    return "ok", 200

@app.post("/run")
def run():
    run_once()
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
```

Add to `requirements.txt`:
```bash
Flask==3.0.3
gunicorn==22.0.0
```

### 2) Dockerfile

Create `Dockerfile` at project root:
```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["gunicorn", "-b", "0.0.0.0:8080", "server:app"]
```

Optional `.dockerignore`:
```bash
.venv
__pycache__
*.pyc
tokens
state
.vscode
.idea
```

### 3) OAuth secrets in Secret Manager

Do a one-time local auth to generate:
- `tokens/client_secret.json` (your OAuth client)
- `tokens/token.json` (your user token)

Create secrets:
```bash
gcloud secrets create jc-client-secret --replication-policy=automatic
gcloud secrets versions add jc-client-secret --data-file=tokens/client_secret.json

gcloud secrets create jc-token --replication-policy=automatic
gcloud secrets versions add jc-token --data-file=tokens/token.json
```

Note: Do NOT commit `tokens/` to git.

### 4) Build and deploy to Cloud Run

Set project/region:
```bash
gcloud config set project YOUR_PROJECT_ID
gcloud config set run/region us-central1
```

Build:
```bash
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/jc-bot
```

Deploy:
```bash
gcloud run deploy jc-bot \
  --image gcr.io/YOUR_PROJECT_ID/jc-bot \
  --allow-unauthenticated \
  --set-env-vars=JC_TIMEZONE=America/Los_Angeles \
  --set-env-vars=JC_SOURCE_LABEL=buffer-label \
  --set-env-vars=JC_PROCESSED_LABEL=jc-processed \
  --set-env-vars=JC_CAL_PREFIX="Journal Club – " \
  --set-secrets=JC_CLIENT_SECRET=jc-client-secret:latest \
  --set-secrets=JC_TOKEN=jc-token:latest
```

Your service URL will be like:
https://jc-bot-XXXX-uc.a.run.app

### 5) Cloud Scheduler (run every N minutes)

Create a service account for scheduler (or reuse an existing one) and grant Cloud Run Invoker:
```bash
gcloud iam service-accounts create jc-scheduler \
  --display-name="Journal Club Scheduler"

gcloud run services add-iam-policy-binding jc-bot \
  --member="serviceAccount:jc-scheduler@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
```

Create the job (runs every 10 minutes):
```bash
gcloud scheduler jobs create http jc-bot-every-10m \
  --schedule="*/10 * * * *" \
  --uri="https://YOUR_CLOUD_RUN_URL/run" \
  --http-method=POST \
  --oidc-service-account-email=jc-scheduler@YOUR_PROJECT_ID.iam.gserviceaccount.com \
  --oidc-token-audience="https://YOUR_CLOUD_RUN_URL"
```

### Configuration (no code changes needed)

Cloud Run env vars override YAML:
- `JC_TIMEZONE` (default: America/Los_Angeles)
- `JC_SOURCE_LABEL` (default: buffer-label)
- `JC_PROCESSED_LABEL` (default: jc-processed)
- `JC_CAL_PREFIX` (default: "Journal Club – ")

You can also update `config/settings.yml`, but env vars are preferred for cloud.

### Notes & Best Practices

- Tokens refresh: If `token.json` refreshes, you’ll need to update the `jc-token` secret with the new file. For long-term automation on Google Workspace, consider a service account with domain-wide delegation (not available for personal Gmail).
- State: For high reliability across revisions/instances, store `state/processed.json` and `state/calendars.json` in Firestore or Cloud Storage.
- Security: Keep credentials in Secret Manager; never commit them to git.
- Monitoring: Use `/healthz` endpoint for health checks; check Cloud Run logs for errors.

### Updating the Cloud Run Deployment

When you modify code, configuration files, or dependencies, follow these steps to update your Cloud Run service:

#### 1. Rebuild the Docker Image
```bash
PROJECT_ID=$(gcloud config get-value project)
gcloud builds submit --tag gcr.io/$PROJECT_ID/jc-bot
```

#### 2. Redeploy to Cloud Run
```bash
REGION=us-central1
gcloud run deploy jc-bot \
  --image gcr.io/$PROJECT_ID/jc-bot \
  --region $REGION \
  --allow-unauthenticated
```

#### 3. Verify the Update
```bash
# Check the service URL and latest revision
gcloud run services describe jc-bot --region $REGION --format='value(status.url, status.latestReadyRevisionName)'

# Test the endpoint manually
curl -X POST "$(gcloud run services describe jc-bot --region $REGION --format='value(status.url)')/run"
```

#### 4. Update Dependencies (if needed)
If you modified `requirements.txt`:
- Repeat steps 1-2 (rebuild + redeploy)
- The new dependencies will be installed in the updated image

#### 5. Update Configuration Files
Changes to `config/settings.yml` and `config/categories.yml` are automatically included when you rebuild the image. No additional steps needed.

#### 6. Update OAuth Credentials (if needed)
If you refreshed your OAuth tokens or client credentials:
```bash
# Update the secrets in Secret Manager
gcloud secrets versions add jc-client-secret --data-file=tokens/client_secret.json
gcloud secrets versions add jc-token --data-file=tokens/token.json
```
No redeploy needed unless you changed secret names - the latest version is read at runtime.

#### 7. Test the Updated Service
```bash
# Trigger the scheduler job manually to test
gcloud scheduler jobs run jc-bot-every-10m --location=us-central1
```

#### 8. Rollback (if needed)
If something goes wrong, you can rollback to a previous revision:
```bash
# List available revisions
gcloud run revisions list --service=jc-bot --region $REGION

# Rollback to a specific revision
gcloud run services update-traffic jc-bot --region $REGION --to-revisions REVISION_NAME=100
```

#### Important Notes
- The Cloud Scheduler job and environment variables persist across redeploys
- If deployment fails with "image not found", ensure the tag in step 2 matches your build in step 1
- If you encounter secret permission errors, grant your Cloud Run service account the `roles/secretmanager.secretAccessor` role on the secrets
- The scheduler will automatically use the new version on its next scheduled run

### Alternative: Gmail Push (advanced)

For near real-time processing:
- Set up Gmail `users.watch` to a Pub/Sub topic.
- Make Cloud Run handle Pub/Sub push messages and process new emails.
- Requires renewing the watch periodically and extra setup; use Scheduler + polling first.

## What Each File Does

### Core Files
- **`main.py`**: Entry point that orchestrates the entire process
- **`requirements.txt`**: Lists all Python packages needed

### Configuration Files
- **`config