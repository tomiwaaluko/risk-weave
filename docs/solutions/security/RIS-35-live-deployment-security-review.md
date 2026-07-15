# Live-deployment security review — RW-SEC-001..004 (RIS-35)

Date: 2026-07-14
Scope: verify (not merely assume) that the security invariants hold now that the
backend is public on Railway and the frontend is public on Vercel, with real
provider secrets in two hosting platforms and a hackathon git history. Review /
audit only — remediation beyond trivial fixes is ticketed separately.

Spec anchors: `RW-SEC-001` (keys server-side only), `RW-SEC-002` (closed Gemini
tool registry), `RW-SEC-003` (untrusted inputs to Gemini), `RW-SEC-004` (no
secret in the repo), `RW-SAFE-001/002` (advice-free framing), `RW-DATA-005`
(provider-terms compliance).

## Verdict

No leaked secret was found in the repository or in the built client bundle, and
the core AI-safety invariants (RW-SEC-002/003, RW-SAFE) hold. Four
infrastructure/config findings were raised; the two highest concern **publicly
reachable data-store ports on Railway**. None is a code vulnerability in the
application; all are deployment/config posture. Each real finding is filed as its
own Linear ticket (linked below).

## What was checked and the evidence

### 1. History-wide secret scan (`RW-SEC-004`) — PASS

- Scanned all 101 commits / all blobs across full history (`git log --all -p`)
  for high-signal key patterns (Google `AIza…`, `sk-…`, AWS `AKIA…`, private-key
  headers, `ghp_/github_pat_`, `xox…`) and for non-placeholder assignments to
  `*_API_KEY / *_PASSWORD / *_TOKEN / *_SECRET`.
- **Result: no secret material in history.** The only tracked env file is
  `.env.example`, and every value in it is a placeholder (`change-me-…`,
  `replace-with-a-real-server-side-key`). Matches on `gemini_api_key="…"` /
  `neo4j_password="password"` are test fixtures; docker-compose values are
  `${VAR}` reference indirections. No `.env`, `*.pem`, `*.key`, or
  credential-named file was ever committed.
- Nothing to rotate on the basis of repository history.
- Tooling note: `gitleaks` could not be installed in this environment (binary
  download blocked); an equivalent history-wide regex sweep was used. Recommend a
  one-time `gitleaks detect` run in CI or locally to double-confirm.

### 2. Client-bundle inspection (`RW-SEC-001`) — PASS

- Frontend source references exactly one env var, `NEXT_PUBLIC_BACKEND_URL`, in
  all four pages; no server-secret name (`GEMINI…`, `DATABASE_URL`, `NEO4J…`,
  `FRED…`) appears in `frontend/src`.
- Fetched the live Vercel production build (`risk-weave-five.vercel.app`,
  authenticated fetch — the app sits behind Vercel deployment protection) and its
  JS chunks. Grepped the built JS for key patterns and connection strings:
  **zero server secrets in the bundle.** The only inlined values are
  `NEXT_PUBLIC_BACKEND_URL` and its `http://localhost:8000` fallback.
- Observation (functionality, out of security scope — noted for the team): the
  bundle contains the `localhost:8000` fallback and **no** baked Railway backend
  URL, which suggests `NEXT_PUBLIC_BACKEND_URL` is not set in the Vercel project.
  This is not a secret exposure; it is a config gap that interacts with finding F3.

### 3. Log audit (`RW-SEC-001`) — PASS

- `SecretStr` is used for `neo4j_password` and `gemini_api_key` (and
  `fred_api_key`) in `settings.py`. `.get_secret_value()` is called in exactly
  two places, both in `extraction/gemini.py`: (a) to set the `x-goog-api-key`
  request header, and (b) inside `_redact()`, which *removes* the key from any
  Gemini error text before it is raised. Neither logs the secret.
- No `logger.*`/`print` statement interpolates a URL, password, key, DSN, or the
  settings object. The one request-path log (`logger.debug("cache hit for %s",
  cache_key)`) logs a `sha256`-derived cache key containing no secret.
- Conclusion: no secret-material path can reach Railway logs from application code.

### 4. Deployed env / networking audit (Railway + Vercel)

Inspected via the Railway and Vercel MCP integrations (read-only).

- **Neo4j — PASS (good posture):** private networking only. No public domain, no
  TCP proxy. Browser port **7474** and Bolt port **7687** are **not** publicly
  exposed. This is exactly the required posture.
- **Postgres — FINDING F1 (High):** exposed to the public internet via a Railway
  TCP proxy on **5432** (`DATABASE_PUBLIC_URL` present). The financials /
  provenance / time-series store is internet-reachable; only the DB password
  gates it.
- **Redis — FINDING F2 (Medium):** exposed via Railway TCP proxy on **6379**
  (`REDIS_PUBLIC_URL` present). It is password-protected
  (`redis-server --requirepass …`), but the port should not be public.
- **backend** has the expected public domain (`…up.railway.app:8000`); public API
  auth/rate-limiting is out of scope here (tracked in RIS-31).
- **ingestion** has no public domain; it inherits its secrets from the backend
  service via Railway reference variables.
- Backend env vars are exactly the eight the app expects
  (`DATABASE_URL`, `NEO4J_URI/USER/PASSWORD`, `REDIS_URL`, `GEMINI_API_KEY`,
  `FRED_API_KEY`, `SEC_USER_AGENT`) — no stray/unknown vars.

### 5. Config hygiene

