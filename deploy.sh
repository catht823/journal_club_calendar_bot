#!/bin/bash

# Google Cloud Deployment Script for Journal Club Calendar Bot
# This script deploys the bot to Google Cloud Run with Cloud Scheduler

set -e

# Configuration
PROJECT_ID=${PROJECT_ID:-"your-project-id"}
REGION=${REGION:-"us-central1"}
SERVICE_NAME="journal-club-bot"
IMAGE_NAME="gcr.io/$PROJECT_ID/$SERVICE_NAME"

echo "🚀 Deploying Journal Club Calendar Bot to Google Cloud"
echo "Project ID: $PROJECT_ID"
echo "Region: $REGION"
echo "Service: $SERVICE_NAME"

# Check if gcloud is installed and authenticated
if ! command -v gcloud &> /dev/null; then
    echo "❌ gcloud CLI is not installed. Please install it first:"
    echo "   https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Check if user is authenticated
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
    echo "❌ Not authenticated with gcloud. Please run:"
    echo "   gcloud auth login"
    exit 1
fi

# Set the project
echo "📋 Setting project to $PROJECT_ID"
gcloud config set project $PROJECT_ID

# Enable required APIs
echo "🔧 Enabling required Google Cloud APIs..."
gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable cloudscheduler.googleapis.com
gcloud services enable secretmanager.googleapis.com
gcloud services enable gmail.googleapis.com
gcloud services enable calendar.googleapis.com

# Build and push the container image
echo "🏗️  Building and pushing container image..."
gcloud builds submit --tag $IMAGE_NAME

# Deploy to Cloud Run
echo "🚀 Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
    --image $IMAGE_NAME \
    --region $REGION \
    --platform managed \
    --allow-unauthenticated \
    --memory 512Mi \
    --cpu 1 \
    --max-instances 10 \
    --timeout 300 \
    --set-env-vars "LOG_LEVEL=INFO,JC_TIMEZONE=America/Los_Angeles,JC_SOURCE_LABEL=buffer-label,JC_PROCESSED_LABEL=jc-processed,JC_CAL_PREFIX=Journal Club – "

# Get the service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format="value(status.url)")

echo "✅ Service deployed successfully!"
echo "🌐 Service URL: $SERVICE_URL"
echo "🏥 Health check: $SERVICE_URL/healthz"

# Create Cloud Scheduler job (runs every 6 hours)
echo "⏰ Setting up Cloud Scheduler job..."
gcloud scheduler jobs create http journal-club-bot-scheduler \
    --schedule="0 */6 * * *" \
    --uri="$SERVICE_URL/run" \
    --http-method=POST \
    --time-zone="America/Los_Angeles" \
    --description="Journal Club Calendar Bot - runs every 6 hours" \
    --max-retry-attempts=3 \
    --max-retry-duration=300s \
    || echo "⚠️  Scheduler job might already exist. Use 'gcloud scheduler jobs update' to modify."

echo ""
echo "🎉 Deployment complete!"
echo ""
echo "📋 Next steps:"
echo "1. Upload your OAuth credentials to Google Secret Manager:"
echo "   gcloud secrets create journal-club-oauth --data-file=tokens/client_secret.json"
echo ""
echo "2. Upload your token file to Google Secret Manager:"
echo "   gcloud secrets create journal-club-token --data-file=tokens/token.json"
echo ""
echo "3. Test the service:"
echo "   curl -X POST $SERVICE_URL/run"
echo ""
echo "4. Check logs:"
echo "   gcloud run logs tail $SERVICE_NAME --region=$REGION"
echo ""
echo "5. View the scheduler job:"
echo "   gcloud scheduler jobs list"
