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

## What Each File Does

### Core Files
- **`main.py`**: Entry point that orchestrates the entire process
- **`requirements.txt`**: Lists all Python packages needed

### Configuration Files
- **`config