# DSP Portal Data Model

Status: Approved logical model v3

Owner: DSP Platform

Last reviewed: 2026-08-26

The DSP Portal is an operational aggregation layer. PostgreSQL owns portal identity mappings, resource inventory, relationships, execution metadata, derived health, impact mappings, and portal-owned state. LDAP, Compute, Nexus, GitHub, Remedy, Confluence, and the monitoring platform remain authoritative for their respective domains.

The renderable relational definition is maintained in [`data-model.dbml`](./data-model.dbml). Alembic migrations will become the authoritative physical schema when persistence is implemented.

## Architectural decisions

1. Use PostgreSQL for durable relational data and relationship traversal. The expected scale does not justify a separate graph database.
2. Keep Pydantic API response models separate from persistence models. Homepage, VM, devspace, and job responses are derived read models.
3. Separate resource lifecycle from health. A stopped devspace is a lifecycle state, not an unhealthy resource.
4. Represent LDAP groups and business teams independently. Explicit bindings relate groups to teams and entitlements.
5. Give every user an internal DSP principal ID and preserve external directory identifiers separately.
6. Model VM addresses through interfaces and temporal IP assignments. IP addresses are attributes, never resource identifiers.
7. Preserve temporal history for LDAP membership, team membership, access, devspace placement, and IP assignment.
8. Snapshot VM, image digest, and Git commit on every job run so historical execution context cannot change.
9. Keep high-frequency metrics and logs outside PostgreSQL. Store only operational metadata, state changes, and references.
10. Never store plaintext or reversible passwords, CyberArk credentials, service tokens, or unredacted secrets. Governed local accounts store only encoded Argon2id password hashes with per-password salts.
11. Store Hive catalogue identity, entitlement, and ingestion metadata only. The portal must never persist or expose Hive rows, samples, column values, query results, or downloadable table contents.
12. Treat administrator mutations as governed workflows with requester, approval, execution, and audit states. A portal record is not proof that an infrastructure change completed.
13. Use PostgreSQL—not Redis or process memory—for release-one SAML login transactions, replay markers, one-time exchange codes, refresh sessions and governed local accounts. Store only hashes and expiry metadata for browser/session values; never persist raw SAML assertions, plaintext browser codes/session identifiers or plaintext/reversible passwords.
14. Give every active human principal exactly one portal capability role: `READ_ONLY` by default or explicitly governed `ADMIN`. Capability role and resource scope are independent controls.

## Conceptual relationships

```mermaid
flowchart LR
    IDP[Identity provider] --> PI[Principal identity]
    PI --> P[Principal / DSP user]
    P --> LA[Local account]
    LA --> LPA[Password setup / reset action]
    IDP --> SLT[SAML login transaction]
    SLT --> AEC[One-time exchange code]
    P --> AEC
    P --> ARS[Refresh session]
    IDP --> LG[LDAP group]
    P --> GM[Group membership]
    LG --> GM
    P --> TM[Team membership]
    T[Team] --> TM
    LG --> TGB[Team-group binding]
    T --> TGB

    P --> AS[Access subject]
    T --> AS
    LG --> AS
    AS --> RA[Resource access]
    AS --> SE[Service entitlement]
    AS --> HTE[Hive table entitlement]
    HT[Hive table metadata] --> HTE
    HT --> MIS[Morning ingestion snapshot]
    T --> YQ[YARN queue]
    YQ --> YQS[YARN queue snapshot]

    TEN[DSP tenant] --> R[Resource registry]
    R --> VM[VM]
    VM --> NI[Network interface]
    NI --> IP[IP assignment]
    TEN --> SUB[Network subnet / CIDR]
    SUB --> IP

    R --> DS[Devspace]
    VM --> DP[Devspace placement]
    DS --> DP
    IMG[Image version / digest] --> DS
    DS --> JR[Kedro job run]
    JR --> NR[Node run]
    JR --> JA[Job artifact]

    R --> HA[Health assessment]
    SVC[Platform service] --> HA
    INC[Incident] --> II[Incident impact]
    R --> II
    SVC --> II
    CHG[Planned change] --> CI[Change impact]
    R --> CI
```

