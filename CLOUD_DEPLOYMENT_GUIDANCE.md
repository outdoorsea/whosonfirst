# Who's on First (WOF) Cloud Deployment Guidance

This document provides guidance for deploying the containerized WOF API service to a cloud environment, specifically using AWS services as an example.

## 1. Prerequisites

*   **AWS Account**: With necessary permissions to create ECR repositories, App Runner services, and potentially VPCs/security groups.
*   **AWS CLI**: Configured on your local machine.
*   **Docker Desktop**: Installed and running.
*   **WOF API Service Docker Image**: You should have built and tested the Docker image locally using `docker compose build`.

## 2. Build and Push Docker Image to AWS ECR

The WOF API service is containerized using Docker. To deploy it to AWS, you'll need to push its image to a container registry like Amazon Elastic Container Registry (ECR).

### Step 2.1: Create an ECR Repository

1.  Go to the AWS Management Console.
2.  Navigate to **ECR (Elastic Container Registry)**.
3.  Click "Create repository".
4.  Give it a name (e.g., `wof-api-service`). Keep other settings as default for now.
5.  Click "Create repository".

### Step 2.2: Authenticate Docker to ECR

Retrieve the `docker login` command for your ECR repository. You can find this by selecting your repository in the ECR console and clicking "View push commands".

```bash
aws ecr get-login-password --region <your-aws-region> | docker login --username AWS --password-stdin <your-aws-account-id>.dkr.ecr.<your-aws-region>.amazonaws.com
```

### Step 2.3: Build and Tag the Docker Image

Navigate to your `~/whosonfirst` directory.

```bash
cd ~/whosonfirst
docker build -t wof-api-service .
docker tag wof-api-service:latest <your-aws-account-id>.dkr.ecr.<your-aws-region>.amazonaws.com/wof-api-service:latest
```

### Step 2.4: Push the Docker Image to ECR

```bash
docker push <your-aws-account-id>.dkr.ecr.<your-aws-region>.amazonaws.com/wof-api-service:latest
```

## 3. Deploy to AWS App Runner

AWS App Runner is a fully managed service that makes it easy to deploy containerized web applications and APIs. It's a good choice for this standalone microservice.

### Step 3.1: Create an App Runner Service

1.  Go to the AWS Management Console.
2.  Navigate to **App Runner**.
3.  Click "Create service".

### Step 3.2: Configure Source and Deployment

*   **Source**: Choose "Container registry".
*   **Provider**: Select "Amazon ECR".
*   **Repository**: Browse and select the `wof-api-service` repository you just created.
*   **Tag**: Enter `latest` (or the tag you pushed).
*   **Deployment settings**: Choose "Manual" for now. You can configure automatic deployments later.
*   Click "Next".

### Step 3.3: Configure Service Settings

*   **Service name**: `wof-api-service`
*   **Port**: `8000` (as defined in your `Dockerfile` and `main.py`)
*   **Environment variables**: This is crucial for connecting to your PostGIS database. Add the following:
    *   `DB_HOST`: The endpoint of your RDS PostgreSQL instance (from Terraform outputs).
    *   `DB_PORT`: `5432`
    *   `DB_NAME`: `wof` (or your custom database name).
    *   `DB_USER`: `wofadmin` (or your custom user).
    *   `DB_PASS`: The secure password for your database. **Use AWS Secrets Manager for production.**
*   **Instance configuration**: Choose appropriate CPU and Memory (e.g., 1 vCPU, 2 GB Memory).
*   **Security**:
    *   **VPC connector**: If your RDS database is in a private VPC subnet (recommended), you *must* create a VPC connector for App Runner to access it.
    *   **Instance role**: App Runner will need an IAM role with permissions to access ECR and potentially Secrets Manager.

### Step 3.4: Review and Create

Review all settings and click "Create & deploy". App Runner will pull your image, deploy it, and provide you with a service URL.

## 4. Testing the Deployed Service

Once the App Runner service is deployed and healthy, you can test it:

1.  **Access the Service URL**: Open the provided App Runner service URL in your browser.
2.  **Health Check**: Append `/health` to the URL (e.g., `https://<apprunner-url>.awsapprunner.com/health`). You should see `{"status": "ok"}`.
3.  **Hierarchy Endpoint**: Test the main endpoint: `https://<apprunner-url>.awsapprunner.com/api/v1/hierarchy?lat=37.7749&lon=-122.4194`. You should receive the stubbed hierarchy response.

## 5. Next Steps

*   **Implement Real Logic**: Replace the stubbed logic in `main.py` with actual PostGIS queries.
*   **Security**: Implement proper secrets management (e.g., AWS Secrets Manager) for database credentials.
*   **Monitoring & Logging**: Configure monitoring and logging for your App Runner service.
*   **CI/CD**: Set up a CI/CD pipeline to automate building, pushing, and deploying new versions of your WOF API service.
