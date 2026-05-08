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
    <title>WHO'S ON FIRST — A GAZETTEER</title>
    <link rel="icon" type="image/png" sizes="16x16" href="/static/favicon-16x16.png">
    <link rel="icon" type="image/png" sizes="32x32" href="/static/favicon-32x32.png">
    <link rel="apple-touch-icon" sizes="180x180" href="/static/apple-touch-icon.png">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=VT323&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #0a0e08;
            --fg: #4cff4c;
            --bright: #ffffff;
            --amber: #ffb84c;
            --dim: #2a8a2a;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        html, body { background: var(--bg); }
        body {
            font-family: 'VT323', ui-monospace, 'Courier New', monospace;
            font-size: 22px;
            line-height: 1.35;
            color: var(--fg);
            min-height: 100vh;
            padding: 32px 16px 48px;
            text-shadow: 0 0 1px currentColor;
        }
        body::after {
            content: "";
            position: fixed;
            inset: 0;
            background: repeating-linear-gradient(to bottom,
                rgba(0,0,0,0) 0,
                rgba(0,0,0,0) 2px,
                rgba(0,0,0,0.18) 2px,
                rgba(0,0,0,0.18) 3px);
            pointer-events: none;
            z-index: 100;
            mix-blend-mode: multiply;
        }
        .screen {
            max-width: 720px;
            margin: 0 auto;
        }
        h1, h2, h3 {
            color: var(--bright);
            font-weight: normal;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }
        h1 {
            font-size: 44px;
            line-height: 1;
            text-align: center;
            margin: 24px 0 12px;
        }
        .subtitle {
            text-align: center;
            color: var(--fg);
            margin-bottom: 8px;
            font-size: 22px;
        }
        .copyright {
            text-align: center;
            color: var(--dim);
            margin-bottom: 28px;
            font-size: 18px;
        }
        .rule {
            color: var(--fg);
            white-space: pre;
            overflow: hidden;
            margin: 18px 0;
            font-size: 20px;
        }

        /* Title card / title screen */
        .title-card {
            text-align: center;
            padding: 32px 16px 24px;
            margin: 8px 0 32px;
            border: 2px solid var(--fg);
            position: relative;
            background:
                radial-gradient(ellipse at center,
                    rgba(76, 255, 76, 0.04) 0%,
                    transparent 70%);
        }
        .title-card::before, .title-card::after {
            content: "";
            position: absolute;
            top: -2px; bottom: -2px;
            width: 12px;
            border-top: 2px solid var(--amber);
            border-bottom: 2px solid var(--amber);
        }
        .title-card::before { left: -2px; border-left: 2px solid var(--amber); }
        .title-card::after  { right: -2px; border-right: 2px solid var(--amber); }
        .presents {
            color: var(--fg);
            text-transform: uppercase;
            letter-spacing: 0.32em;
            font-size: 20px;
            margin-bottom: 6px;
            animation: presents-fade 0.9s ease-out backwards;
        }
        .title-rule {
            color: var(--fg);
            white-space: pre;
            overflow: hidden;
            margin: 8px auto;
            font-size: 18px;
            opacity: 0.6;
            max-width: 18ch;
        }
        .game-title {
            display: block;
            font-family: 'VT323', monospace;
            font-size: clamp(48px, 11vw, 96px);
            line-height: 0.95;
            letter-spacing: 0.02em;
            color: var(--bright);
            margin: 22px 0 18px;
            text-transform: uppercase;
            text-shadow:
                0 0 1px var(--fg),
                4px 4px 0 var(--amber),
                4px 4px 6px rgba(255, 184, 76, 0.4);
            animation: title-drop 0.7s cubic-bezier(.2,.7,.3,1) backwards;
        }
        .game-title span {
            display: block;
        }
        .game-title span:nth-child(2) { animation-delay: 0.15s; }
        .title-art {
            display: block;
            width: 100%;
            max-width: 480px;
            height: auto;
            margin: 16px auto 18px;
            image-rendering: pixelated;
            image-rendering: crisp-edges;
            filter: drop-shadow(0 0 4px rgba(76, 255, 76, 0.2));
            animation: art-fade 0.9s ease-out 0.3s backwards;
        }
        .title-card .subtitle {
            color: var(--fg);
            margin: 14px 0 4px;
            font-size: 22px;
            text-transform: uppercase;
            letter-spacing: 0.12em;
        }
        .title-card .copyright {
            color: var(--dim);
            margin-bottom: 18px;
            font-size: 18px;
            letter-spacing: 0.12em;
        }
        .press-any-key {
            color: var(--bright);
            text-transform: uppercase;
            letter-spacing: 0.12em;
            font-size: 22px;
            margin-top: 12px;
            animation: pak-blink 1.3s steps(1) infinite;
        }
        .press-any-key .key {
            color: var(--amber);
            background: rgba(255, 184, 76, 0.12);
            padding: 2px 8px;
            border: 1px solid var(--amber);
            margin: 0 4px;
        }
        @keyframes pak-blink { 0%, 60% { opacity: 1; } 70%, 100% { opacity: 0.25; } }
        @keyframes title-drop {
            from { opacity: 0; transform: translateY(-12px); }
            to   { opacity: 1; transform: none; }
        }
        @keyframes presents-fade { from { opacity: 0; } to { opacity: 1; } }
        @keyframes art-fade { from { opacity: 0; } to { opacity: 1; } }

        section {
            margin: 28px 0;
        }
        h2 {
            font-size: 26px;
            margin-bottom: 4px;
        }
        h2::before { content: ">> "; color: var(--amber); }
        section p {
            margin: 8px 0;
            max-width: 64ch;
        }
        a {
            color: var(--amber);
            text-decoration: underline;
            text-underline-offset: 4px;
            text-decoration-thickness: 1px;
        }
        a:hover { background: var(--amber); color: var(--bg); text-decoration: none; }
        code {
            color: var(--bright);
            background: rgba(76, 255, 76, 0.10);
            padding: 0 4px;
        }
        strong {
            color: var(--bright);
            font-weight: normal;
        }

        .frame {
            border: 1px solid var(--fg);
            padding: 12px 18px;
            margin: 14px 0;
            position: relative;
        }
        .frame-title {
            position: absolute;
            top: -14px;
            left: 14px;
            background: var(--bg);
            padding: 0 8px;
            color: var(--amber);
            font-size: 20px;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }

        /* Stats — party status panel */
        .stats { padding: 8px 0; }
        .stats .row {
            display: grid;
            grid-template-columns: 1fr auto;
            gap: 8px;
            font-size: 22px;
            color: var(--bright);
            position: relative;
            padding: 4px 0;
        }
        .stats .row .label {
            background: var(--bg);
            padding-right: 6px;
            position: relative;
            z-index: 1;
        }
        .stats .row .value {
            background: var(--bg);
            padding-left: 6px;
            position: relative;
            z-index: 1;
            color: var(--amber);
        }
        .stats .row::after {
            content: "";
            position: absolute;
            left: 0; right: 0;
            bottom: 12px;
            border-bottom: 2px dotted var(--dim);
            z-index: 0;
        }

        /* Notice */
        .notice {
            border: 1px solid var(--amber);
            padding: 14px 18px;
            margin: 16px 0;
            color: var(--bright);
        }
        .notice .heading {
            color: var(--amber);
            text-transform: uppercase;
            margin-bottom: 6px;
        }
        .notice p { margin: 6px 0; }

        /* Endpoint listing */
        .endpoint {
            margin: 18px 0;
        }
        .endpoint .name { color: var(--bright); text-transform: uppercase; }
        .endpoint .name::before { content: ""; }
        .endpoint .verb {
            color: var(--bg);
            background: var(--fg);
            padding: 0 8px;
            margin-right: 8px;
        }
        .endpoint .path { color: var(--bright); }
        .endpoint .desc { color: var(--fg); margin: 4px 0 8px; font-style: normal; }
        .endpoint pre {
            background: rgba(76, 255, 76, 0.06);
            border-left: 2px solid var(--fg);
            padding: 10px 14px;
            margin: 8px 0;
            font-family: 'VT323', monospace;
            font-size: 20px;
            color: var(--bright);
            white-space: pre-wrap;
            word-break: break-word;
        }
        .endpoint pre::before {
            content: "$ ";
            color: var(--amber);
        }
        .endpoint .returns {
            color: var(--dim);
            font-size: 20px;
        }
        .endpoint .returns::before { content: "↳ "; color: var(--amber); }
        .endpoint .public-tag {
            color: var(--amber);
            margin-left: 8px;
            font-size: 18px;
        }

        /* Menus */
        .menu {
            list-style: none;
            margin: 10px 0;
            padding: 0;
        }
        .menu li {
            padding: 4px 0;
        }
        .menu li a { display: block; }
        .menu .num {
            color: var(--amber);
            display: inline-block;
            width: 2.2ch;
        }

        /* Press-key prompt */
        .prompt {
            text-align: center;
            margin-top: 36px;
            color: var(--bright);
            text-transform: uppercase;
            letter-spacing: 0.1em;
        }
        .prompt::after {
            content: "_";
            color: var(--fg);
            animation: blink 1s steps(1) infinite;
            margin-left: 4px;
        }
        @keyframes blink { 50% { opacity: 0; } }

        footer {
            text-align: center;
            margin-top: 32px;
            color: var(--dim);
            font-size: 18px;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }

        @media (max-width: 600px) {
            body { font-size: 20px; padding: 16px 10px 32px; }
            h1 { font-size: 34px; }
        }
    </style>
