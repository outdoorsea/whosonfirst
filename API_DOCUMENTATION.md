# Who's On First API Documentation

## Base URL
```
http://localhost:2000
```

## Overview

The Who's On First API provides geocoding services to resolve geographic coordinates into administrative hierarchies using the Who's On First (WOF) gazetteer dataset. The API currently contains **258,937 places** across the United States.

## Interactive Documentation

FastAPI provides interactive API documentation:
- **Swagger UI**: http://localhost:2000/docs
- **ReDoc**: http://localhost:2000/redoc
- **OpenAPI Schema**: http://localhost:2000/openapi.json

---

## Authentication

All `/api/v1/*` endpoints require a Bearer token in the `Authorization` header:

```bash
curl -H "Authorization: Bearer wof_<your-token>" \
  "http://localhost:2000/api/v1/hierarchy?lat=37.7749&lon=-122.4194"
```

Tokens are issued via the admin page at `/admin` (HTTP Basic auth, configured
with `ADMIN_USERNAME` / `ADMIN_PASSWORD` env vars). The admin page lists all
tokens with usage counts and lets you create or revoke tokens. A token's
plaintext value is shown only once at creation time — only its sha256 hash is
stored.

The `/health` and `/` endpoints remain public.

Auth failures return `401 Unauthorized` with `WWW-Authenticate: Bearer`.

---

## Endpoints

### 1. Get Geographic Hierarchy by Coordinates

Resolve latitude/longitude coordinates to their corresponding administrative hierarchy.

**Endpoint:** `GET /api/v1/hierarchy`

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `lat` | float | Yes | Latitude (-90 to 90) |
| `lon` | float | Yes | Longitude (-180 to 180) |

**Response Schema:**
```json
{
  "continent": {
    "id": integer,
    "name": "string",
    "placetype": "string"
  } | null,
  "country": { ... } | null,
  "region": { ... } | null,
  "county": { ... } | null,
  "locality": { ... } | null,
  "neighbourhood": { ... } | null
}
```

**Example Request:**
```bash
# San Francisco, CA
curl "http://localhost:2000/api/v1/hierarchy?lat=37.7749&lon=-122.4194"

# New York City
curl "http://localhost:2000/api/v1/hierarchy?lat=40.7128&lon=-74.0060"

# Vinton, OH
curl "http://localhost:2000/api/v1/hierarchy?lat=38.977570&lon=-82.337409"
```

**Example Response (San Francisco):**
```json
{
  "continent": null,
  "country": null,
  "region": null,
  "county": null,
  "locality": {
    "id": 85922583,
    "name": "San Francisco",
    "placetype": "locality"
  },
  "neighbourhood": null
}
```

**HTTP Status Codes:**
- `200 OK` - Success
- `400 Bad Request` - Invalid coordinates
- `500 Internal Server Error` - Server error
- `503 Service Unavailable` - Database unavailable

---

### 2. Get Place by ID

Retrieve detailed information about a specific Who's On First place by its ID.

**Endpoint:** `GET /api/v1/place/{wof_id}`

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `wof_id` | integer | Yes | Who's On First place ID |

**Response Schema:**
```json
{
  "id": integer,
  "name": "string",
  "placetype": "string",
  "parent_id": integer | null,
  "properties": {
    // Full WOF properties including:
    // - Hierarchy information
    // - Geometric data (bbox, centroid)
    // - Names in multiple languages
    // - Population statistics
    // - External concordances (Wikidata, GeoNames, etc.)
    // - And much more...
  }
}
```

**Example Request:**
```bash
# Get San Francisco
curl "http://localhost:2000/api/v1/place/85922583"

# Get Alaska Congressional District
curl "http://localhost:2000/api/v1/place/1108737357"

# Get Vinton, OH
curl "http://localhost:2000/api/v1/place/101711873"
```

