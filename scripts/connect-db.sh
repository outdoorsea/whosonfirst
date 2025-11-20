#!/bin/bash
# Quick database connection script

set -e

# Load environment variables if .env exists
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Try to get from Terraform if not in env
if [ -z "$DB_HOST" ] && [ -d "terraform" ]; then
    cd terraform
    DB_HOST=$(terraform output -raw db_endpoint 2>/dev/null || echo "localhost")
    cd ..
fi

DB_HOST=${DB_HOST:-localhost}
DB_PORT=${DB_PORT:-5432}
DB_NAME=${DB_NAME:-wof}
DB_USER=${DB_USER:-user}

echo "Connecting to PostgreSQL..."
echo "Host: $DB_HOST"
echo "Port: $DB_PORT"
echo "Database: $DB_NAME"
echo "User: $DB_USER"
echo ""

PGPASSWORD=$DB_PASS psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME
