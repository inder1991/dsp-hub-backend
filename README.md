# DSP Portal Backend

FastAPI aggregation service for the DSP Portal. Release one serves stable API contracts backed by illustrative data and configurable links. Later phases can replace the static service with VM, Hadoop, Trino, Nexus, GitHub, workspace, job, release-calendar, and identity adapters.

## Run locally

Requirements: Python 3.9+.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -e '.[dev]'
cp .env.example .env
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Configure the actual Confluence and Remedy destinations in `.env` before a release-one deployment. Empty values are returned as `null`; the frontend then presents the option as planned/unconfigured rather than opening a fake URL.

Support destinations can be overridden per service with one environment map:

```env
DSP_SUPPORT_SERVICE_LINKS={"cyberark":{"remedyUrl":"https://remedy.example/cyberark","confluenceUrl":"https://confluence.example/cyberark","teamsUrl":"https://teams.example/cyberark"},"nexus":{"remedyUrl":"https://remedy.example/nexus","confluenceUrl":"https://confluence.example/nexus","teamsUrl":"https://teams.example/nexus"}}
```

Supported service keys are `dev-container`, `cyberark`, `nexus`, `compute`, `cdp`, `trino`, and `sas`. Each value is optional. The generic Remedy and Confluence settings remain fallbacks for services without an override.

`DSP_TEAMS_SUPPORT_URL`, `DSP_SUPPORT_ROSTER_NAME`, and `DSP_SUPPORT_ROSTER_ROLE` configure the central DSP support contact shown in the support-page header. Per-service `teamsUrl` values configure the individual specialists and do not fall back to the central DSP support chat.

## API

- `GET /healthz` — service liveness.
- `GET /api/v1/home` — complete operational homepage payload.
- `GET /api/v1/health/summary` — compact payload for the persistent health control.
- `GET /api/v1/support` — read-only service guides, roster contacts, and escalation links.
- `GET /api/v1/onboarding` — onboarding journey, access requirements, bootcamp, and training catalog.
- `GET /docs` — generated OpenAPI interface.

Responses use camelCase to match TypeScript conventions while the Python models remain snake_case.

## Quality gates

```bash
.venv/bin/python -m pytest
.venv/bin/ruff check app tests
.venv/bin/ruff format --check app tests
```

## Phase-two extension model

`app/services/dashboard.py` is the release-one static adapter. Replace it incrementally with service-specific adapters while keeping `app/models/dashboard.py` stable for the frontend. Recommended adapters include:

- identity and user-to-resource relationships;
- VM/workspace inventory;
- Hadoop and Trino health;
- Nexus availability and package releases;
- GitHub activity and builds;
- change-calendar impact analysis;
- incident and Remedy context.

The backend should continue aggregating operational signals; it should not become a duplicate UI for systems that already have mature interfaces.