## Domain model

### Integration and provenance

- `source_system` identifies LDAP, Compute, Podman/runtime, Nexus, GitHub, Remedy, Confluence, and monitoring integrations.
- `operational_event` provides an idempotent event envelope using `(source_system_id, external_event_id)`.
- Source-fed records carry `observed_at`; time-sensitive assessments additionally carry `valid_until`.

### Identity, LDAP, and teams

- `principal` is the internal DSP identity. Its UUID is the application user ID.
- `principal.portal_role` is exactly `ADMIN` or `READ_ONLY`; `authorization_version` changes whenever role/status authorization changes.
- `principal_identity` stores enterprise user ID, username, UPN, LDAP DN, and immutable directory object ID.
- `directory_group` stores LDAP/AD groups.
- `directory_group_membership` supports both user-to-group and nested group-to-group membership.
- `team` is a business/DSP concept and owns the canonical team name.
- `team_membership` relates users to teams and records whether membership came from HR, LDAP mapping, or manual administration.
- `team_group_binding` maps one or more LDAP groups to a team without treating the group as the team itself.
- `access_subject` allows a principal, team, or LDAP group to receive resource access and service entitlements.

### Authentication state

- `saml_login_transaction` correlates an SP-initiated request with RelayState, the request ID, browser-binding nonce and safe return path. Rows expire after five minutes and are consumed transactionally by the ACS.
- `saml_assertion_replay` stores only hashed assertion identifiers until the assertion expiry so a valid assertion cannot be accepted twice.
- `auth_exchange_code` stores only a hash of the 60-second, single-use browser exchange code and its browser-binding nonce hash. Consumption uses an atomic `DELETE ... RETURNING` operation.
- `auth_refresh_session` stores only a hash of the refresh-session identifier together with revocation, rotation, authorization-version and expiry metadata.
- `local_account` maps one case-insensitive local username to one principal and stores only its encoded Argon2id hash and governed account/lock/expiry facts.
- `local_password_action` stores a hash of a short-lived, single-use initial-setup or reset code. Administrators never retrieve a permanent password.
- Issuing a new `local_password_action` consumes any older outstanding code for the same account, preventing an earlier setup/reset link from becoming valid again.
- `auth_rate_limit_bucket` provides shared PostgreSQL rate limiting across API replicas without storing raw usernames or source addresses.
- `auth_idempotency_key` prevents duplicate administrator mutations such as account provisioning, role changes, expiry changes, and reset issuance.
- `authentication_audit_event` captures correlation, actor, target, outcome, reason, and approved before/after state without assertions, credentials, cookies, codes, or tokens.
- Expired state is rejected in consuming SQL regardless of cleanup timing. A bounded cleanup job removes expired records.
- These tables never contain the raw SAML response/assertion, plaintext RelayState, plaintext exchange code, plaintext browser nonce, plaintext refresh-session identifier, plaintext/reversible password or signing key.

### Tenants, resources, and access

- `dsp_tenant` represents a controlled DSP allocation: VM set, IP range, environment, and ownership boundary.
- `resource` provides stable internal IDs and external source mappings for VMs, devspaces, repositories, images, and pipelines.
- Typed extension tables contain operational fields; queryable attributes must not be placed in an EAV structure.
- `resource_access` assigns owner, contributor, viewer, or support roles to an access subject.
- `service_entitlement` records access to CDP, Trino, SAS, CyberArk, Nexus, GitHub Actions, and other platform services without storing credentials.

### VM and network inventory

- `vm` extends a resource with hostname, FQDN, host group, operating system, runtime, capacity, and patch facts.
- `network_zone` identifies controlled network/security boundaries.
- `network_subnet` stores tenant CIDRs using PostgreSQL `CIDR`.
- `network_interface` stores VM interfaces and MAC addresses.
- `ip_assignment` stores temporal primary, secondary, or NAT addresses using PostgreSQL `INET`.
- IP and CIDR fields are security-sensitive and must be filtered by authorization policy before being returned by an API.

### Devspaces and software supply chain

- `artifact_repository` represents Nexus container or Python repositories.
- `image_version` stores both the human-readable tag and immutable image digest.
- `devspace` stores runtime identity, resource limits, lifecycle timestamps, and last activity.
- `devspace_placement` preserves VM placement history and permits only one active placement per devspace.
- `devspace_service_binding` records current connectivity to platform services.

### GitHub and Kedro execution

- `git_repository`, `kedro_project`, `pipeline_definition`, and `pipeline_version` describe versioned executable code.
- `job_run` records a Kedro execution and snapshots its VM, image digest, and Git commit.
- `job_node_run` records node-level progress and failure context.
- `job_artifact` references models, datasets, reports, and metrics produced by a run.
- Local Kedro hooks should emit start, node, completion, and failure events; the portal must not run commands inside a devspace.

### Hive access, morning ingestion, and YARN

- `hive_table` is a catalogue identity only: database, table name, owning team, source ID, and lifecycle metadata.
- `hive_table_entitlement` relates a table to an `access_subject`, normally an LDAP group or team, with its Ranger privilege and policy reference.
- `morning_ingestion_snapshot` stores one operational outcome per Hive table and business date, including scheduled/completion time, status, SLA state, and a short operational summary.
- `yarn_queue` maps a queue path to its owning team and, where applicable, its LDAP access group.
- `yarn_queue_snapshot` stores time-series operational queue capacity, application counts, and allocated/pending memory.
- These tables intentionally contain no Hive schema details, rows, samples, column values, query output, storage locations, or download references.

### Governed administration

- `vm_allocation_request` records the requested tenant/team/LDAP allocation, approval state, and eventual execution reference.
- Creating or approving a request does not directly mutate Compute or LDAP. An authenticated adapter executes the approved change and reports the result separately.
- Maintenance, support, troubleshooting, and documentation publishing reuse their domain records with explicit draft/review/scheduled/published state and an audit trail in `operational_event`.

### Health, incidents, and changes

- `platform_service` defines Compute, CyberArk, Nexus, CDP, Trino, SAS, GitHub Actions, and other operational services.
- `health_assessment` is an append-only evaluation for either a resource or a platform service.
- `incident` stores a local reference to an externally owned incident, normally Remedy.
- `incident_impact` relates incidents to affected resources and services.
- `planned_change` and `change_impact` support personalized maintenance and release impact.

### Support, onboarding, and user continuity

- `troubleshooting_guide` and `common_issue` hold searchable guide metadata and Confluence deep links.
- `support_route` keeps service-specific Teams, Remedy, and Confluence routes.
- `support_roster_shift` identifies the current DSP or service specialist.
- `ticket_reference` stores only Remedy identifiers, state, and deep links—not a duplicate ticket body.
- Onboarding tables track programs, steps, entitlements, training, bootcamp sessions, and completion.
- `notification` and `user_notification_state` provide personalized attention and read state.

## Critical invariants

