# Lodestone Reverse-Geocode — `wof.wherigo.live` Verification (Phase A)

**Bead:** `wh-9s2` · **Labels:** integration, lodestone-v1, phase-a
**Source of requirements:** `PRD-lodestone-integrations.md` (Lodestone project)
**Verified:** 2026-06-10 (~23:29–23:40 UTC) against the live Railway deployment
**Target endpoint:** `GET https://wof.wherigo.live/api/v1/hierarchy?lat=&lon=`
(the endpoint Lodestone's `/integrations/region` will call)

---

## Verdict: ⚠️ NOT READY — conditional, two blockers

The endpoint **exists with the correct contract** and, when healthy, responds
with **excellent latency** from a **Bay-Area-adjacent** region. However, the
service is **not currently fit to depend on** for activation reverse-geocode:

| Requirement (from bead) | Result |
|---|---|
| `/api/v1/hierarchy` endpoint exists & correct contract | ✅ Confirmed (live OpenAPI) |
| Acceptable **latency** | ✅ Excellent (warm TTFB 24–50 ms) |
| Bay-Area / US **coverage** | ⚠️ **Not live-verified** — endpoint gated by auth (see Blocker 1) |
| Acceptable **uptime / reliability** | ❌ **Failing now** — DB connection pool exhausted (see Blocker 2) |

**Two blockers must be resolved before Lodestone can rely on this service:**
1. **Auth** — `/api/v1/*` now requires `Authorization: Bearer <token>`; Lodestone
   has no token and coverage cannot be exercised without one.
2. **Reliability** — the live service degraded to `connection pool exhausted`
   under light probing and did **not** recover within ~5 minutes; the
   reverse-geocode endpoint returns `503` in this state.

---

## What was verified

### 1. Service reachability & hosting ✅
- `GET /health` → `200` with `{"status":"ok","service":"wof-api","database":"healthy"}` (initial probe).
- Hosting headers: `server: railway-hikari`, `x-railway-edge: railway/us-west2`,
  `x-hikari-trace: sjc1` → **Railway `us-west2` (San Jose)**. Excellent physical
  proximity for Bay Area activation reverse-geocode (sub-millisecond regional RTT
  from Bay Area clients; the SJC edge is the right region).

### 2. Endpoint contract ✅ (confirmed via public `GET /openapi.json`)
`GET /api/v1/hierarchy` — required query params `lat` (number), `lon` (number);
secured by `HTTPBearer`. Response `HierarchyResponse`:

```jsonc
// HierarchyResponse — every level is nullable
{
  "continent":     WOFRecord | null,
  "country":       WOFRecord | null,
  "region":        WOFRecord | null,
  "county":        WOFRecord | null,
  "locality":      WOFRecord | null,
  "neighbourhood": WOFRecord | null
}
// WOFRecord (all fields required)
{ "id": integer, "name": string, "placetype": string }
```

**Integration note:** every hierarchy level is independently nullable. Even a
successful Bay Area lookup may return `null` for some levels (the documented SF
example returns `locality` but `null` for `region`/`county`). `/integrations/region`
must treat each level as optional and not assume presence.

### 3. Latency ✅ (excellent)
Measured against the live deployment (HTTP/2, warm connection, TLS reused):

| Path | Cold (incl. DNS+TLS) | Warm TTFB |
|---|---|---|
| `/health` | ~0.32 s first hit | **24–50 ms** |
| `/api/v1/hierarchy` (auth/503 path) | — | **28–80 ms** |

Latency is **well within** any reasonable bar for activation reverse-geocode.
Latency is **not** a concern — connection-pool stability is (Blocker 2).

---

## Blockers

### Blocker 1 — `/api/v1/*` requires a Bearer token (coverage not live-verified)
The deployed service gates the data endpoints behind authentication that is
**not present in this repo's `main.py`** (the deployment is ahead of the repo):

```
$ curl -i https://wof.wherigo.live/api/v1/hierarchy?lat=37.7749&lon=-122.4194
HTTP/2 401
www-authenticate: Bearer
{"detail":"Missing or invalid Authorization header. Expected: Bearer <token>"}
```

- Public OpenAPI declares security schemes `HTTPBearer` and `HTTPBasic`.
- `/api/v1/hierarchy` and `/api/v1/place/{wof_id}` → `401` (require `HTTPBearer`).
- `/`, `/docs`, `/openapi.json`, `/health` are public (`200`).
- A token-management surface exists: `POST /admin/tokens` (form field `name`,
  protected by `HTTPBasic`), plus `/admin` and `/admin/tokens/{id}/revoke`.

**Impact:** Lodestone's `/integrations/region` will receive `401` unless it sends
`Authorization: Bearer <token>`. No token is available in this environment, so
**Bay Area coverage could not be exercised end-to-end.**

**Unblock path:** an operator with HTTPBasic admin creds mints a token via
`POST /admin/tokens` (name it e.g. `lodestone-integrations`), stores it as a
Lodestone secret, and the integration sends it on every call.

### Blocker 2 — DB connection pool exhaustion (reliability)
During light verification (~15 lightweight requests over ~2 minutes), the service
flipped from healthy to degraded and **stayed** degraded:

```
$ curl https://wof.wherigo.live/health
{"status":"degraded","service":"wof-api","database":"unhealthy","error":"connection pool exhausted"}

$ curl -i https://wof.wherigo.live/api/v1/hierarchy?lat=37.7749&lon=-122.4194
HTTP/2 503
{"detail":"Database connection pool exhausted"}
```

- Initial `/health` (23:29Z) reported `database: healthy`.
- After a short burst of health/hierarchy probes, `/health` reported
  `connection pool exhausted` and the hierarchy endpoint returned `503`
  (the DB-pool check short-circuits **before** the auth check).
- The pool did **not** recover after load stopped — still `degraded` ~5 minutes
  later. A correctly-sized pool that releases connections would recover in
  seconds. Non-recovery points to a **connection leak or undersized pool**
  (docs default `DB_MAX_CONNECTIONS=10`).

**Impact:** In this state, reverse-geocode calls fail with `503`. A pool that
exhausts under ~15 requests cannot support production activation load. This is
the single most important finding: **the dependency is currently unreliable.**

---

## Coverage assessment (indirect — pending token)
Live Bay Area coverage was **not** confirmed (Blocker 1). Indirect evidence that
US/Bay Area coverage exists in the dataset:
- Repo `API_DOCUMENTATION.md`: **258,937** US places (179,570 localities, 40,263
  neighbourhoods, 3,143 counties, …); San Francisco is the canonical example
  (`lat=37.7749&lon=-122.4194` → locality "San Francisco", id `85922583`).
- Initial `/health` reported the database healthy before pool exhaustion.

Confidence that the data covers the Bay Area is **high**, but this must be
**confirmed live** with a token across representative points (SF, Oakland, San
Jose, Fremont, Berkeley, Palo Alto, Mountain View) before sign-off.

---

## Recommendations for the Lodestone integration
1. **Provision a Bearer token** (`POST /admin/tokens` → secret store) and send
   `Authorization: Bearer <token>` from `/integrations/region`.
2. **Fix Blocker 2 before depending on the service**: investigate the suspected
   connection leak, raise `DB_MAX_CONNECTIONS`, and confirm the pool recovers
   under sustained load. Re-run this verification afterward.
3. **Defensive client behavior** in `/integrations/region`:
   - Handle `401` (missing/expired token) and `503` (pool exhausted) explicitly.
   - Add timeout + retry-with-backoff and a circuit breaker so a degraded
     `wof.wherigo.live` cannot stall activation.
   - Treat every hierarchy level as nullable.
4. **Add uptime monitoring** (Railway metrics + an external pinger on `/health`)
   to establish an actual SLA — single-session checks cannot measure historical
   uptime.
5. **Reconcile repo ↔ deployment**: the live auth + `/admin/tokens` system is not
   in this repo. Commit the deployed code so the source of truth matches prod.

---

## Reproduction (commands used)
```bash
# Health + hosting region
curl -i https://wof.wherigo.live/health

# Contract (public, no auth)
curl -s https://wof.wherigo.live/openapi.json | jq '.paths, .components.securitySchemes'

# Endpoint behavior (gated)
curl -i "https://wof.wherigo.live/api/v1/hierarchy?lat=37.7749&lon=-122.4194"   # 401 (or 503 when pool exhausted)

# Coverage check once a token exists:
TOKEN=...   # mint via POST /admin/tokens
for p in "37.7749 -122.4194 SF" "37.8044 -122.2712 Oakland" "37.3382 -121.8863 SanJose" \
         "37.5485 -121.9886 Fremont" "37.8715 -122.2730 Berkeley" "37.4419 -122.1430 PaloAlto"; do
  set -- $p
  echo "== $3 =="; curl -s -H "Authorization: Bearer $TOKEN" \
    "https://wof.wherigo.live/api/v1/hierarchy?lat=$1&lon=$2" | jq .
done
```
