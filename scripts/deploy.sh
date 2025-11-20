#!/bin/bash
set -e

# Who's On First API Deployment Script
# This script automates the deployment of the WOF API to AWS

echo "=== Who's On First API Deployment ==="
echo ""

# Check for required tools
command -v aws >/dev/null 2>&1 || { echo "Error: AWS CLI is required but not installed." >&2; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "Error: Docker is required but not installed." >&2; exit 1; }
command -v terraform >/dev/null 2>&1 || { echo "Error: Terraform is required but not installed." >&2; exit 1; }

# Get AWS account ID and region
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=${AWS_REGION:-us-east-1}

echo "AWS Account ID: $AWS_ACCOUNT_ID"
echo "AWS Region: $AWS_REGION"
echo ""

# Step 1: Build Docker image
echo "Step 1: Building Docker image..."
docker build -t wof-api-service:latest .
echo "✓ Docker image built successfully"
echo ""

# Step 2: Get ECR repository URL from Terraform
echo "Step 2: Getting ECR repository URL..."
cd terraform
ECR_REPO_URL=$(terraform output -raw ecr_repository_url 2>/dev/null || echo "")

if [ -z "$ECR_REPO_URL" ]; then
    echo "Error: ECR repository not found. Please run 'terraform apply' first."
    exit 1
fi

echo "ECR Repository: $ECR_REPO_URL"
echo ""

# Step 3: Authenticate Docker to ECR
echo "Step 3: Authenticating Docker to ECR..."
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_REPO_URL
echo "✓ Docker authenticated to ECR"
echo ""

# Step 4: Tag and push image
echo "Step 4: Tagging and pushing image to ECR..."
docker tag wof-api-service:latest $ECR_REPO_URL:latest
docker tag wof-api-service:latest $ECR_REPO_URL:$(date +%Y%m%d-%H%M%S)
docker push $ECR_REPO_URL:latest
docker push $ECR_REPO_URL:$(date +%Y%m%d-%H%M%S)
echo "✓ Image pushed to ECR"
echo ""

# Step 5: Deploy/Update App Runner (if enabled)
echo "Step 5: Checking App Runner service..."
APPRUNNER_URL=$(terraform output -raw apprunner_service_url 2>/dev/null || echo "")

if [ -n "$APPRUNNER_URL" ]; then
    echo "App Runner service already exists: $APPRUNNER_URL"
    echo "Note: If auto-deployments are enabled, App Runner will automatically deploy the new image."
else
    echo "App Runner service not yet created."
    echo "To create it, uncomment the aws_apprunner_service resource in terraform/apprunner.tf"
    echo "Then run: cd terraform && terraform apply"
fi

echo ""
echo "=== Deployment Complete ==="
echo ""
echo "Next steps:"
echo "1. If this is your first deployment, import WOF data:"
echo "   python import_wof_data.py --regions US"
echo ""
echo "2. Test the API:"
if [ -n "$APPRUNNER_URL" ]; then
    echo "   curl $APPRUNNER_URL/health"
    echo "   curl '$APPRUNNER_URL/api/v1/hierarchy?lat=37.7749&lon=-122.4194'"
else
    echo "   First create the App Runner service in Terraform"
fi
echo ""