**Example Response (Vinton, OH - truncated):**
```json
{
  "id": 101711873,
  "name": "Vinton",
  "placetype": "locality",
  "parent_id": 404524595,
  "properties": {
    "wof:id": 101711873,
    "wof:name": "Vinton",
    "wof:placetype": "locality",
    "wof:country": "US",
    "wof:hierarchy": [
      {
        "continent_id": 102191575,
        "country_id": 85633793,
        "region_id": 85688485,
        "county_id": 102083675,
        "localadmin_id": 404524595,
        "locality_id": 101711873
      }
    ],
    "wof:parent_id": 404524595,
    "wof:population": 222,
    "geom:latitude": 38.97757,
    "geom:longitude": -82.337409,
    "geom:bbox": "-82.350061,38.969332,-82.326371,38.98621",
    "iso:country": "US",
    "lbl:latitude": 38.977868,
    "lbl:longitude": -82.337402,
    "name:eng_x_preferred": ["Vinton"],
    "qs:a0": "United States",
    "qs:a1": "*Ohio",
    "wof:concordances": {
      "gn:id": 4527247,
      "wd:id": "Q2186359",
      "uscensus:geoid": "3980178"
    }
  }
}
```

**HTTP Status Codes:**
- `200 OK` - Success
- `404 Not Found` - Place ID not found
- `500 Internal Server Error` - Server error
- `503 Service Unavailable` - Database unavailable

---

### 3. Health Check

Check the health status of the API and database connection.

**Endpoint:** `GET /health`

**Response Schema:**
```json
{
  "status": "ok" | "degraded",
  "service": "wof-api",
  "database": "healthy" | "unhealthy" | "unavailable",
  "error": "string" // Optional, only present if there's an error
}
```

**Example Request:**
```bash
curl "http://localhost:2000/health"
```

**Example Response:**
```json
{
  "status": "ok",
  "service": "wof-api",
  "database": "healthy"
}
```

**HTTP Status Codes:**
- `200 OK` - Always returns 200, check `status` field for actual health

---

## Data Coverage

### Place Types Available

The database contains the following place types for the United States:

| Place Type | Count | Description |
|------------|-------|-------------|
| Locality | 179,570 | Cities, towns, villages |
| Neighbourhood | 40,263 | Neighborhoods and districts |
| Localadmin | 19,769 | Townships, local administrative areas |
| Campus | 8,073 | University campuses, facilities |
| Constituency | 7,194 | Congressional & state legislative districts |
| County | 3,143 | County boundaries |
| Microhood | 263 | Micro-neighborhoods |
| Marketarea | 210 | Designated market areas |
| Macrohood | 24 | Macro-neighborhoods |
| Borough | 4 | NYC boroughs and similar |

### Geographic Coverage
- **Region**: United States
- **Total Places**: 258,937
- **Data Source**: Who's On First (WOF) via geocode.earth
- **Last Updated**: 2024

---

## Use Cases

### 1. Reverse Geocoding
Convert coordinates to place names:
```bash
# Where am I?
curl "http://localhost:2000/api/v1/hierarchy?lat=40.7589&lon=-73.9851"
```

### 2. Address Enrichment
Given a coordinate from an address geocoder, get the full administrative hierarchy:
```bash
# Get full hierarchy for a delivery address
curl "http://localhost:2000/api/v1/hierarchy?lat=37.7749&lon=-122.4194"
```

### 3. Electoral District Lookup
Find which congressional district a coordinate falls within:
```bash
# Get place details including constituency
curl "http://localhost:2000/api/v1/hierarchy?lat=37.7749&lon=-122.4194"
# Then lookup constituency by exploring the database
```

### 4. Campus Location
Identify if coordinates are within a university campus:
```bash
# Check if coordinates are on a campus
curl "http://localhost:2000/api/v1/hierarchy?lat=37.8719&lon=-122.2585"
```

### 5. Property Data Enrichment
Enrich real estate listings with neighborhood and administrative data:
```bash
# Get neighborhood and locality for a property
curl "http://localhost:2000/api/v1/hierarchy?lat=40.7489&lon=-73.9680"
```

---

## Rate Limiting

Currently, there are no rate limits on the local API. If deploying to production, consider implementing:
- Rate limiting per IP address
- API key authentication
- Request throttling

---

## Error Handling

