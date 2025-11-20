# Who's On First Cloud API - Complete Deployment Guide

This guide walks you through deploying the Who's On First API to AWS from scratch.

## Prerequisites

### Required Tools
- **AWS CLI** (v2.x): [Installation Guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
- **Docker Desktop**: [Installation Guide](https://www.docker.com/products/docker-desktop/)
- **Terraform** (v1.5+): [Installation Guide](https://developer.hashicorp.com/terraform/install)
- **Python 3.9+**: For running the data import script

### AWS Requirements
- AWS Account with appropriate permissions
- AWS CLI configured with credentials (`aws configure`)
- An existing VPC with at least 2 subnets in different availability zones

---

## Part 1: Infrastructure Deployment

### Step 1: Prepare Terraform Configuration

1. Navigate to the terraform directory:
   ```bash
   cd terraform
   ```

2. Copy the example variables file:
   ```bash
   cp terraform.tfvars.example terraform.tfvars
   ```

3. Edit `terraform.tfvars` with your values:
   ```bash
   # Find your VPC ID
   aws ec2 describe-vpcs

   # Find subnet IDs in your VPC (need at least 2 in different AZs)
   aws ec2 describe-subnets --filters "Name=vpc-id,Values=YOUR_VPC_ID"
   ```

4. Update `terraform.tfvars`:
   - Set `vpc_id` to your VPC ID
   - Set `subnet_ids` to at least 2 subnet IDs in different availability zones
   - Set a strong `db_password` (minimum 8 characters)
   - Adjust other settings as needed

### Step 2: Deploy Infrastructure with Terraform

1. Initialize Terraform:
   ```bash
   terraform init
   ```

2. Preview the changes:
   ```bash
   terraform plan
   ```

3. Apply the configuration:
   ```bash
   terraform apply
   ```

   Type `yes` when prompted. This will create:
   - RDS PostgreSQL database with PostGIS
   - ECR repository for Docker images
   - Security groups and networking
   - VPC connector for App Runner
   - IAM roles

4. Save the outputs:
   ```bash
   terraform output > ../terraform-outputs.txt
   ```

**Important Notes:**
- Initial deployment takes 10-15 minutes (RDS creation is slow)
- The App Runner service is commented out by default - we'll enable it after pushing the Docker image

---

## Part 2: Database Setup

### Step 3: Enable PostGIS Extension

1. Get the database endpoint from Terraform outputs:
   ```bash
   terraform output db_endpoint
   ```

2. Install PostgreSQL client (if not already installed):
   ```bash
   # macOS
   brew install postgresql@15

   # Ubuntu/Debian
   sudo apt-get install postgresql-client-15
   ```

3. Connect to the database:
   ```bash
   psql -h $(terraform output -raw db_endpoint) \
        -U wofadmin \
        -d wof
   ```

   Enter the password you set in `terraform.tfvars`.

4. Enable PostGIS:
   ```sql
   CREATE EXTENSION IF NOT EXISTS postgis;
   SELECT PostGIS_full_version();
   \q
   ```

### Step 4: Import Who's On First Data

1. Go back to the project root:
   ```bash
   cd ..
   ```

2. Create a `.env` file with database credentials:
   ```bash
   cat > .env << EOF
   DB_HOST=$(cd terraform && terraform output -raw db_endpoint)
   DB_PORT=5432
   DB_NAME=wof
   DB_USER=wofadmin
   DB_PASS=YOUR_PASSWORD_HERE
   EOF
   ```

3. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Run the import script (start with just US data):
   ```bash
   # Import US localities and neighbourhoods (this will take 1-2 hours)
   python import_wof_data.py --regions US --placetypes locality neighbourhood

   # Optional: Import additional regions
   # python import_wof_data.py --regions CA GB --placetypes locality neighbourhood
   ```

5. Verify the data import:
   ```bash
   psql -h $(cd terraform && terraform output -raw db_endpoint) \
        -U wofadmin \
        -d wof \
        -c "SELECT placetype, COUNT(*) FROM whosonfirst GROUP BY placetype;"
   ```

**Data Import Notes:**
- The script downloads GeoJSON bundles from data.whosonfirst.org
- Files are cached in `./wof_data` directory
- You can interrupt and restart - existing records are skipped
- Full world import can take 24+ hours and require 100GB+ storage

---

## Part 3: Application Deployment

### Step 5: Build and Push Docker Image

1. Set your AWS region:
   ```bash
   export AWS_REGION=us-east-1  # Or your region
   ```

2. Build the Docker image:
   ```bash
   docker build -t wof-api-service:latest .
   ```

3. Get your ECR repository URL:
   ```bash
   cd terraform
   ECR_REPO_URL=$(terraform output -raw ecr_repository_url)
   echo $ECR_REPO_URL
   ```

4. Authenticate Docker to ECR:
   ```bash
   aws ecr get-login-password --region $AWS_REGION | \
       docker login --username AWS --password-stdin $ECR_REPO_URL
   ```

5. Tag and push the image:
   ```bash
   docker tag wof-api-service:latest $ECR_REPO_URL:latest
   docker push $ECR_REPO_URL:latest
   ```

### Step 6: Deploy App Runner Service

1. Edit `terraform/apprunner.tf` and uncomment the `aws_apprunner_service` resource (lines ~164-210)

2. Apply the Terraform changes:
   ```bash
   cd terraform
   terraform apply
   ```

3. Get the App Runner service URL:
   ```bash
   terraform output apprunner_service_url
   ```

4. Wait for the service to be ready (2-3 minutes):
   ```bash
   # Check status
   aws apprunner list-services --region $AWS_REGION
   ```

---

## Part 4: Testing and Verification

### Step 7: Test the API

1. Test the health endpoint:
   ```bash
   SERVICE_URL=$(cd terraform && terraform output -raw apprunner_service_url)
   curl $SERVICE_URL/health
   ```

   Expected response:
   ```json
   {
     "status": "ok",
     "service": "wof-api",
     "database": "healthy"
   }
   ```

2. Test the hierarchy endpoint:
   ```bash
   # San Francisco City Hall
   curl "$SERVICE_URL/api/v1/hierarchy?lat=37.7749&lon=-122.4194"
   ```

   Expected response:
   ```json
   {
     "continent": {"id": 102191581, "name": "North America", "placetype": "continent"},
     "country": {"id": 85633793, "name": "United States", "placetype": "country"},
     "region": {"id": 85688637, "name": "California", "placetype": "region"},
     "locality": {"id": 85922583, "name": "San Francisco", "placetype": "locality"}
   }
   ```

3. Test the place lookup endpoint:
   ```bash
   curl "$SERVICE_URL/api/v1/place/85922583"
   ```

4. View API documentation:
   ```bash
   open "$SERVICE_URL/docs"
   ```

### Step 8: Monitor the Service

1. View App Runner logs:
   ```bash
   aws apprunner list-operations \
       --service-arn $(cd terraform && terraform output -raw apprunner_service_arn) \
       --region $AWS_REGION
   ```

2. View RDS metrics in AWS Console:
   - Navigate to RDS → Databases → wof-postgis-db
   - Check "Monitoring" tab for CPU, connections, etc.

3. Set up CloudWatch alarms (optional):
   ```bash
   # Example: Alert on high database CPU
   aws cloudwatch put-metric-alarm \
       --alarm-name wof-db-high-cpu \
       --alarm-description "Alert when DB CPU exceeds 80%" \
       --metric-name CPUUtilization \
       --namespace AWS/RDS \
       --statistic Average \
       --period 300 \
       --threshold 80 \
       --comparison-operator GreaterThanThreshold \
       --evaluation-periods 2
   ```

---

## Part 5: Ongoing Operations

### Updating the Application

To deploy code changes:

1. Make your changes to `main.py` or other files
2. Run the deployment script:
   ```bash
   chmod +x scripts/deploy.sh
   ./scripts/deploy.sh
   ```

Or manually:
```bash
docker build -t wof-api-service:latest .
docker tag wof-api-service:latest $ECR_REPO_URL:latest
docker push $ECR_REPO_URL:latest
# App Runner will auto-deploy if enabled
```

### Updating WOF Data

To refresh with latest WOF data:

```bash
python import_wof_data.py --regions US --skip-download=false
```

### Scaling the Service

**To scale the database:**
```bash
cd terraform
# Edit terraform.tfvars and change db_instance_type
# Options: db.t3.small, db.t3.medium, db.t3.large, db.r6g.large, etc.
terraform apply
```

**To scale the API:**
```bash
cd terraform
# Edit apprunner.tf and change instance_configuration cpu/memory
terraform apply
```

### Backup and Recovery

**Manual backup:**
```bash
aws rds create-db-snapshot \
    --db-instance-identifier wof-postgis-db \
    --db-snapshot-identifier wof-manual-backup-$(date +%Y%m%d)
```

**Restore from backup:**
```bash
# List snapshots
aws rds describe-db-snapshots --db-instance-identifier wof-postgis-db

# Restore
aws rds restore-db-instance-from-db-snapshot \
    --db-instance-identifier wof-postgis-db-restored \
    --db-snapshot-identifier SNAPSHOT_ID
```

---

## Part 6: Deploying to Kubernetes (Alternative)

If you prefer to run the API on Kubernetes instead of App Runner, use the manifests under `k8s/`.

1. **Build & push the Docker image** to a registry reachable by your cluster:
   ```bash
   docker build -t whosonfirst-api:latest .
   docker tag whosonfirst-api:latest ghcr.io/YOUR_ORG/whosonfirst-api:<tag>
   docker push ghcr.io/YOUR_ORG/whosonfirst-api:<tag>
   ```

2. **Configure runtime settings**:
   - Edit `k8s/configmap.yaml` with the correct PostGIS endpoint and pool sizing
   - Create `k8s/secret.yaml` (copy from `secret.example.yaml`) or run `kubectl create secret generic wof-api-secrets ...` with your DB credentials
   - Update `k8s/deployment.yaml` to reference the pushed container image and add any `imagePullSecrets`

3. **Apply the manifests** (requires `kubectl` and an accessible cluster):
   ```bash
   kubectl apply -k k8s
   kubectl -n wof-api rollout status deploy/wof-api
   ```

4. **Expose the service**:
   - Use the provided `ingress.yaml` with your ingress controller and host, or
   - Change `service.yaml` to `type: LoadBalancer` on managed clouds

5. **Verify**:
   ```bash
   kubectl -n wof-api port-forward svc/wof-api 8080:80
   curl http://localhost:8080/health
   ```

For more detailed guidance and operational tips see `k8s/README.md`.

---

## Cost Estimates (Production-Low)

### Monthly AWS Costs (approximate):

- **RDS db.t3.small** (50GB gp3 storage): ~$35/month
- **App Runner** (1 vCPU, 2GB RAM, low traffic): ~$25/month
- **Data Transfer**: ~$5/month
- **ECR Storage**: ~$1/month
- **CloudWatch Logs**: ~$5/month

**Total: ~$70-80/month**

### Cost Optimization Tips:
- Use Reserved Instances for RDS (40% savings)
- Enable storage autoscaling only when needed
- Use CloudWatch to monitor and adjust resources
- Delete old ECR images (automated with lifecycle policy)

---

## Troubleshooting

### Database Connection Issues

**Error: "could not connect to server"**
```bash
# Check security groups
aws ec2 describe-security-groups --group-ids sg-xxx

# Verify VPC connector is attached
cd terraform
terraform output vpc_connector_arn
```

### App Runner Deployment Failures

**Check logs:**
```bash
aws apprunner list-operations \
    --service-arn $(cd terraform && terraform output -raw apprunner_service_arn) \
    --region $AWS_REGION
```

**Common issues:**
- Image not found in ECR: Re-push the image
- Database connection timeout: Check security groups and VPC connector
- Out of memory: Increase memory in apprunner.tf

### Data Import Errors

**Error: "Connection refused"**
- Check if database endpoint is correct
- Verify security group allows your IP
- Try adding your IP temporarily:
  ```bash
  aws ec2 authorize-security-group-ingress \
      --group-id sg-xxx \
      --protocol tcp \
      --port 5432 \
      --cidr YOUR_IP/32
  ```

### Query Performance Issues

**Slow queries?**
```sql
-- Check if indexes exist
SELECT indexname, tablename FROM pg_indexes WHERE tablename = 'whosonfirst';

-- Analyze query performance
EXPLAIN ANALYZE
SELECT * FROM whosonfirst
WHERE ST_Contains(geom, ST_MakePoint(-122.4194, 37.7749));
```

---

## Security Best Practices

1. **Database Credentials:**
   - Use AWS Secrets Manager (recommended for production)
   - Rotate passwords regularly
   - Never commit credentials to git

2. **Network Security:**
   - Keep RDS in private subnets
   - Use VPC connector for App Runner
   - Restrict security groups to minimum required access

3. **API Security:**
   - Add API authentication (e.g., API keys, OAuth)
   - Implement rate limiting
   - Use AWS WAF for DDoS protection

4. **Monitoring:**
   - Enable CloudWatch alarms
   - Monitor RDS Performance Insights
   - Set up AWS GuardDuty for threat detection

---

## Additional Resources

- [Who's On First Documentation](https://github.com/whosonfirst/whosonfirst-data)
- [PostGIS Documentation](https://postgis.net/documentation/)
- [AWS App Runner Documentation](https://docs.aws.amazon.com/apprunner/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)

---

## Support

For issues with:
- **Who's On First data**: https://github.com/whosonfirst/whosonfirst-data/issues
- **This deployment**: Check the troubleshooting section above
- **AWS services**: https://aws.amazon.com/support/

---

**Deployment complete! 🎉**

Your Who's On First API is now running in the cloud and ready to serve geographic hierarchy queries.