- External identity: `UNIQUE(identity_provider_id, external_object_id)`.
- SAML login correlation: unique RelayState hash and SAML request ID.
- SAML replay protection: `UNIQUE(identity_provider_id, assertion_id_hash)` until assertion expiry.
- Authentication exchange: unique code hash, atomic one-time consumption, and a fixed 60-second expiry.
- Refresh session: unique session-ID hash with transactional rotation and revocation.
- Local identity: one local account per principal and a case-insensitive unique username.
- Portal role: exactly one of `ADMIN` or `READ_ONLY`; `READ_ONLY` is the default.
- Local password action: unique action-code hash with transactional one-time consumption.
- Source resource: `UNIQUE(source_system_id, external_id)`.
- Event ingestion: `UNIQUE(source_system_id, external_event_id)`.
- Exactly one member target on each directory membership: principal or nested group.
- Exactly one subject target on each access subject: principal, team, or directory group.
- Exactly one health target: resource or platform service.
- Exactly one incident impact target: resource or platform service.
- At most one active VM placement for a devspace.
- At most one active primary address per VM interface/address family.
- A Hive table is unique within its source catalogue by database and table name.
- A morning ingestion snapshot is unique per Hive table and business date.
- A YARN queue path is unique within its source ResourceManager.
- Hive entitlement targets are metadata-only and must resolve through an access subject.
- Image digest is immutable after creation.
- Job execution snapshot fields are immutable after a run starts.
- All stored timestamps use UTC `TIMESTAMPTZ`; relative strings such as `2h ago` are generated only by the UI.
- Memory and storage use bytes, CPU uses cores or millicores, IP uses `INET`, and network ranges use `CIDR`.
- Percentages and running ages are derived, not persisted as authoritative values.

## Storage ownership

| Data | Authoritative store |
|---|---|
| Portal identity mappings, teams, inventory, relationships | PostgreSQL |
| SAML login, replay, exchange-code, and refresh-session state | PostgreSQL authentication schema |
| Local users, Argon2id password hashes, account lock/expiry and password-action state | PostgreSQL authentication schema |
| LDAP users and groups | Enterprise directory |
| VM provisioning facts | Compute platform |
| Devspace/runtime inventory | Podman/runtime integration |
| Images and Python packages | Nexus |
| Repositories and workflows | GitHub/GitHub Actions |
| Kedro run and node metadata | PostgreSQL from Kedro events |
| Hive table names and access entitlements | PostgreSQL projection from Hive Metastore/Ranger |
| Morning Hive ingestion outcomes | PostgreSQL from the ingestion monitor |
| YARN queue ownership and operational snapshots | PostgreSQL from YARN ResourceManager |
| Hive table contents, samples, values, and query results | Hive only; never stored by the portal |
| CPU, memory, storage, restart metrics | Prometheus/Thanos |
| Logs | Loki/OpenSearch |
| Short-lived process snapshots | Monitoring platform or live runtime adapter; no Redis in release one |
| Tickets and incidents | Remedy |
| Documentation | Confluence |
| Large model/report artifacts | Approved enterprise artifact/object store |

## API read models

The following remain API projections rather than persistence tables:

- Homepage/DSP health
- My DSP and recent activity
- VM inventory and VM detail
- Devspace inventory and devspace detail
- Kedro job inventory and job detail
- Troubleshooting/support catalog
- Onboarding and training
- User-scoped Hive access and morning ingestion
- Admin Hive access and ingestion across teams
- Team-scoped YARN queue status
- Admin control-plane attention and workflow summaries

FastAPI application services assemble these projections from repositories and integration clients. Existing camelCase API contracts can remain stable while static preview services are replaced incrementally.

## Physical implementation sequence

1. Source systems, identity providers, principals, two-role authorization, authentication-state tables, local accounts, LDAP groups, memberships.
2. Teams, access subjects, DSP tenants, resource access, service entitlements.
3. Resource registry, VM inventory, network zones, interfaces, IP assignments.
4. Nexus repositories, image versions, devspaces, placements, service bindings.
5. Git repositories, Kedro projects, pipelines, job runs, nodes, artifacts.
6. Platform health, incidents, planned changes, and impact mappings.
7. Hive metadata, access entitlements, morning ingestion, and YARN queues.
8. Governed allocation workflows and administration audit events.
9. Support, onboarding, operational events, and notifications.

SQLAlchemy persistence models should live separately from Pydantic API schemas, and every physical change must be delivered through an Alembic migration.