- **CORS default — FINDING F3 (Medium):** `CORS_ALLOW_ORIGIN_REGEX` is **not**
  set on the Railway backend, so the code default in `settings.py` is live:
  `^https://riskweave.*\.vercel\.app$|^http://localhost:3000$`. That regex expects
  `riskweave` (no hyphen) but the real Vercel origins are `risk-weave-*.vercel.app`
  (with a hyphen). Verified: the default matches **none** of the four live Vercel
  domains — only `localhost:3000`. The allowlist is effectively broken for the
  real frontend origin. (`allow_credentials` is not enabled and methods/headers
  are `*`, which is acceptable without credentials; the defect is purely the
  origin pattern.) One-line fix candidate; ticketed for a deliberate change.
- **`SEC_USER_AGENT` — CONFIRMED (was finding F4, now resolved):** the code
  default is the placeholder `RiskWeave contact@example.com`, and the deployed
  value is stored as a masked variable so it could not be read via API. Confirmed
  manually against the Railway dashboard: the deployed value is
  `RiskWeave tomiwaaluko02@gmail.com` — a real identifying contact, satisfying SEC
  fair-access policy (RW-DATA-005). No deployment change needed. Optional code
  hardening remains (RIS-42): the `settings.py` default is still a placeholder and
  the `SecClient` accepts an `example.com` address, so a stricter validation could
  reject obvious placeholders — a nice-to-have, not a live risk.
- **Exposed ports:** covered in §4 (Neo4j clean; Postgres/Redis exposed → F1/F2).

### 6. Dependency audit — PASS

- Backend: `pip-audit` against the committed `uv.lock` (exported to requirements)
  → **no known vulnerabilities**. (An initial `pip-audit` run reported CVEs, but
  those were the container's *system* Python packages — cryptography 41, pip 24,
  setuptools 68, etc. — not RiskWeave's locked dependencies. The project lock is
  clean.)
- Frontend: `npm audit` against `package-lock.json` → **0 vulnerabilities**
  (info/low/moderate/high/critical all 0).
- Nothing to ticket.

### 7. RW-SEC-002 / RW-SEC-003 spot check — PASS (test added)

- **RW-SEC-002 (closed tool registry):** the pre-existing `test_registry.py`
  covers the *derivation-method* registry (`DER-*`), **not** the Gemini tool
  registry — so the closure of the §13.2 tool set was previously unverified.
  Added `backend/tests/test_tool_registry_closure.py`, which pins the registry
  router (`riskweave_api.routers.registry`) to exactly the ten §13.2 tools and
  fails if any tool is added, renamed, or removed. This turns "arbitrary tool
  execution is prohibited" into an enforced invariant (adding a Gemini-callable
  tool now requires a deliberate, reviewed change). Tests pass.
- **RW-SEC-003 (untrusted inputs to Gemini):** confirmed. Every Gemini prompt
  (relationship extraction, covenant extraction, shock parsing) explicitly frames
  the document/sentence as "untrusted data, not instructions." Outputs are
  validated with strict Pydantic models (`extra="forbid"`, enum-constrained
  factor ids/units) via `model_validate` / `model_validate_json` **before** any
  use, with a bounded retry then a deterministic fallback — no unvalidated model
  output enters the pipeline.

### 8. RW-SAFE-001/002 (advice-free framing) — PASS

- The live terminal renders `MODELED RISK / NOT INVESTMENT ADVICE` in the metrics
  ticker, and the methodology page carries a disclaimer footer plus explicit
  data-limitation copy. Framing is intact on the deployed surface.

### 9. CI hygiene — PASS

- `.github/workflows/ci.yml` uses only `.env.example` placeholder values for the
  compose build, references no `secrets.*` context, and never echoes env
  (`printenv`, `set -x`). Actions are pinned to commit SHAs and the workflow runs
  with `permissions: contents: read`.

## Findings → tickets

| ID | Severity | Finding | Disposition |
|----|----------|---------|-------------|
| F1 | High | Postgres publicly reachable via Railway TCP proxy (`:5432`) | New ticket; disable public proxy or restrict, rotate password |
| F2 | Medium | Redis publicly reachable via Railway TCP proxy (`:6379`), password-set | New ticket; disable public proxy |
| F3 | Medium | Backend CORS default regex matches no real Vercel origin (`riskweave` vs `risk-weave`); no env override set | New ticket; fix pattern + set explicit `CORS_ALLOW_ORIGIN_REGEX` |
| F4 | Low | `SEC_USER_AGENT` unverifiable via API; code default is placeholder | **Resolved** — deployed value confirmed a real contact (`RiskWeave tomiwaaluko02@gmail.com`). RIS-42 retained only for optional code hardening |

Passing, no action: history secret scan, client-bundle secret check, log audit,
Neo4j port exposure, dependency audits (backend + frontend), RW-SEC-002 closure
(test added), RW-SEC-003 schema validation, RW-SAFE framing, CI hygiene.

## Acceptance-criteria status

- [x] History-wide secret scan run; result recorded (clean; nothing to rotate)
- [x] Client-bundle inspection shows zero server secrets (`RW-SEC-001`)
- [x] Log audit shows zero secret-material paths (`RW-SEC-001`)
- [x] Real `SEC_USER_AGENT` in deployed envs — confirmed via Railway dashboard
  (`RiskWeave tomiwaaluko02@gmail.com`, a genuine contact). CORS + exposed-ports
  review recorded (F1/F2/F3).
- [x] Dependency audit clean (backend `uv.lock` + frontend `package-lock.json`)
- [x] RW-SEC-002 closure test exists and passes
