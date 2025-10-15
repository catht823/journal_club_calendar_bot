#!/bin/bash

# Update Script for Existing Google Cloud Task
# This script updates your existing journal club calendar bot deployment

set -e

# Configuration - Update these with your actual values
PROJECT_ID=${PROJECT_ID:-"your-project-id"}
REGION=${REGION:-"us-central1"}
SERVICE_NAME=${SERVICE_NAME:-"journal-club-bot"}
IMAGE_NAME="gcr.io/$PROJECT_ID/$SERVICE_NAME"

echo "🔄 Updating Journal Club Calendar Bot"
echo "Project ID: $PROJECT_ID"
echo "Region: $REGION"
echo "Service: $SERVICE_NAME"

# Check if gcloud is installed and authenticated
if ! command -v gcloud &> /dev/null; then
    echo "❌ gcloud CLI is not installed. Please install it first:"
    echo "   https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Set the project
echo "📋 Setting project to $PROJECT_ID"
gcloud config set project $PROJECT_ID

# Build and push the new container image
echo "🏗️  Building and pushing updated container image..."
gcloud builds submit --tag $IMAGE_NAME

# Update the Cloud Run service
echo "🚀 Updating Cloud Run service..."
gcloud run deploy $SERVICE_NAME \
    --image $IMAGE_NAME \
    --region $REGION \
    --platform managed

# Get the service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format="value(status.url)")

echo "✅ Service updated successfully!"
echo "🌐 Service URL: $SERVICE_URL"
echo "🏥 Health check: $SERVICE_URL/healthz"

# Test the updated service
echo "🧪 Testing the updated service..."
if curl -f -X POST "$SERVICE_URL/run" > /dev/null 2>&1; then
    echo "✅ Service test passed!"
else
    echo "⚠️  Service test failed. Check the logs:"
    echo "   gcloud run logs tail $SERVICE_NAME --region=$REGION"
fi

echo ""
echo "🎉 Update complete!"
echo ""
echo "📋 Useful commands:"
echo "• View logs: gcloud run logs tail $SERVICE_NAME --region=$REGION"
echo "• Test manually: curl -X POST $SERVICE_URL/run"
echo "• Check service status: gcloud run services describe $SERVICE_NAME --region=$REGION"