### Common Errors

**Invalid Coordinates (400)**
```json
{
  "detail": "Invalid latitude or longitude."
}
```

**Place Not Found (404)**
```json
{
  "detail": "Place with ID 999999999 not found"
}
```

**Database Connection Error (503)**
```json
{
  "detail": "Database connection pool not available"
}
```

**Internal Server Error (500)**
```json
{
  "detail": "An internal error occurred: [error details]"
}
```

---

## Performance

### Response Times
- **Hierarchy lookup**: 50-200ms (depends on complexity)
- **Place by ID**: 10-50ms (indexed query)
- **Health check**: <10ms

### Optimization Tips
1. **Use connection pooling** - Already configured (1-10 connections)
2. **Enable query caching** - Can be added with Redis
3. **Add read replicas** - For high-traffic scenarios
4. **Use CDN caching** - For static lookups

---

## Development & Testing

### Testing with curl
```bash
# Test hierarchy endpoint
curl -X GET "http://localhost:2000/api/v1/hierarchy?lat=37.7749&lon=-122.4194" \
  -H "accept: application/json"

# Test place lookup
curl -X GET "http://localhost:2000/api/v1/place/85922583" \
  -H "accept: application/json"

# Test health check
curl -X GET "http://localhost:2000/health" \
  -H "accept: application/json"
```

### Testing with Python
```python
import requests

# Get hierarchy
response = requests.get(
    "http://localhost:2000/api/v1/hierarchy",
    params={"lat": 37.7749, "lon": -122.4194}
)
print(response.json())

# Get place by ID
response = requests.get("http://localhost:2000/api/v1/place/85922583")
print(response.json())
```

### Testing with JavaScript
```javascript
// Get hierarchy
fetch('http://localhost:2000/api/v1/hierarchy?lat=37.7749&lon=-122.4194')
  .then(response => response.json())
  .then(data => console.log(data));

// Get place by ID
fetch('http://localhost:2000/api/v1/place/85922583')
  .then(response => response.json())
  .then(data => console.log(data));
```

---

## Database Schema

### Main Table: `whosonfirst`

| Column | Type | Description |
|--------|------|-------------|
| `id` | BIGINT | WOF place ID (primary key) |
| `parent_id` | BIGINT | Parent place ID |
| `name` | TEXT | Place name |
| `placetype` | VARCHAR(50) | Type of place |
| `country_code` | VARCHAR(2) | ISO country code |
| `properties` | JSONB | Full WOF properties |
| `geom` | GEOMETRY | PostGIS geometry (polygon/multipolygon) |

### Indexes
- Primary key on `id`
- GIST spatial index on `geom` (for fast point-in-polygon queries)
- B-tree index on `placetype`
- B-tree index on `parent_id`

---

## Deployment Considerations

### Environment Variables
```bash
DB_HOST=localhost          # Database host
DB_PORT=5432              # Database port
DB_NAME=wof               # Database name
DB_USER=user              # Database user
DB_PASS=password          # Database password
DB_MIN_CONNECTIONS=1      # Min connection pool size
DB_MAX_CONNECTIONS=10     # Max connection pool size
```

### Docker Deployment
```bash
# Build and start services
docker-compose up -d

# View logs
docker-compose logs -f wof-api

# Stop services
docker-compose down
```

### Production Deployment
See `DEPLOYMENT_GUIDE.md` for AWS deployment instructions.

---

## Support & Resources

- **FastAPI Documentation**: https://fastapi.tiangolo.com/
- **Who's On First**: https://whosonfirst.org/
- **PostGIS Documentation**: https://postgis.net/documentation/
- **OpenAPI Specification**: http://localhost:2000/openapi.json

---

## Version History

### v1.0.0 (Current)
- Initial release
- 258,937 US places
- 3 endpoints (hierarchy, place lookup, health)
- PostgreSQL + PostGIS backend
- Connection pooling
- Comprehensive error handling

---

## License

This API uses Who's On First data, which is licensed under [Creative Commons Zero](https://creativecommons.org/publicdomain/zero/1.0/).