</head>
<body>
    <div class="screen">

        <div class="title-card">
            <p class="presents">GEOCACHING HQ PRESENTS</p>
            <div class="title-rule">━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</div>

            <h1 class="game-title">
                <span>THE OREGON</span>
                <span>GAZETTEER</span>
            </h1>

            <svg class="title-art" viewBox="0 0 80 22" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
                <g fill="#ffb84c">
                    <rect x="62" y="2" width="6" height="4"/>
                    <rect x="61" y="3" width="8" height="2"/>
                    <rect x="58" y="3" width="1" height="2"/>
                    <rect x="71" y="3" width="1" height="2"/>
                    <rect x="64" y="0" width="2" height="1"/>
                    <rect x="64" y="7" width="2" height="1"/>
                </g>
                <g fill="#2a8a2a">
                    <polygon points="0,15 8,7 16,13 24,5 32,11 40,8 48,13 56,10 64,15 80,15 80,17 0,17"/>
                </g>
                <g fill="#4cff4c">
                    <polygon points="0,16 6,10 12,16"/>
                    <polygon points="14,16 22,8 30,16"/>
                </g>
                <rect x="0" y="17" width="80" height="1" fill="#4cff4c"/>
                <g fill="#4cff4c">
                    <rect x="33" y="13" width="6" height="3"/>
                    <rect x="39" y="13" width="2" height="2"/>
                    <rect x="33" y="16" width="1" height="2"/>
                    <rect x="36" y="16" width="1" height="2"/>
                    <rect x="38" y="16" width="1" height="2"/>
                    <rect x="39" y="12" width="1" height="1"/>
                    <rect x="41" y="12" width="1" height="1"/>
                </g>
                <g fill="#4cff4c">
                    <rect x="20" y="12" width="2" height="1"/>
                    <rect x="28" y="12" width="2" height="1"/>
                    <rect x="22" y="11" width="6" height="1"/>
                    <rect x="20" y="13" width="10" height="1"/>
                    <rect x="19" y="14" width="1" height="3"/>
                    <rect x="30" y="14" width="1" height="3"/>
                    <rect x="19" y="16" width="12" height="1"/>
                    <rect x="20" y="17" width="2" height="2"/>
                    <rect x="28" y="17" width="2" height="2"/>
                </g>
                <g fill="#2a8a2a">
                    <rect x="2" y="20" width="1" height="1"/>
                    <rect x="7" y="20" width="1" height="1"/>
                    <rect x="12" y="20" width="1" height="1"/>
                    <rect x="50" y="20" width="1" height="1"/>
                    <rect x="55" y="20" width="1" height="1"/>
                    <rect x="60" y="20" width="1" height="1"/>
                    <rect x="65" y="20" width="1" height="1"/>
                    <rect x="70" y="20" width="1" height="1"/>
                    <rect x="75" y="20" width="1" height="1"/>
                </g>
            </svg>

            <p class="subtitle">WHO'S ON FIRST · HTTP API</p>
            <p class="copyright">© 2026 GROUNDSPEAK, INC. · VERSION 1</p>

            <div class="title-rule">━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</div>
            <p class="press-any-key">▸ PRESS <span class="key">[ ANY KEY ]</span> TO BEGIN ◂</p>
        </div>

        <section>
            <h2>About this gazetteer</h2>
            <p><strong>Who's On First</strong> (WOF) is a gazetteer of places — a comprehensive geographic database covering countries, regions, cities, neighbourhoods, and the small named bits in between. It is an open-data project providing consistent, accurate place records with rich metadata and hierarchical relationships.</p>
            <p>This service exposes a fast, production-ready HTTP API for resolving geographic coordinates to their administrative hierarchies using Who's On First data.</p>
        </section>

        <section>
            <h2>What is in the index</h2>
            <div class="frame stats">
                <span class="frame-title">Supplies on hand</span>
                <div class="row"><span class="label">Total places</span><span class="value">300,767</span></div>
                <div class="row"><span class="label">Localities</span><span class="value">180,225</span></div>
                <div class="row"><span class="label">Neighbourhoods</span><span class="value">56,947</span></div>
                <div class="row"><span class="label">Constituencies</span><span class="value">7,194</span></div>
            </div>
        </section>

        <section>
            <h2>Authentication</h2>
            <p>All <code>/api/v1/*</code> endpoints require a Bearer token. Include your token in the <code>Authorization</code> header on every request:</p>
            <pre style="background: rgba(255,184,76,0.08); border-left: 2px solid var(--amber); padding: 10px 14px; color: var(--bright); font-family: 'VT323', monospace; font-size: 20px;">Authorization: Bearer wof_&lt;your-token&gt;</pre>
            <div class="notice">
                <div class="heading">!! Notice !!</div>
                <p>Tokens are issued through the <a href="/admin">admin page</a> (password-protected). Each token's usage is tracked, and any token may be revoked at any time.</p>
                <p style="color: var(--fg);">The <code>/health</code> endpoint and this landing page remain public. Requests without a valid token return <code>401 Unauthorized</code>.</p>
            </div>
        </section>

        <section>
            <h2>The instrument panel</h2>

            <div class="endpoint">
                <p class="name">1. Resolve hierarchy from coordinates</p>
                <p><span class="verb">GET</span><span class="path">/api/v1/hierarchy?lat={latitude}&amp;lon={longitude}</span></p>
                <p class="desc">Returns the continent, country, region, county, locality, and neighbourhood enclosing the point.</p>
                <pre>curl -H "Authorization: Bearer wof_..." \\
   "/api/v1/hierarchy?lat=37.7749&amp;lon=-122.4194"</pre>
                <p class="returns">continent · country · region · county · locality · neighbourhood</p>
            </div>

            <div class="endpoint">
                <p class="name">2. Fetch a place record by id</p>
                <p><span class="verb">GET</span><span class="path">/api/v1/place/{wof_id}</span></p>
                <p class="desc">Returns the complete place record with properties and full hierarchy.</p>
                <pre>curl -H "Authorization: Bearer wof_..." /api/v1/place/85922583</pre>
                <p class="returns">complete place details with properties and hierarchy</p>
            </div>

            <div class="endpoint">
                <p class="name">3. Health check<span class="public-tag">[ no auth ]</span></p>
                <p><span class="verb">GET</span><span class="path">/health</span></p>
                <p class="desc">Liveness probe. No authentication required.</p>
            </div>
        </section>

        <section>
            <h2>What would you like to read?</h2>
            <ul class="menu">
                <li><a href="/docs"><span class="num">1.</span>Interactive Swagger UI ........ /docs</a></li>
                <li><a href="/redoc"><span class="num">2.</span>ReDoc reference ............... /redoc</a></li>
                <li><a href="/openapi.json"><span class="num">3.</span>OpenAPI schema ................ /openapi.json</a></li>
            </ul>
        </section>

        <section>
            <h2>Provenance</h2>
            <ul class="menu">
                <li><a href="https://whosonfirst.org/" target="_blank" rel="noopener"><span class="num">A.</span>Who's On First ................ whosonfirst.org</a></li>
                <li><a href="https://geocode.earth/data/whosonfirst" target="_blank" rel="noopener"><span class="num">B.</span>Bulk data downloads ........... geocode.earth</a></li>
                <li><a href="https://github.com/whosonfirst/whosonfirst-data" target="_blank" rel="noopener"><span class="num">C.</span>Source repository ............. github</a></li>
                <li><a href="https://www.whosonfirst.org/docs/licenses/" target="_blank" rel="noopener"><span class="num">D.</span>Licensing ..................... cc-by · odbl</a></li>
            </ul>
        </section>

        <div class="rule">═══════════════════════════════════════════════</div>
        <p class="prompt">Press a key to resolve coordinates</p>

        <footer>
            <p>FastAPI &middot; PostgreSQL &middot; PostGIS</p>
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
        <div class="banner banner-success">
            <div class="banner-heading">!! New key forged !!</div>
            <p>Copy this token now — it will not be shown again.</p>
            <pre class="token-display">{html_lib.escape(new_token)}</pre>
        </div>
        """
    msg_banner = ""
    if message:
        msg_banner = f'<div class="banner banner-info"><div class="banner-heading">Notice</div><p>{html_lib.escape(message)}</p></div>'

    rows = []
    for t in tokens:
        status_label = "revoked" if t["revoked_at"] else "active"
        last_called = t["last_called_at"].strftime("%Y-%m-%d %H:%M UTC") if t["last_called_at"] else "—"
        created = t["created_at"].strftime("%Y-%m-%d %H:%M UTC") if t["created_at"] else "—"
        revoke_cell = ""
        if not t["revoked_at"]:
            revoke_cell = f"""
            <form method="post" action="/admin/tokens/{t['id']}/revoke" onsubmit="return confirm('Revoke token \\'{html_lib.escape(t['name'])}\\'? This cannot be undone.');">
                <button type="submit" class="btn-danger">[ revoke ]</button>
            </form>
            """
        rows.append(f"""
            <tr class="{'revoked' if t['revoked_at'] else ''}">
                <td class="cell-name">{html_lib.escape(t['name'])}</td>
                <td class="mono">{html_lib.escape(t['token_prefix'])}…</td>
                <td><span class="status status-{status_label}">[{status_label.upper()}]</span></td>
                <td class="num">{t['call_count']}</td>
                <td class="mono">{last_called}</td>
                <td class="mono">{created}</td>
                <td class="action">{revoke_cell}</td>
            </tr>
        """)
    rows_html = "\n".join(rows) if rows else '<tr><td colspan="7" class="empty">No tokens issued yet — forge one below.</td></tr>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WHO'S ON FIRST — TOKEN LEDGER</title>
    <link rel="icon" type="image/png" sizes="32x32" href="/static/favicon-32x32.png">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=VT323&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg: #0a0e08;
            --fg: #4cff4c;
            --bright: #ffffff;
            --amber: #ffb84c;
            --dim: #2a8a2a;
            --red: #ff5a3c;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        html, body {{ background: var(--bg); }}
        body {{
            font-family: 'VT323', ui-monospace, 'Courier New', monospace;
            font-size: 22px;
            line-height: 1.35;
            color: var(--fg);
            min-height: 100vh;
            padding: 32px 16px 48px;
            text-shadow: 0 0 1px currentColor;
        }}
        body::after {{
            content: "";
            position: fixed;
            inset: 0;
            background: repeating-linear-gradient(to bottom,
                rgba(0,0,0,0) 0,
                rgba(0,0,0,0) 2px,
                rgba(0,0,0,0.18) 2px,
                rgba(0,0,0,0.18) 3px);
            pointer-events: none;
            z-index: 100;
            mix-blend-mode: multiply;
        }}
        .screen {{ max-width: 920px; margin: 0 auto; }}
        h1, h2 {{ color: var(--bright); font-weight: normal; text-transform: uppercase; letter-spacing: 0.04em; }}
        h1 {{ font-size: 40px; line-height: 1; text-align: center; margin: 16px 0 8px; }}
        .subtitle {{ text-align: center; color: var(--fg); margin-bottom: 6px; font-size: 22px; }}
        .copyright {{ text-align: center; color: var(--dim); margin-bottom: 24px; font-size: 18px; }}
        .rule {{ color: var(--fg); white-space: pre; overflow: hidden; margin: 16px 0; font-size: 20px; }}
        section {{ margin: 28px 0; }}
        h2 {{ font-size: 26px; margin-bottom: 8px; }}
        h2::before {{ content: ">> "; color: var(--amber); }}
        a {{ color: var(--amber); text-decoration: underline; text-underline-offset: 4px; text-decoration-thickness: 1px; }}
        a:hover {{ background: var(--amber); color: var(--bg); text-decoration: none; }}
        strong {{ color: var(--bright); font-weight: normal; }}
        .nav-bar {{
            display: flex; justify-content: space-between; align-items: center;
            font-size: 18px; color: var(--dim); text-transform: uppercase; letter-spacing: 0.08em;
            margin-bottom: 8px;
        }}
        .nav-bar a {{ color: var(--dim); text-decoration: none; }}
        .nav-bar a:hover {{ color: var(--amber); background: transparent; }}

        /* Banners */
        .banner {{
            border: 1px solid var(--fg);
            padding: 14px 18px;
            margin: 16px 0;
            color: var(--bright);
        }}
        .banner-success {{ border-color: var(--amber); }}
        .banner-info    {{ border-color: var(--fg); }}
        .banner-heading {{
            color: var(--amber);
            text-transform: uppercase;
            letter-spacing: 0.1em;
            margin-bottom: 6px;
        }}
        .banner-info .banner-heading {{ color: var(--fg); }}
        .banner p {{ margin: 6px 0; }}
        .token-display {{
            background: rgba(255,184,76,0.10);
            border-left: 2px solid var(--amber);
            padding: 12px 16px;
            margin-top: 10px;
            font-family: 'VT323', monospace;
            font-size: 22px;
            color: var(--bright);
            word-break: break-all;
            user-select: all;
        }}

        /* Ledger */
        .ledger-frame {{
            border: 1px solid var(--fg);
            padding: 4px 10px 8px;
            position: relative;
            margin-top: 16px;
            overflow-x: auto;
        }}
        .ledger-frame .frame-title {{
            position: absolute;
            top: -14px;
            left: 14px;
            background: var(--bg);
            padding: 0 8px;
            color: var(--amber);
            font-size: 20px;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }}
        table.ledger {{ width: 100%; border-collapse: collapse; font-size: 20px; }}
        table.ledger thead th {{
            text-align: left;
            padding: 12px 10px 8px;
            color: var(--bright);
            text-transform: uppercase;
            letter-spacing: 0.06em;
            border-bottom: 1px dashed var(--fg);
            font-weight: normal;
            font-size: 18px;
        }}
        table.ledger thead th.num {{ text-align: right; }}
        table.ledger tbody td {{
            padding: 10px;
            border-bottom: 1px dotted var(--dim);
            color: var(--fg);
            vertical-align: middle;
        }}
        table.ledger tbody tr:last-child td {{ border-bottom: none; }}
        table.ledger tbody tr.revoked td {{ color: var(--dim); }}
        table.ledger tbody tr.revoked .cell-name {{ text-decoration: line-through; }}
        td.cell-name {{ color: var(--bright); }}
        td.num {{ text-align: right; color: var(--amber); }}
        td.mono {{ color: var(--fg); }}
        td.action {{ text-align: right; }}
        td.empty {{
            text-align: center;
            padding: 36px 16px;
            color: var(--dim);
            font-size: 22px;
        }}

        .status {{
            display: inline-block;
            padding: 0 6px;
            font-weight: normal;
            letter-spacing: 0.06em;
        }}
        .status-active  {{ color: var(--fg); }}
        .status-revoked {{ color: var(--red); }}

        /* Forge */
        .forge {{
            border: 1px solid var(--amber);
            padding: 14px 18px;
            position: relative;
            margin-top: 18px;
        }}
        .forge .frame-title {{
            position: absolute;
            top: -14px;
            left: 14px;
            background: var(--bg);
            padding: 0 8px;
            color: var(--amber);
            font-size: 20px;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }}
        form.inline {{ display: flex; gap: 0; flex-wrap: wrap; }}
        form.inline input[type=text] {{
            flex: 1 1 280px;
            padding: 10px 14px;
            border: 1px solid var(--fg);
            background: rgba(76,255,76,0.05);
            color: var(--bright);
            font-family: 'VT323', monospace;
            font-size: 22px;
            outline: none;
        }}
        form.inline input[type=text]::placeholder {{ color: var(--dim); }}
        form.inline input[type=text]:focus {{ background: rgba(76,255,76,0.12); border-color: var(--amber); }}
        form.inline button[type=submit] {{
            padding: 10px 20px;
            border: 1px solid var(--amber);
            border-left: none;
            background: var(--amber);
            color: var(--bg);
            font-family: 'VT323', monospace;
            font-size: 22px;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            cursor: pointer;
        }}
        form.inline button[type=submit]:hover {{
            background: var(--bg);
            color: var(--amber);
        }}
        .hint {{ color: var(--dim); margin-top: 10px; font-size: 20px; }}

        .btn-danger {{
            padding: 4px 10px;
            border: 1px solid var(--red);
            background: transparent;
            color: var(--red);
            font-family: 'VT323', monospace;
            font-size: 20px;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            cursor: pointer;
        }}
        .btn-danger:hover {{ background: var(--red); color: var(--bg); }}

        footer {{
            text-align: center;
            margin-top: 32px;
            color: var(--dim);
            font-size: 18px;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }}

        @media (max-width: 720px) {{
            body {{ font-size: 20px; padding: 16px 10px 32px; }}
            h1 {{ font-size: 30px; }}
            table.ledger thead {{ display: none; }}
            table.ledger tbody td {{ display: block; padding: 4px 8px; border: none; font-size: 19px; }}
            table.ledger tbody td.cell-name {{ padding-top: 12px; }}
            table.ledger tbody td.action {{ padding-bottom: 12px; }}
            table.ledger tbody tr {{ border-bottom: 1px dashed var(--dim); }}
            form.inline {{ flex-direction: column; }}
            form.inline button[type=submit] {{ border-left: 1px solid var(--amber); border-top: none; }}
        }}
    </style>
