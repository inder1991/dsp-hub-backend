# Review — DSP Portal data model

| Field | Value |
| --- | --- |
| Reviewing | [data-model.md](data-model.md) · [data-model.dbml](data-model.dbml) |
| Status | Open — verify each against the current DBML before acting |
| Last updated | 2026-09-07 |

## Verdict

Better than most v1 designs. It makes three calls teams usually get wrong and then spend a year
unpicking: health kept separate from lifecycle state, the person kept separate from their directory
identity, and metrics kept out of the relational store. The storage-responsibility section is the
part to keep verbatim.

Two weaknesses. **Most important invariants are prose beneath the tables rather than constraints
inside them**, and a database enforces only what is written in it. And it is a target-state model
presented as a v1 schema — the answer is not to cut it down but to build ten tables from it now
(see [phase-one.md](phase-one.md)) and leave the rest exactly where it is.

## Findings

| ID | Severity | Finding | Fix |
| --- | --- | --- | --- |
| F-01 | Blocker | `source_system` referenced by many tables | Verified present in the DBML; confirm it stays as the anchor for every `UNIQUE (source_system_id, external_id)` |
| F-02 | Blocker | Nothing joins a Prometheus series to a `resource` | Add `resource_metric_identity` — DDL in [phase-one.md](phase-one.md) §4 |
| F-03 | Blocker | `job_run` has no natural key. Hook delivery is at-least-once, so every retry creates a duplicate | `UNIQUE (source_system_id, external_run_id)` on `job_run`; `UNIQUE (job_run_id, node_name, sequence_number)` on `job_node_run`. The pattern is already applied correctly to `resource` and `operational_event` |
| F-04 | High | Four "exactly one of these columns" rules exist only as prose: `access_subject`, `health_assessment`, `incident_impact`, `directory_group_membership` | `CHECK (num_nonnulls(a, b, c) = 1)` on each |
| F-05 | High | Four "only one active" rules likewise: `devspace_placement`, `ip_assignment`, `principal_identity.is_primary`, overlapping `team_membership` | Partial unique indexes, e.g. `UNIQUE (devspace_id) WHERE removed_at IS NULL`. For intervals, a `tstzrange` exclusion constraint |
| F-06 | High | Five vocabularies for one concept — `valid_from/valid_to`, `observed_at/valid_until`, `first_seen_at/last_seen_at/retired_at`, `placed_at/removed_at`, `detected_at/cleared_at` | Standardise on `valid_from`/`valid_to` (null = still true), with `observed_at` meaning only "when a collector last confirmed it". Every future join pays for this otherwise |
| F-07 | High | `job_run.vm_id_snapshot uuid` has no foreign key. A VM's surrogate id never changes, so there is nothing to snapshot | Make it `vm_id uuid REFERENCES vm`. Keep `image_digest_snapshot` and `git_commit_sha_snapshot` — those genuinely change under the run |
| F-08 | Medium | `operational_event` will be the highest-volume table and is not partitioned | Declarative partitioning by `occurred_at`, monthly, from the first migration |
| F-09 | Medium | `health_assessment` has no efficient path for "current health of 200 VMs" | Phase 1: do not build it (D5). Later: index `(resource_id, observed_at DESC)` plus a current-state projection |
| F-10 | Medium | Access subjects are shown as granted access to a tenant, but `dsp_tenant` is not a `resource`, so `resource_access.resource_id` cannot express it | Give tenants a `resource` row, or add `tenant_access`. The diagram promises what the tables cannot store |
| F-11 | Medium | `change_impact` can point only at a `resource`, while `incident_impact` and `health_assessment` can also point at a `platform_service`. "The Trino upgrade affects Trino" is unrecordable | Make all three polymorphic references identical in shape, with the same CHECK as F-04 |
| F-12 | Medium | "CPU uses cores or millicores" — that *or* is a unit bug with a date on it. `vm.cpu_capacity_cores` and `devspace.cpu_limit_millicores` already disagree and are compared on the same page | Millicores everywhere. Rename to `cpu_capacity_millicores` |
| F-13 | Low | `resource_access` has no uniqueness — the same subject can be granted OWNER repeatedly | `UNIQUE (resource_id, access_subject_id, access_role) WHERE expires_at IS NULL` |
| F-14 | Low | `principal_identity.enterprise_user_id` is on the wrong table. One person has one staff number but may hold several directory identities | Move to `principal` |
| F-15 | Low | `image_version.python_version` hardcodes one runtime dimension. The first R, Spark or CUDA image needs a schema change | An `image_version_component` table, or JSONB. Fine through Phase 1 — just know the trigger |
| F-16 | Low | Nothing enforces that `resource_type = 'VM'` has a matching `vm` row, and `resource.metadata jsonb` alongside typed subtype tables invites the same fact in two places | A trigger, or accept and document that the subtype row is the writer's responsibility. Keep `metadata` strictly for source fields with no column |

## Endorsed — do not let review churn undo these

| Decision | Why it matters |
| --- | --- |
| Health separate from lifecycle | Running-but-thrashing and stopped-but-fine are different facts. Merging them is the mistake nearly every internal portal makes |
| Person separate from directory identity | `principal` / `principal_identity`, and LDAP groups separate from business teams. Both survive a directory migration, a rename and a second provider |
| Metrics stay in Prometheus | The storage-responsibility table is correct in every row, and is the thing most likely to be argued away by someone who wants "all the data in one place" |
| Peaks persisted on the run | `cpu_peak_millicores` and `memory_peak_bytes` look like a violation of the rule above and are not. They must outlive retention |
| Digest captured with the tag | Tags get re-pointed; digests are what a failing job actually ran |
| Units and time | Bytes for memory, `TIMESTAMPTZ` in UTC, percentages derived, durations computed. Fix F-12 and this is complete |
