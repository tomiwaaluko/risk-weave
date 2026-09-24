# RIS-40 — Railway Redis public TCP proxy removal

Date: 2026-09-24  
Linear: [RIS-40](https://linear.app/risk-weave/issue/RIS-40/railway-redis-is-publicly-reachable-via-tcp-proxy-6379)  
Origin: Finding F2 from [RIS-35](https://linear.app/risk-weave/issue/RIS-35/security-review-pass-for-the-live-deployment-rw-sec-001004) (`docs/solutions/security/RIS-35-live-deployment-security-review.md` §4).

## Problem

The Railway Redis service was reachable from the public internet via a TCP proxy
on application port 6379 (`REDIS_PUBLIC_URL` present). Redis was
password-protected (`redis-server --requirepass …`), but the cache port should
not be public — the backend reaches Redis over Railway private networking.

## Remediation actions (Railway production)

| Step | Result |
| --- | --- |
| Public TCP proxy on Redis :6379 | **Removed** |
| Backend uses private `REDIS_URL` (not `REDIS_PUBLIC_URL`) | **Confirmed** |
| Redis password rotated after exposure | **Rotated** |
| Backend `/health` after remediation | **Succeeded** (`200`, `{"status":"ok"}`) |

### Proxy removal

- Listed TCP proxies for Redis; one ACTIVE proxy forwarded a public Railway
  `*.proxy.rlwy.net` endpoint to application port 6379.
- Deleted that proxy only. Did not delete the Redis service, its volume, private
  networking, or the backend service.
- Postgres was not modified (owned by RIS-39).
- Re-listed Redis TCP proxies afterward: **none**.

### Private `REDIS_URL` confirmation

- Backend variable names include `REDIS_URL` and do **not** include
  `REDIS_PUBLIC_URL`.
- Backend `REDIS_URL` is a Railway reference to the Redis service’s `REDIS_URL`
  (not a literal connection string on the backend).
- Resolved Redis hostname ends with `.railway.internal` (private network).
- Redis retains private network endpoint `redis`.

### Password rotation

- After closing the public proxy, rotated Redis auth via Railway:
  - `REDIS_PASSWORD` regenerated with Railway `secret(32)`.
  - `REDIS_URL` updated to embed the new password while keeping the private
    `redis.railway.internal` host.
  - `REDISPASSWORD` already references `${{REDIS_PASSWORD}}`, so it followed.
- Backend continued to reference Redis `REDIS_URL`, then redeployed so the
  reference resolved to the rotated credentials.
- Deploy logs after rotation showed `redis connected` on backend startup.
- No password, URL, or connection string values were written into the
  repository, this document, or the PR.

### Health verification

- Public `GET https://backend-production-b2dc.up.railway.app/health` returned
  **HTTP 200** with body `{"status":"ok"}` on 2026-09-24 after remediation.
- During verification, public edge traffic was initially failing with 502
  because the service domain targeted container port **8000** while uvicorn
  listens on **8080**. The domain target port was updated to **8080** so the
  public health check could succeed. This was a pre-existing port mismatch,
  not caused by Redis proxy removal; internal Railway health probes already
  returned 200 and logs already showed `redis connected`.

## Outcome

RIS-40 F2 exposure is closed for Redis: no public TCP proxy, private
`REDIS_URL` wiring confirmed, password rotated after internet exposure, and
backend health verified succeeding.