</head>
<body>
    <div class="screen">
        <div class="nav-bar">
            <span>Operator console</span>
            <a href="/">&lt; back to start screen</a>
        </div>
        <div class="rule">═══════════════════════════════════════════════════════════</div>

        <h1>Token Ledger</h1>
        <p class="subtitle">ISSUE · AUDIT · REVOKE</p>
        <p class="copyright">RESTRICTED — OPERATIONS LOG</p>

        <div class="rule">═══════════════════════════════════════════════════════════</div>

        {new_banner}
        {msg_banner}

        <section>
            <h2>The keyring</h2>
            <div class="ledger-frame">
                <span class="frame-title">Issued tokens</span>
                <table class="ledger">
                    <thead>
                        <tr>
                            <th>Name</th>
                            <th>Prefix</th>
                            <th>Status</th>
                            <th class="num">Calls</th>
                            <th>Last seen</th>
                            <th>Issued</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                </table>
            </div>
        </section>

        <section>
            <h2>Forge a new key</h2>
            <div class="forge">
                <span class="frame-title">Issue token</span>
                <form method="post" action="/admin/tokens" class="inline">
                    <input type="text" name="name" placeholder="Token name (e.g. mobile-app)" required maxlength="100" autocomplete="off">
                    <button type="submit">Issue</button>
                </form>
                <p class="hint">The full token is shown once after creation. Store it somewhere durable — it cannot be recovered.</p>
            </div>
        </section>

        <div class="rule">═══════════════════════════════════════════════════════════</div>

        <footer>
            <p>Who's On First &middot; Token Ledger</p>
        </footer>
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
