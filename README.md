# DSP Portal Backend

## Architecture

- [DSP Portal data model](docs/architecture/data-model.md)
- [Authentication architecture: Ping SSO, local users, and portal roles](docs/architecture/ping-sso-integration-plan.md)

FastAPI aggregation service for the DSP Portal. Release one serves stable API contracts backed by illustrative data and configurable links. Later phases can replace the static service with VM, Hadoop, Trino, Nexus, GitHub, workspace, job, release-calendar, and identity adapters.

## Run locally

Requirements: Python 3.11+ and PostgreSQL.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -e '.[dev]'
cp .env.example .env
.venv/bin/alembic upgrade head
# Optional one-time bootstrap after setting the three DSP_BOOTSTRAP_ADMIN_* values:
.venv/bin/python -m app.auth.bootstrap
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Ping is available when its required `DSP_SAML_*` values are complete. Local
accounts are always supported; there are no authentication enable/disable or
SAML strictness flags. JWT keys, Ping certificates, and database credentials
are supplied at runtime and are never embedded into a frontend or container
image. See [.env.example](.env.example) for the complete configuration surface.

## Authentication API

- `GET /auth/config` — derived provider availability; no sensitive settings.
- `GET /auth/login` — starts SP-initiated Ping SAML login.
- `POST /auth/saml/acs` — validates Ping's signed response.
- `POST /auth/exchange` — consumes the browser-bound 60-second exchange code.
- `POST /auth/local/login` — authenticates a governed local account.
- `POST /auth/local/password-action` — consumes a one-time local setup/reset code.
- `POST /auth/refresh` and `POST /auth/logout` — rotate or revoke the cookie session.
- `GET /auth/me` — current principal, provider, role, and permissions.
- `/auth/admin/local-users` — `ADMIN`-only local-account governance and one-time password actions.

All `/api/v1/*` routes require a bearer access token. The admin control plane
also requires the canonical `ADMIN` role; all other authenticated principals
have `READ_ONLY` access subject to their resource scope.

## Container build

The backend image includes the reusable `enterprise_auth` package and the
native XML security runtime required by `python3-saml`. Configuration and
secrets are runtime inputs, so the same image can be promoted between
environments:

```bash
docker build -t dsp-portal-backend:local .
docker run --env-file .env -p 8000:8000 dsp-portal-backend:local
```

Run `alembic upgrade head` as a controlled deployment step before rolling out
the API. Application containers do not mutate the database schema at startup.
Schedule `python -m app.auth.cleanup` to delete expired authentication state in
bounded batches; expiration is still checked transactionally on every consume.

Configure the actual Confluence and Remedy destinations in `.env` before a release-one deployment. Empty values are returned as `null`; the frontend then presents the option as planned/unconfigured rather than opening a fake URL.

Support destinations can be overridden per service with one environment map:

```env
DSP_SUPPORT_SERVICE_LINKS={"cyberark":{"remedyUrl":"https://remedy.example/cyberark","confluenceUrl":"https://confluence.example/cyberark","teamsUrl":"https://teams.example/cyberark"},"nexus":{"remedyUrl":"https://remedy.example/nexus","confluenceUrl":"https://confluence.example/nexus","teamsUrl":"https://teams.example/nexus"}}
```

Supported service keys are `dev-container`, `cyberark`, `nexus`, `compute`, `cdp`, `trino`, and `sas`. Each value is optional. The generic Remedy and Confluence settings remain fallbacks for services without an override.

`DSP_TEAMS_SUPPORT_URL`, `DSP_SUPPORT_ROSTER_NAME`, and `DSP_SUPPORT_ROSTER_ROLE` configure the central DSP support contact shown in the support-page header. Per-service `teamsUrl` values configure the individual specialists and do not fall back to the central DSP support chat.

## API

- `GET /healthz` — service liveness.
- `GET /readyz` — PostgreSQL/JWT dependency readiness and independent Ping status.
- `GET /api/v1/home` — complete operational homepage payload.
- `GET /api/v1/health/summary` — compact payload for the persistent health control.
- `GET /api/v1/support` — read-only service guides, roster contacts, and escalation links.
- `GET /api/v1/onboarding` — onboarding journey, access requirements, bootcamp, and training catalog.
- `GET /api/v1/devspaces` — devspace ownership, host VM, image, health, CPU, memory, disk, running age, connections, and the latest VM issues.
- `GET /api/v1/jobs` — Kedro runs correlated with their owner, devspace, host VM, node progress, resource peaks, and failure context.
- `GET /api/v1/vms` — VM fleet health, capacity, workload, user, job, and current-issue inventory.
- `GET /api/v1/devspaces/{devspace_id}` — complete devspace observability view including metrics, jobs, processes, runtime configuration, and host issues.
- `GET /api/v1/vms/{vm_id}` — VM facts, capacity, hosted devspaces, associated users, issue history, and top processes.
- `GET /api/v1/data-access` — user-scoped Hive table entitlements, LDAP/team access path, morning ingestion outcome, and team YARN queues.
- `GET /api/v1/admin/control-plane` — cross-team operational attention, Hive access/ingestion, YARN queues, integrations, VM allocation workflows, and published updates.
- `GET /docs` — generated OpenAPI interface.

Responses use camelCase to match TypeScript conventions while the Python models remain snake_case.

The Hive APIs are metadata-only. They never return or persist Hive rows, samples, column values, query results, or downloadable table contents.

## Quality gates

```bash
.venv/bin/python -m pytest
.venv/bin/ruff check app enterprise_auth migrations tests
.venv/bin/ruff format --check app enterprise_auth migrations tests
```

## Phase-two extension model

`app/services/dashboard.py`, `app/services/devspaces.py`, `app/services/observability.py`, and `app/services/data_platform.py` are release-one static adapters. Replace them incrementally with service-specific adapters while keeping their response models stable for the frontend. Recommended adapters include:

- identity and user-to-resource relationships;
- VM/workspace inventory;
- Hadoop and Trino health;
- Nexus availability and package releases;
- GitHub activity and builds;
- change-calendar impact analysis;
- incident and Remedy context.
- Hive Metastore/Ranger access metadata, ingestion monitoring, and YARN ResourceManager queue status.

The backend should continue aggregating operational signals; it should not become a duplicate UI for systems that already have mature interfaces.
