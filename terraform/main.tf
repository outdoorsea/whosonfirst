# Terraform Configuration for Who's on First (WOF) Cloud Infrastructure

# --- AWS Provider Configuration ---
provider "aws" {
  region = var.aws_region
}

# --- Variables ---
variable "aws_region" {
  description = "The AWS region to deploy resources in."
  type        = string
  default     = "us-east-1" # You can change this to your preferred region
}

variable "db_name" {
  description = "The name of the PostgreSQL database."
  type        = string
  default     = "wof"
}

variable "db_user" {
  description = "The username for the PostgreSQL database."
  type        = string
  default     = "wofadmin"
}

variable "db_password" {
  description = "The password for the PostgreSQL database."
  type        = string
  sensitive   = true # Mark as sensitive to prevent logging
}

variable "db_instance_type" {
  description = "The EC2 instance type for the RDS database."
  type        = string
  default     = "db.t3.small" # Cost-effective for production-low workload
}

variable "db_allocated_storage" {
  description = "The allocated storage in GB for the RDS database."
  type        = number
  default     = 50 # Start smaller, can be increased later
}

variable "db_max_allocated_storage" {
  description = "Maximum storage for autoscaling in GB."
  type        = number
  default     = 200 # Allow autoscaling up to 200GB
}

variable "vpc_id" {
  description = "The ID of the VPC to deploy the RDS instance into."
  type        = string
  # You will need to provide your existing VPC ID here
}

variable "subnet_ids" {
  description = "A list of subnet IDs for the RDS instance (at least two for multi-AZ)."
  type        = list(string)
  # You will need to provide your existing subnet IDs here
}

# --- Security Group for RDS ---
resource "aws_security_group" "wof_db_sg" {
  name        = "wof-db-security-group"
  description = "Allow inbound traffic to WOF PostGIS DB"
  vpc_id      = var.vpc_id

  ingress {
    description = "Allow traffic from Lilypad API (adjust source as needed)"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    # IMPORTANT: Restrict this to your Lilypad API's security group or VPC CIDR
    # For testing, you might temporarily use your IP or a broader CIDR, but restrict it for production.
    cidr_blocks = ["0.0.0.0/0"] # Placeholder: REPLACE WITH YOUR LILYPAD API'S CIDR OR SECURITY GROUP ID
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "wof-db-sg"
  }
}

# --- RDS Subnet Group ---
resource "aws_db_subnet_group" "wof_db_subnet_group" {
  name       = "wof-db-subnet-group"
  subnet_ids = var.subnet_ids

  tags = {
    Name = "wof-db-subnet-group"
  }
}

# --- AWS RDS PostgreSQL Instance with PostGIS ---
resource "aws_db_instance" "wof_postgis_db" {
  allocated_storage       = var.db_allocated_storage
  max_allocated_storage   = var.db_max_allocated_storage
  engine                  = "postgres"
  engine_version          = "15.5" # Latest version supporting PostGIS
  instance_class          = var.db_instance_type
  db_name                 = var.db_name
  username                = var.db_user
  password                = var.db_password
  parameter_group_name    = "default.postgres15"
  skip_final_snapshot     = false # Create snapshot on deletion
  final_snapshot_identifier = "wof-db-final-snapshot-${formatdate("YYYY-MM-DD-hhmm", timestamp())}"
  publicly_accessible     = false
  vpc_security_group_ids  = [aws_security_group.wof_db_sg.id]
  db_subnet_group_name    = aws_db_subnet_group.wof_db_subnet_group.name
  multi_az                = false # Single AZ for production-low to save costs
  storage_type            = "gp3" # gp3 is more cost-effective than gp2
  storage_encrypted       = true
  backup_retention_period = 7 # Keep backups for 7 days
  backup_window          = "03:00-04:00" # Daily backup window (UTC)
  maintenance_window     = "Mon:04:00-Mon:05:00" # Weekly maintenance window

  # Performance insights for monitoring
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]

  # Deletion protection for production
  deletion_protection = true

  tags = {
    Name        = "wof-postgis-db"
    Environment = "production"
    Service     = "whosonfirst"
  }

  lifecycle {
    ignore_changes = [final_snapshot_identifier]
  }
}

# --- Outputs ---
output "db_endpoint" {
  description = "The endpoint of the RDS database."
  value       = aws_db_instance.wof_postgis_db.address
}

output "db_port" {
  description = "The port of the RDS database."
  value       = aws_db_instance.wof_postgis_db.port
}

output "db_username" {
  description = "The username for the RDS database."
  value       = aws_db_instance.wof_postgis_db.username
}

output "db_name" {
  description = "The name of the RDS database."
  value       = aws_db_instance.wof_postgis_db.db_name
}

# --- Optional: AWS App Runner for FastAPI Service Deployment ---
# This section is commented out as it requires more context (e.g., ECR repo, build commands)
# but provides a starting point for deploying the FastAPI app.

/*
resource "aws_apprunner_service" "wof_api_apprunner" {
  service_name = "wof-api-service"

  source_configuration {
    image_repository {
      image_identifier      = "public.ecr.aws/aws-apprunner/python:3.9" # Placeholder: Replace with your ECR image
      image_repository_type = "ECR_PUBLIC" # Or "ECR" for private repo

      # If using a private ECR, you'll need an instance_configuration with access role
    }
    auto_deployments_enabled = false # Set to true for automatic deployments on image push

    # For a custom Dockerfile, you'd use a code_repository block
    # code_repository {
    #   repository_url = "https://github.com/your-org/your-repo"
    #   source_code_version {
    #     type  = "BRANCH"
    #     value = "main"
    #   }
    #   code_configuration {
    #     configuration_source = "API" # Or "REPOSITORY" if apprunner.yaml is in repo
    #     runtime              = "python"
    #     build_command        = "pip install -r requirements.txt"
    #     start_command        = "uvicorn main:app --host 0.0.0.0 --port 8000"
    #     port                 = "8000"
    #   }
    # }
  }

  instance_configuration {
    cpu    = "1024" # 1 vCPU
    memory = "2048" # 2 GB
  }

  health_check_configuration {
    protocol = "HTTP"
    path     = "/health"
    interval = 10
    timeout  = 5
    healthy_threshold = 1
    unhealthy_threshold = 5
  }

  tags = {
    Name = "wof-api-service"
  }
}

output "apprunner_service_url" {
  description = "The URL of the App Runner service."
  value       = aws_apprunner_service.wof_api_apprunner.service_url
}
*/
