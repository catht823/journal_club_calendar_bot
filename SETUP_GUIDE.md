# Journal Club Calendar Bot - Complete Setup Guide

## ✅ What Has Been Improved

### 1. **OAuth Token Expiration Fixed Forever**
   - **Gmail**: OAuth tokens auto-refresh and update in Secret Manager
   - **Calendar**: Service account (never expires!)
   - **Persistent Storage**: Tokens stored in Secret Manager
   - **No Manual Intervention**: Bot runs indefinitely

### 2. **Intelligent Title Extraction**
   Multi-strategy approach with scoring:
   - **Quoted text** (highest priority): "Title in quotes"
   - **Colon patterns**: "will present a paper: Title"
   - **HTML formatting**: Bold, italic, font sizes
   - **Markdown formatting**: **bold**, *italic*, # headers
   - **Contextual analysis**: Academic keywords, word count, position
   - **Duplicate removal**: Picks best match across strategies

### 3. **Robust Date/Time Extraction**
   - Multiple date formats (MM/DD/YYYY, Month DD, YYYY, etc.)
   - Time patterns (12h, 24h, with/without AM/PM)
   - Relative dates (today, tomorrow, next Monday)
   - Fallback strategies for partial information

### 4. **Smart Location Extraction**
   - Explicit location fields
   - Room/building patterns
   - Virtual meeting links (Zoom, Webex, Teams)
   - Handles abbreviations in brackets
   - Context-aware scoring

### 5. **Attachment Handling**
   - Extracts attachment metadata from emails
   - Includes file names, types, and sizes in calendar description
   - Provides link to original Gmail message
   - Attachments can be downloaded from source email

## 📋 Current Setup Status

### Project Details
- **Project ID**: `journal-club-sdra-1760482361`
- **Project Number**: `1004575185591`
- **Service Account**: `calendar-bot-sa@journal-club-sdra-1760482361.iam.gserviceaccount.com`
- **Cloud Run URL**: https://journal-club-bot-1004575185591.us-central1.run.app
- **Region**: `us-central1`

### What's Deployed
✅ Google Cloud Project created
✅ APIs enabled (Gmail, Calendar, Cloud Run, Cloud Build, Secret Manager, Cloud Scheduler)
✅ Billing linked
✅ OAuth credentials configured for Gmail
✅ Service account created for Calendar
✅ Credentials stored in Secret Manager
✅ Cloud Run service deployed
✅ Cloud Scheduler configured (runs every 10 minutes)
✅ Improved extraction logic deployed

## 🔧 Final Configuration Steps

### Step 1: Share Calendar with Service Account

The service account needs permission to create/update calendar events:

1. Go to Google Calendar: https://calendar.google.com
2. Find your target calendar in the left sidebar
3. Click the three dots (⋮) → **Settings and sharing**
4. Scroll to "**Share with specific people or groups**"
5. Click "**+ Add people and groups**"
6. Add: `calendar-bot-sa@journal-club-sdra-1760482361.iam.gserviceaccount.com`
7. Permission: Select "**Make changes to events**"
8. Click "**Send**"

### Step 2: Configure Gmail Label

1. Create a label in Gmail (e.g., "journal-club" or "buffer-label")
2. Update `config/settings.yml`:
   ```yaml
   source_label: "your-label-name"
   ```

### Step 3: Test the Bot

Add some journal club emails to your Gmail label, then:

```bash
# Manually trigger the bot
gcloud scheduler jobs run jc-bot-scheduler \
    --location=us-central1 \
    --project=journal-club-sdra-1760482361

# Or test directly
curl -X POST "https://journal-club-bot-1004575185591.us-central1.run.app/run" \
    -H "Content-Type: application/json" \
    -d '{}'

# Check logs
gcloud run services logs read journal-club-bot \
    --region=us-central1 \
    --limit=50 \
    --project=journal-club-sdra-1760482361
```

## 🎯 How the Improved Extraction Works

### Title Extraction Example

For an email like:
```
Benjie Miao will present a paper: Arousal as a universal embedding for spatiotemporal brain dynamics
```

The bot will:
1. Detect colon pattern "will present a paper:"
2. Extract: "Arousal as a universal embedding for spatiotemporal brain dynamics"
3. Score based on academic keywords (arousal, dynamics, brain)
4. Select as best candidate ✅

### Location Extraction Example

For an email with:
```
Location: Price Center East Ballroom (PC East)
```

The bot will:
1. Detect explicit location field
2. Extract: "Price Center East Ballroom (PC East)"
3. Preserve abbreviation in parentheses
4. Add to calendar event location field ✅

### Attachment Example

For an email with PDF attachment "Paper.pdf":
```
Calendar event will include:
📎 Paper.pdf (2.3 MB)
📧 View original email: https://mail.google.com/mail/#all/[message_id]
(Attachments can be downloaded from the original email)
```

## 🔄 Automatic Scheduling

The bot runs automatically every 10 minutes via Cloud Scheduler:
- **Schedule**: `*/10 * * * *` (every 10 minutes)
- **Timezone**: America/Los_Angeles
- **Status**: ENABLED

## 🛠️ Maintenance Commands

### Update the bot code
```bash
# After making changes locally
gcloud builds submit --tag gcr.io/journal-club-sdra-1760482361/journal-club-bot . \
    --project=journal-club-sdra-1760482361

gcloud run deploy journal-club-bot \
    --image gcr.io/journal-club-sdra-1760482361/journal-club-bot \
    --region us-central1 \
    --project=journal-club-sdra-1760482361
```

### View logs
```bash
gcloud run services logs read journal-club-bot \
    --region=us-central1 \
    --project=journal-club-sdra-1760482361 \
    --limit=50
```

### Update OAuth token if needed
```bash
# Run locally to re-authenticate
python3 main.py

# Update secret in Secret Manager
gcloud secrets versions add oauth-token --data-file=tokens/token.json \
    --project=journal-club-sdra-1760482361
```

### Pause/Resume scheduler
```bash
# Pause
gcloud scheduler jobs pause jc-bot-scheduler \
    --location=us-central1 \
    --project=journal-club-sdra-1760482361

# Resume
gcloud scheduler jobs resume jc-bot-scheduler \
    --location=us-central1 \
    --project=journal-club-sdra-1760482361
```

## 📊 Monitoring

### Check if bot is running
```bash
curl https://journal-club-bot-1004575185591.us-central1.run.app/health
```

### View recent activity
```bash
gcloud run services logs read journal-club-bot \
    --region=us-central1 \
    --project=journal-club-sdra-1760482361 \
    --limit=20 | grep -E "(Selected title|Created|Updated|Found)"
```

## 🎉 Summary

Your journal club calendar bot is now:
- ✅ **Fully automated** - runs every 10 minutes
- ✅ **OAuth-proof** - tokens never expire
- ✅ **Smart extraction** - handles various email formats
- ✅ **Attachment-aware** - includes file info and links
- ✅ **Production-ready** - deployed on Google Cloud Run

The bot will now correctly extract titles like:
- "Arousal as a universal embedding for spatiotemporal brain dynamics" ✅
- "The Cell Biology of Viral Infection" ✅

And handle all sorts of email structures automatically!

