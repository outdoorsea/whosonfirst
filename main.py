import os
import secrets
import hashlib
import logging
import html as html_lib
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends, Request, Form, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials, HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Configuration ---
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "wof")
DB_USER = os.getenv("DB_USER", "user")
DB_PASS = os.getenv("DB_PASS", "password")
DB_MIN_CONNECTIONS = int(os.getenv("DB_MIN_CONNECTIONS", "1"))
DB_MAX_CONNECTIONS = int(os.getenv("DB_MAX_CONNECTIONS", "10"))

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

TOKEN_PREFIX = "wof_"

# Global connection pool
connection_pool = None


AUTH_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS api_tokens (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    token_prefix TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS api_token_usage (
    id BIGSERIAL PRIMARY KEY,
    token_id INTEGER NOT NULL REFERENCES api_tokens(id) ON DELETE CASCADE,
    endpoint TEXT NOT NULL,
    called_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_token_usage_token_id ON api_token_usage(token_id);
CREATE INDEX IF NOT EXISTS idx_token_usage_called_at ON api_token_usage(called_at DESC);
"""


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI application.
    Manages connection pool lifecycle.
    """
    global connection_pool

    # Startup: Create connection pool
    try:
        logger.info("Creating database connection pool...")
        connection_pool = pool.ThreadedConnectionPool(
            DB_MIN_CONNECTIONS,
            DB_MAX_CONNECTIONS,
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASS,
            cursor_factory=RealDictCursor
        )
        logger.info(f"Connection pool created: {DB_MIN_CONNECTIONS}-{DB_MAX_CONNECTIONS} connections")

        # Test connection and bootstrap auth schema
        conn = connection_pool.getconn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1;")
            logger.info("Database connection test successful")
            cursor.execute(AUTH_SCHEMA_SQL)
            conn.commit()
            logger.info("Auth schema verified")
            cursor.close()
        finally:
            connection_pool.putconn(conn)

        if not ADMIN_PASSWORD:
            logger.warning("ADMIN_PASSWORD is not set — /admin will reject all requests")

    except Exception as e:
        logger.error(f"Failed to create connection pool: {e}")
        raise

    yield

    # Shutdown: Close connection pool
    if connection_pool:
        logger.info("Closing database connection pool...")
        connection_pool.closeall()
        logger.info("Connection pool closed")


def get_db_connection():
    """
    Gets a connection from the pool.
    The connection is automatically returned to the pool when the request completes.
    """
    if not connection_pool:
        logger.error("Connection pool not initialized")
        raise HTTPException(status_code=503, detail="Database connection pool not available")

    try:
        conn = connection_pool.getconn()
        if conn:
            return conn
        else:
            logger.error("Failed to get connection from pool")
            raise HTTPException(status_code=503, detail="No database connections available")
    except pool.PoolError as e:
        logger.error(f"Connection pool error: {e}")
        raise HTTPException(status_code=503, detail="Database connection pool exhausted")
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        raise HTTPException(status_code=503, detail=f"Database connection failed: {str(e)}")

# --- Authentication ---
bearer_scheme = HTTPBearer(auto_error=False)
basic_scheme = HTTPBasic(auto_error=False)


def require_token(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> int:
    """Validate Bearer token, log usage, return token id."""
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header. Expected: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_hash = hash_token(creds.credentials)

    if not connection_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")

    conn = connection_pool.getconn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM api_tokens WHERE token_hash = %s AND revoked_at IS NULL",
            (token_hash,),
        )
        row = cursor.fetchone()
        if not row:
            cursor.close()
            raise HTTPException(
                status_code=401,
                detail="Invalid or revoked token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        token_id = row['id']
        cursor.execute(
            "INSERT INTO api_token_usage (token_id, endpoint) VALUES (%s, %s)",
            (token_id, request.url.path),
        )
        conn.commit()
        cursor.close()
        return token_id
    finally:
        connection_pool.putconn(conn)


def require_admin(
    creds: Optional[HTTPBasicCredentials] = Depends(basic_scheme),
) -> str:
    """HTTP Basic auth gate for /admin."""
    if not ADMIN_PASSWORD:
        raise HTTPException(
            status_code=503,
            detail="Admin disabled: ADMIN_PASSWORD environment variable not set",
        )
    if creds is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": 'Basic realm="admin"'},
        )
    user_ok = secrets.compare_digest(creds.username, ADMIN_USERNAME)
    pass_ok = secrets.compare_digest(creds.password, ADMIN_PASSWORD)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": 'Basic realm="admin"'},
        )
    return creds.username


# --- Pydantic Models for API Schema ---
class WOFRecord(BaseModel):
    id: int
    name: str
    placetype: str

class HierarchyResponse(BaseModel):
    continent: Optional[WOFRecord] = None
    country: Optional[WOFRecord] = None
    region: Optional[WOFRecord] = None
    county: Optional[WOFRecord] = None
    locality: Optional[WOFRecord] = None
    neighbourhood: Optional[WOFRecord] = None

# --- FastAPI Application ---
app = FastAPI(
    title="Who's on First API Service",
    description="A standalone service to resolve geographic coordinates to a WOF hierarchy.",
    version="1.0.0",
    lifespan=lifespan
)

# Mount static files for favicon
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
def landing_page():
    """
    Landing page explaining Who's On First and providing API links.
    """
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Who's On First API</title>
        <link rel="icon" type="image/png" sizes="16x16" href="/static/favicon-16x16.png">
        <link rel="icon" type="image/png" sizes="32x32" href="/static/favicon-32x32.png">
        <link rel="apple-touch-icon" sizes="180x180" href="/static/apple-touch-icon.png">
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                background: #f5f5f5;
            }
            .container {
                max-width: 900px;
                margin: 0 auto;
                padding: 40px 20px;
            }
            header {
                background: white;
                padding: 40px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                margin-bottom: 30px;
            }
            h1 {
                color: #2c3e50;
                margin-bottom: 20px;
                font-size: 2.5em;
            }
            h2 {
                color: #34495e;
                margin: 30px 0 15px;
                font-size: 1.5em;
            }
            .subtitle {
                color: #7f8c8d;
                font-size: 1.2em;
                margin-bottom: 20px;
            }
            .section {
                background: white;
                padding: 30px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                margin-bottom: 20px;
            }
            .stats {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin: 20px 0;
            }
            .stat-card {
                background: #ecf0f1;
                padding: 20px;
                border-radius: 6px;
                text-align: center;
            }
            .stat-number {
                font-size: 2em;
                font-weight: bold;
                color: #3498db;
            }
            .stat-label {
                color: #7f8c8d;
                margin-top: 5px;
            }
            .links {
                list-style: none;
                margin: 20px 0;
            }
            .links li {
                margin: 12px 0;
            }
            a {
                color: #3498db;
                text-decoration: none;
                font-weight: 500;
                transition: color 0.2s;
            }
            a:hover {
                color: #2980b9;
                text-decoration: underline;
            }
            .api-endpoint {
                background: #2c3e50;
                color: #ecf0f1;
                padding: 12px 16px;
                border-radius: 4px;
                font-family: 'Courier New', monospace;
                margin: 10px 0;
                overflow-x: auto;
            }
            .example {
                background: #f8f9fa;
                border-left: 4px solid #3498db;
                padding: 15px;
                margin: 15px 0;
            }
            footer {
                text-align: center;
                margin-top: 40px;
                color: #7f8c8d;
                padding: 20px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <h1>Who's On First API</h1>
                <p class="subtitle">Geographic hierarchy resolution service powered by Who's On First gazetteer data</p>
            </header>

            <div class="section">
                <h2>About Who's On First</h2>
                <p>
                    <strong>Who's On First</strong> (WOF) is a gazetteer of places - a comprehensive geographic database
                    covering countries, regions, cities, neighborhoods, and more. It's an open data project that provides
                    consistent, accurate place records with rich metadata and hierarchical relationships.
                </p>
                <p style="margin-top: 15px;">
                    This API provides a fast, production-ready service for resolving geographic coordinates to their
                    administrative hierarchies using Who's On First data.
                </p>
            </div>

            <div class="section">
                <h2>Database Statistics</h2>
                <div class="stats">
                    <div class="stat-card">
                        <div class="stat-number">300,767</div>
                        <div class="stat-label">Total Places</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">180,225</div>
                        <div class="stat-label">Localities</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">56,947</div>
                        <div class="stat-label">Neighbourhoods</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">7,194</div>
                        <div class="stat-label">Constituencies</div>
                    </div>
                </div>
            </div>

            <div class="section">
                <h2>API Endpoints</h2>

                <h3 style="margin-top: 20px;">Get Geographic Hierarchy</h3>
                <div class="api-endpoint">GET /api/v1/hierarchy?lat={latitude}&lon={longitude}</div>
                <div class="example">
                    <strong>Example:</strong><br>
                    <code>/api/v1/hierarchy?lat=37.7749&lon=-122.4194</code><br>
                    <span style="color: #7f8c8d;">Returns: continent, country, region, county, locality, and neighbourhood</span>
                </div>

                <h3 style="margin-top: 20px;">Get Place by ID</h3>
                <div class="api-endpoint">GET /api/v1/place/{wof_id}</div>
                <div class="example">
                    <strong>Example:</strong><br>
                    <code>/api/v1/place/85922583</code><br>
                    <span style="color: #7f8c8d;">Returns: Complete place details with properties and hierarchy</span>
                </div>

                <h3 style="margin-top: 20px;">Health Check</h3>
                <div class="api-endpoint">GET /health</div>
            </div>

            <div class="section">
                <h2>API Documentation</h2>
                <ul class="links">
                    <li><a href="/docs">📖 Interactive API Documentation (Swagger UI)</a></li>
                    <li><a href="/redoc">📚 Alternative Documentation (ReDoc)</a></li>
                    <li><a href="/openapi.json">🔧 OpenAPI Schema (JSON)</a></li>
                </ul>
            </div>

            <div class="section">
                <h2>Resources</h2>
                <ul class="links">
                    <li><a href="https://whosonfirst.org/" target="_blank">🌍 Who's On First Website</a></li>
                    <li><a href="https://geocode.earth/data/whosonfirst" target="_blank">💾 WOF Data Downloads</a></li>
                    <li><a href="https://github.com/whosonfirst/whosonfirst-data" target="_blank">💻 WOF Data Repository</a></li>
                    <li><a href="https://www.whosonfirst.org/docs/licenses/" target="_blank">📄 Licensing Information</a></li>
                </ul>
            </div>

            <footer>
                <p>Powered by <strong>Who's On First</strong> gazetteer data</p>
                <p style="margin-top: 10px;">Built with FastAPI, PostgreSQL, and PostGIS</p>
            </footer>
        </div>
    </body>
    </html>
    """

@app.get("/api/v1/hierarchy", response_model=HierarchyResponse)
def get_hierarchy_by_coords(
    lat: float,
    lon: float,
    db=Depends(get_db_connection),
    _token_id: int = Depends(require_token),
):
    """
    Resolves geographic coordinates to their corresponding Who's on First (WOF) hierarchy.

    This endpoint performs a point-in-polygon query to find all administrative regions
    containing the given coordinates, then builds a complete hierarchy.
    """

    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise HTTPException(status_code=400, detail="Invalid latitude or longitude.")

    try:
        cursor = db.cursor()

        # Query to find all matching placetypes containing this point
        # We order by placetype hierarchy (smallest to largest) for efficiency
        query = """
        SELECT id, name, placetype, parent_id, properties
        FROM whosonfirst
        WHERE ST_Contains(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
        ORDER BY CASE placetype
            WHEN 'neighbourhood' THEN 1
            WHEN 'locality' THEN 2
            WHEN 'borough' THEN 3
            WHEN 'county' THEN 4
            WHEN 'region' THEN 5
            WHEN 'country' THEN 6
            WHEN 'continent' THEN 7
            ELSE 99
        END;
        """

        cursor.execute(query, (lon, lat))
        results = cursor.fetchall()

        # Build hierarchy from results
        hierarchy = {}
        found_placetypes = set()

        for row in results:
            wof_id = row['id']
            name = row['name']
            placetype = row['placetype']
            parent_id = row['parent_id']
            properties = row['properties']

            # Only take the first match for each placetype
            if placetype not in found_placetypes:
                hierarchy[placetype] = {
                    "id": wof_id,
                    "name": name,
                    "placetype": placetype
                }
                found_placetypes.add(placetype)

        # If we didn't find all placetypes, try to fill in gaps using parent relationships
        if results and len(hierarchy) < 6:
            hierarchy = fill_hierarchy_gaps(cursor, hierarchy, found_placetypes)

        # Map to response model
        response = HierarchyResponse(
            continent=hierarchy.get('continent'),
            country=hierarchy.get('country'),
            region=hierarchy.get('region'),
            county=hierarchy.get('county'),
            locality=hierarchy.get('locality'),
            neighbourhood=hierarchy.get('neighbourhood')
        )

        return response

    except psycopg2.OperationalError as e:
        logger.error(f"Database operational error: {e}")
        raise HTTPException(status_code=503, detail=f"Database connection error: {str(e)}")
    except Exception as e:
        logger.error(f"Error processing hierarchy request: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {str(e)}")
    finally:
        if cursor:
            cursor.close()
        if db and connection_pool:
            connection_pool.putconn(db)


def fill_hierarchy_gaps(cursor, hierarchy: dict, found_placetypes: set) -> dict:
    """
    Fill in missing hierarchy levels by querying parent relationships.

    Args:
        cursor: Database cursor
        hierarchy: Current hierarchy dictionary
        found_placetypes: Set of placetypes already found

    Returns:
        Updated hierarchy dictionary
    """
    # Define the hierarchy order
    placetype_chain = ['neighbourhood', 'locality', 'borough', 'county', 'region', 'country', 'continent']

    # Find the most specific placetype we have
    for placetype in placetype_chain:
        if placetype in hierarchy:
            # Try to find parents
            current_id = hierarchy[placetype]['id']

            for _ in range(10):  # Limit iterations to prevent infinite loops
                parent_query = """
                SELECT id, name, placetype, parent_id
                FROM whosonfirst
                WHERE id = (
                    SELECT parent_id FROM whosonfirst WHERE id = %s
                )
                LIMIT 1;
                """

                cursor.execute(parent_query, (current_id,))
                parent = cursor.fetchone()

                if not parent:
                    break

                parent_id = parent['id']
                parent_name = parent['name']
                parent_placetype = parent['placetype']
                grandparent_id = parent['parent_id']

                if parent_placetype not in found_placetypes:
                    hierarchy[parent_placetype] = {
                        "id": parent_id,
                        "name": parent_name,
                        "placetype": parent_placetype
                    }
                    found_placetypes.add(parent_placetype)

                current_id = parent_id

            break

    return hierarchy

@app.get("/health")
def health_check():
    """
    Health check endpoint with database connectivity test.
    """
    health_status = {
        "status": "ok",
        "service": "wof-api",
        "database": "unknown"
    }

    # Check database connectivity
    try:
        if not connection_pool:
            health_status["database"] = "unavailable"
            health_status["status"] = "degraded"
            return health_status

        conn = connection_pool.getconn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1;")
            cursor.fetchone()
            cursor.close()
            health_status["database"] = "healthy"
        finally:
            connection_pool.putconn(conn)

    except Exception as e:
        logger.error(f"Health check database error: {e}")
        health_status["database"] = "unhealthy"
        health_status["status"] = "degraded"
        health_status["error"] = str(e)

    return health_status


@app.get("/api/v1/place/{wof_id}")
def get_place_by_id(
    wof_id: int,
    db=Depends(get_db_connection),
    _token_id: int = Depends(require_token),
):
    """
    Retrieve a WOF place by its ID.
    """
    try:
        cursor = db.cursor()

        query = """
        SELECT id, name, placetype, parent_id, properties
        FROM whosonfirst
        WHERE id = %s
        LIMIT 1;
        """

        cursor.execute(query, (wof_id,))
        result = cursor.fetchone()

        if not result:
            raise HTTPException(status_code=404, detail=f"Place with ID {wof_id} not found")

        return {
            "id": result['id'],
            "name": result['name'],
            "placetype": result['placetype'],
            "parent_id": result['parent_id'],
            "properties": result['properties']
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving place {wof_id}: {e}")
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {str(e)}")
    finally:
        if cursor:
            cursor.close()
        if db and connection_pool:
            connection_pool.putconn(db)

# --- Admin: token management ---

def _fetch_tokens(cursor):
    cursor.execute("""
        SELECT t.id, t.name, t.token_prefix, t.created_at, t.revoked_at,
               COUNT(u.id) AS call_count,
               MAX(u.called_at) AS last_called_at
        FROM api_tokens t
        LEFT JOIN api_token_usage u ON u.token_id = t.id
        GROUP BY t.id
        ORDER BY t.created_at DESC;
    """)
    return cursor.fetchall()


def _render_admin_html(tokens, new_token: Optional[str] = None, message: Optional[str] = None) -> str:
    new_banner = ""
    if new_token:
        new_banner = f"""
        <div class="banner success">
            <strong>New token created — copy it now, it will not be shown again:</strong>
            <pre class="token-display">{html_lib.escape(new_token)}</pre>
        </div>
        """
    msg_banner = ""
    if message:
        msg_banner = f'<div class="banner info">{html_lib.escape(message)}</div>'

    rows = []
    for t in tokens:
        status_label = "revoked" if t["revoked_at"] else "active"
        last_called = t["last_called_at"].strftime("%Y-%m-%d %H:%M:%S UTC") if t["last_called_at"] else "—"
        created = t["created_at"].strftime("%Y-%m-%d %H:%M:%S UTC") if t["created_at"] else "—"
        revoke_cell = ""
        if not t["revoked_at"]:
            revoke_cell = f"""
            <form method="post" action="/admin/tokens/{t['id']}/revoke" onsubmit="return confirm('Revoke token \\'{html_lib.escape(t['name'])}\\'? This cannot be undone.');">
                <button type="submit" class="btn-danger">Revoke</button>
            </form>
            """
        rows.append(f"""
            <tr class="{'revoked' if t['revoked_at'] else ''}">
                <td>{html_lib.escape(t['name'])}</td>
                <td><code>{html_lib.escape(t['token_prefix'])}…</code></td>
                <td><span class="status status-{status_label}">{status_label}</span></td>
                <td>{t['call_count']}</td>
                <td>{last_called}</td>
                <td>{created}</td>
                <td>{revoke_cell}</td>
            </tr>
        """)
    rows_html = "\n".join(rows) if rows else '<tr><td colspan="7" class="empty">No tokens yet — create one below.</td></tr>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>WOF API — Admin</title>
    <link rel="icon" type="image/png" sizes="32x32" href="/static/favicon-32x32.png">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                line-height: 1.5; color: #333; background: #f5f5f5; }}
        .container {{ max-width: 1100px; margin: 0 auto; padding: 30px 20px; }}
        header {{ background: white; padding: 24px 30px; border-radius: 8px;
                  box-shadow: 0 2px 4px rgba(0,0,0,0.08); margin-bottom: 20px;
                  display: flex; justify-content: space-between; align-items: center; }}
        h1 {{ color: #2c3e50; font-size: 1.6em; }}
        h2 {{ color: #34495e; font-size: 1.2em; margin-bottom: 16px; }}
        .section {{ background: white; padding: 24px 30px; border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.08); margin-bottom: 20px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid #ecf0f1; }}
        th {{ background: #f8f9fa; font-weight: 600; color: #555; font-size: 0.9em; }}
        tr.revoked {{ color: #999; }}
        td.empty {{ text-align: center; color: #999; padding: 30px; }}
        code {{ font-family: 'SF Mono', Menlo, monospace; font-size: 0.9em;
                background: #ecf0f1; padding: 2px 6px; border-radius: 3px; }}
        .status {{ display: inline-block; padding: 2px 8px; border-radius: 10px;
                   font-size: 0.8em; font-weight: 500; }}
        .status-active {{ background: #d4edda; color: #155724; }}
        .status-revoked {{ background: #f8d7da; color: #721c24; }}
        form.inline {{ display: flex; gap: 10px; align-items: center; }}
        input[type=text] {{ padding: 8px 10px; border: 1px solid #ccc; border-radius: 4px;
                            font-size: 1em; flex: 1; max-width: 320px; }}
        button {{ padding: 8px 16px; border: none; border-radius: 4px;
                  font-size: 0.95em; cursor: pointer; font-weight: 500; }}
        button[type=submit]:not(.btn-danger) {{ background: #3498db; color: white; }}
        button[type=submit]:not(.btn-danger):hover {{ background: #2980b9; }}
        .btn-danger {{ background: #e74c3c; color: white; }}
        .btn-danger:hover {{ background: #c0392b; }}
        .banner {{ padding: 16px 20px; border-radius: 6px; margin-bottom: 20px; }}
        .banner.success {{ background: #fff3cd; border: 1px solid #ffeaa7; color: #856404; }}
        .banner.info {{ background: #d1ecf1; border: 1px solid #bee5eb; color: #0c5460; }}
        .token-display {{ background: #2c3e50; color: #ecf0f1; padding: 12px 14px;
                          border-radius: 4px; font-family: 'SF Mono', Menlo, monospace;
                          margin-top: 10px; word-break: break-all; }}
        .hint {{ color: #7f8c8d; font-size: 0.9em; margin-top: 8px; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>API Token Admin</h1>
            <a href="/">← Back to landing</a>
        </header>

        {new_banner}
        {msg_banner}

        <div class="section">
            <h2>Tokens</h2>
            <table>
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Prefix</th>
                        <th>Status</th>
                        <th>Calls</th>
                        <th>Last used</th>
                        <th>Created</th>
                        <th></th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
        </div>

        <div class="section">
            <h2>Create new token</h2>
            <form method="post" action="/admin/tokens" class="inline">
                <input type="text" name="name" placeholder="Token name (e.g. mobile-app)" required maxlength="100">
                <button type="submit">Create token</button>
            </form>
            <p class="hint">The full token will be shown once after creation. Store it somewhere safe.</p>
        </div>
    </div>
</body>
</html>"""


@app.get("/admin", response_class=HTMLResponse)
def admin_page(_user: str = Depends(require_admin)):
    if not connection_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")
    conn = connection_pool.getconn()
    try:
        cursor = conn.cursor()
        tokens = _fetch_tokens(cursor)
        cursor.close()
        return _render_admin_html(tokens)
    finally:
        connection_pool.putconn(conn)


@app.post("/admin/tokens", response_class=HTMLResponse)
def admin_create_token(name: str = Form(...), _user: str = Depends(require_admin)):
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    if len(name) > 100:
        raise HTTPException(status_code=400, detail="Name too long (max 100 chars)")

    if not connection_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")

    raw = secrets.token_urlsafe(32)
    plaintext = f"{TOKEN_PREFIX}{raw}"
    token_hash = hash_token(plaintext)
    token_prefix = plaintext[:12]

    conn = connection_pool.getconn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO api_tokens (name, token_hash, token_prefix) VALUES (%s, %s, %s)",
            (name, token_hash, token_prefix),
        )
        conn.commit()
        tokens = _fetch_tokens(cursor)
        cursor.close()
        return _render_admin_html(tokens, new_token=plaintext)
    finally:
        connection_pool.putconn(conn)


@app.post("/admin/tokens/{token_id}/revoke")
def admin_revoke_token(token_id: int, _user: str = Depends(require_admin)):
    if not connection_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")
    conn = connection_pool.getconn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE api_tokens SET revoked_at = NOW() WHERE id = %s AND revoked_at IS NULL",
            (token_id,),
        )
        conn.commit()
        cursor.close()
    finally:
        connection_pool.putconn(conn)
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


# To run this application:
# 1. Install dependencies: pip install -r requirements.txt
# 2. Run the server: uvicorn main:app --reload
# 3. Access the docs at http://127.0.0.1:8000/docs
