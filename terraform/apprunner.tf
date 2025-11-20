# App Runner and ECR Configuration for WOF API Service
# This file contains optional resources for deploying the API service

# --- ECR Repository for Docker Images ---
resource "aws_ecr_repository" "wof_api" {
  name                 = "wof-api-service"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = {
    Name        = "wof-api-repository"
    Environment = "production"
    Service     = "whosonfirst"
  }
}

# --- ECR Lifecycle Policy to Clean Up Old Images ---
resource "aws_ecr_lifecycle_policy" "wof_api_lifecycle" {
  repository = aws_ecr_repository.wof_api.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 10 images"
      selection = {
        tagStatus     = "any"
        countType     = "imageCountMoreThan"
        countNumber   = 10
      }
      action = {
        type = "expire"
      }
    }]
  })
}

# --- IAM Role for App Runner ---
resource "aws_iam_role" "apprunner_instance_role" {
  name = "wof-apprunner-instance-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "tasks.apprunner.amazonaws.com"
      }
    }]
  })

  tags = {
    Name        = "wof-apprunner-instance-role"
    Environment = "production"
  }
}

# --- IAM Role for App Runner to Access ECR ---
resource "aws_iam_role" "apprunner_ecr_access_role" {
  name = "wof-apprunner-ecr-access-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "build.apprunner.amazonaws.com"
      }
    }]
  })

  tags = {
    Name        = "wof-apprunner-ecr-access-role"
    Environment = "production"
  }
}

resource "aws_iam_role_policy_attachment" "apprunner_ecr_access" {
  role       = aws_iam_role.apprunner_ecr_access_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess"
}

# --- VPC Connector for App Runner to Access RDS ---
resource "aws_apprunner_vpc_connector" "wof_vpc_connector" {
  vpc_connector_name = "wof-vpc-connector"
  subnets            = var.subnet_ids
  security_groups    = [aws_security_group.wof_apprunner_sg.id]

  tags = {
    Name        = "wof-vpc-connector"
    Environment = "production"
  }
}

# --- Security Group for App Runner ---
resource "aws_security_group" "wof_apprunner_sg" {
  name        = "wof-apprunner-sg"
  description = "Security group for WOF App Runner service"
  vpc_id      = var.vpc_id

  egress {
    description = "Allow all outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "wof-apprunner-sg"
    Environment = "production"
  }
}

# --- Update RDS Security Group to Allow App Runner Access ---
resource "aws_security_group_rule" "allow_apprunner_to_rds" {
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.wof_db_sg.id
  source_security_group_id = aws_security_group.wof_apprunner_sg.id
  description              = "Allow App Runner to access RDS"
}

# --- App Runner Service ---
# Note: This resource requires the Docker image to be pushed to ECR first
# Uncomment and apply after pushing your first image

# resource "aws_apprunner_service" "wof_api" {
#   service_name = "wof-api-service"
#
#   source_configuration {
#     image_repository {
#       image_identifier      = "${aws_ecr_repository.wof_api.repository_url}:latest"
#       image_repository_type = "ECR"
#       image_configuration {
#         port = "8000"
#         runtime_environment_variables = {
#           DB_HOST            = aws_db_instance.wof_postgis_db.address
#           DB_PORT            = tostring(aws_db_instance.wof_postgis_db.port)
#           DB_NAME            = var.db_name
#           DB_USER            = var.db_user
#           DB_PASS            = var.db_password
#           DB_MIN_CONNECTIONS = "2"
#           DB_MAX_CONNECTIONS = "10"
#         }
#       }
#     }
#     authentication_configuration {
#       access_role_arn = aws_iam_role.apprunner_ecr_access_role.arn
#     }
#     auto_deployments_enabled = true
#   }
#
#   instance_configuration {
#     cpu    = "1024"  # 1 vCPU
#     memory = "2048"  # 2 GB
#     instance_role_arn = aws_iam_role.apprunner_instance_role.arn
#   }
#
#   network_configuration {
#     egress_configuration {
#       egress_type       = "VPC"
#       vpc_connector_arn = aws_apprunner_vpc_connector.wof_vpc_connector.arn
#     }
#   }
#
#   health_check_configuration {
#     protocol            = "HTTP"
#     path                = "/health"
#     interval            = 10
#     timeout             = 5
#     healthy_threshold   = 1
#     unhealthy_threshold = 5
#   }
#
#   tags = {
#     Name        = "wof-api-service"
#     Environment = "production"
#     Service     = "whosonfirst"
#   }
# }

# --- Outputs ---
output "ecr_repository_url" {
  description = "The URL of the ECR repository"
  value       = aws_ecr_repository.wof_api.repository_url
}

# output "apprunner_service_url" {
#   description = "The URL of the App Runner service"
#   value       = aws_apprunner_service.wof_api.service_url
# }

output "vpc_connector_arn" {
  description = "The ARN of the VPC connector"
  value       = aws_apprunner_vpc_connector.wof_vpc_connector.arn
}
