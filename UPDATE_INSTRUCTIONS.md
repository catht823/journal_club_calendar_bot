# Quick Update Commands for Google Cloud Task

## Option 1: Using the update script
```bash
# Make the script executable
chmod +x update.sh

# Set your project ID and run the update
export PROJECT_ID="your-actual-project-id"
./update.sh
```

## Option 2: Manual update commands
```bash
# Set your project ID
export PROJECT_ID="your-actual-project-id"
export REGION="us-central1"  # or your region
export SERVICE_NAME="journal-club-bot"  # or your service name

# Build and push the new image
gcloud builds submit --tag gcr.io/$PROJECT_ID/$SERVICE_NAME

# Update the Cloud Run service
gcloud run deploy $SERVICE_NAME \
    --image gcr.io/$PROJECT_ID/$SERVICE_NAME \
    --region $REGION \
    --platform managed
```

## Option 3: Using Cloud Build (if you have cloudbuild.yaml)
```bash
# Set your project ID
export PROJECT_ID="your-actual-project-id"

# Trigger a build
gcloud builds submit --config cloudbuild.yaml
```

## After updating, test your service:
```bash
# Get your service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format="value(status.url)")

# Test the service
curl -X POST $SERVICE_URL/run

# Check logs
gcloud run logs tail $SERVICE_NAME --region=$REGION
```
