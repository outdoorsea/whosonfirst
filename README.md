# Who's On First Cloud API

A production-ready FastAPI service for querying Who's On First geographic data using PostGIS.

## Features

- 🌍 **Geographic Hierarchy Resolution**: Convert lat/lon coordinates to administrative hierarchies
- 🔍 **Place Lookup**: Query places by Who's On First ID
- 🚀 **Production-Ready**: Connection pooling, error handling, health checks
- ☁️ **Cloud-Native**: Containerized and ready for AWS deployment
- 📊 **Spatial Indexing**: Optimized PostGIS queries with spatial indexes

## Quick Start

### Local Development

1. **Start the services:**
   ```bash
   docker-compose up -d
   ```

2. **Import sample data:**
   ```bash
   pip install -r requirements.txt
   python import_wof_data.py --regions US --placetypes locality neighbourhood
   ```

3. **Access the API:**
   - API: http://localhost:2000
   - Docs: http://localhost:2000/docs
   - Health: http://localhost:2000/health

### Cloud Deployment (AWS)

See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for complete instructions.

**Quick deploy:**
```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your AWS settings
terraform init
terraform apply
cd ..
chmod +x scripts/deploy.sh
./scripts/deploy.sh
```

## API Endpoints

### GET `/api/v1/hierarchy`
Resolve coordinates to geographic hierarchy.

**Query Parameters:**
- `lat` (float): Latitude (-90 to 90)
- `lon` (float): Longitude (-180 to 180)

**Example:**
```bash
curl "http://localhost:2000/api/v1/hierarchy?lat=37.7749&lon=-122.4194"
```

**Response:**
```json
{
  "continent": {"id": 102191581, "name": "North America", "placetype": "continent"},
  "country": {"id": 85633793, "name": "United States", "placetype": "country"},
  "region": {"id": 85688637, "name": "California", "placetype": "region"},
  "locality": {"id": 85922583, "name": "San Francisco", "placetype": "locality"}
}
```

### GET `/api/v1/place/{wof_id}`
Get place details by Who's On First ID.

**Example:**
```bash
curl "http://localhost:2000/api/v1/place/85922583"
```

### GET `/health`
Health check with database connectivity test.

**Example:**
```bash
curl "http://localhost:2000/health"
```

**📖 For complete API documentation, see [API_DOCUMENTATION.md](API_DOCUMENTATION.md)**

## Project Structure

```
.
├── main.py                     # FastAPI application
├── import_wof_data.py         # Data import script
├── requirements.txt           # Python dependencies
├── Dockerfile                 # Container image
├── docker-compose.yml         # Local development setup
├── .env.example               # Environment configuration template
├── DEPLOYMENT_GUIDE.md        # Complete deployment guide
├── terraform/                 # Infrastructure as Code
│   ├── main.tf               # Main infrastructure
│   ├── apprunner.tf          # API service deployment
│   └── terraform.tfvars.example
└── scripts/
    └── deploy.sh             # Deployment automation
```

## Configuration

Environment variables (see `.env.example`):

- `DB_HOST`: PostgreSQL host
- `DB_PORT`: PostgreSQL port (default: 5432)
- `DB_NAME`: Database name (default: wof)
- `DB_USER`: Database username
- `DB_PASS`: Database password
- `DB_MIN_CONNECTIONS`: Min connection pool size (default: 1)
- `DB_MAX_CONNECTIONS`: Max connection pool size (default: 10)

## Data Import

The `import_wof_data.py` script downloads and imports Who's On First GeoJSON data.

### Quick Start

**Initial import (US data):**
```bash
python import_wof_data.py --regions US --placetypes locality neighbourhood
```

**Add new regions (safe, won't touch existing data):**
```bash
python import_wof_data.py --regions CA GB FR --placetypes locality neighbourhood
```

**Update existing data with latest WOF changes:**
```bash
python import_wof_data.py --regions US CA GB FR --update
```

### Import Modes

- **INSERT mode (default)**: Adds new records, skips existing ones
  - Use for: Initial imports, adding new regions

- **UPDATE mode (`--update`)**: Updates existing records + adds new ones
  - Use for: Refreshing data with latest changes from WOF

See [DATA_MANAGEMENT.md](DATA_MANAGEMENT.md) for complete data import workflows and examples.

## Tech Stack

- **FastAPI**: Modern Python web framework
- **PostgreSQL**: Relational database
- **PostGIS**: Spatial database extension
- **psycopg2**: PostgreSQL adapter
- **Shapely**: Geometric operations
- **Docker**: Containerization
- **Terraform**: Infrastructure as Code
- **AWS**: Cloud platform (RDS, App Runner, ECR)

## Cost Estimate (Production-Low)

Approximate monthly costs on AWS:
- RDS db.t3.small (50GB): ~$35
- App Runner (1 vCPU, 2GB): ~$25
- Data transfer & storage: ~$10
- **Total: ~$70/month**

See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for cost optimization tips.

## Development

**Run tests:**
```bash
# TODO: Add tests
pytest
```

**Format code:**
```bash
black main.py import_wof_data.py
```

**Type checking:**
```bash
mypy main.py
```

## Documentation

- **[API_DOCUMENTATION.md](API_DOCUMENTATION.md)** - Complete API reference with examples
- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - Complete deployment instructions
- [DATA_MANAGEMENT.md](DATA_MANAGEMENT.md) - Data import and management guide
- [WOF_CLOUD_SETUP.md](WOF_CLOUD_SETUP.md) - Cloud setup background
- [CLOUD_DEPLOYMENT_GUIDANCE.md](CLOUD_DEPLOYMENT_GUIDANCE.md) - AWS specifics

## Resources

- [Who's On First](https://www.whosonfirst.org/) - Project website
- [WOF Data](https://github.com/whosonfirst/whosonfirst-data) - Data repository
- [PostGIS](https://postgis.net/) - Spatial database
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework

## License

See Who's On First licensing at: https://www.whosonfirst.org/docs/licenses/

## Support

For issues or questions:
1. Check [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) troubleshooting section
2. Review [WOF documentation](https://github.com/whosonfirst/whosonfirst-data)
3. Check application logs and CloudWatch metrics

---

Made with ❤️ using Who's On First data
