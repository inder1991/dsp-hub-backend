# DSP Portal — go-live plan

| Field | Value |
| --- | --- |
| Status | Draft for review |
| Shape | Three release trains, one parallel content track, one hardening sprint |
| Last updated | 2026-09-07 |

## 1. Where the build is

Authentication, the application shell and the API contracts are production-shaped and covered by
tests. Nothing behind them is real.

| Area | State | Evidence |
| --- | --- | --- |
| Ping SAML + local auth | Real | PostgreSQL, Alembic migrations, backend tests green |
| App shell, routing, login | Real | Auth provider, frontend tests green |
| API contracts | Real | camelCase, OpenAPI-generated, every route authenticated |
| Data access, ingestion, YARN, Hive | Static | `data_platform.py` |
| Devspaces, VMs, Kedro jobs | Static | `devspaces.py`, `observability.py` |
| Health, support, onboarding | Static | `dashboard.py`, `support.py`, `onboarding.py` |
| Prometheus / Trino / Hive / CDP clients | None | No HTTP or DB client in any service module |
| Kedro run collection | None | Hooks package not written, not in the base image |

Every remaining feature is therefore the same shape of work: swap one static service for a real
adapter behind a contract that already exists and is already consumed by a working screen.

## 2. The R1 split

The data-access page answers two different kinds of question.

- *"Did the morning batch land?"* — same answer for everyone, one call to the ingestion scheduler.
  **Two hops.**
- *"Which tables can I see?"* — different per person, needs the user's LDAP groups, which the
  assertion does not carry. Ping IAM change, then entitlement tables, then a directory sync.
  **Five hops, and the first is another team's queue.**

Built as one release, the fast half waits on the slow half. Split into **R1a** and **R1b** and the
portal goes live while the entitlement chain is still in flight.

On pure engineering grounds compute would come first — Prometheus already holds the data and needs
no authorization model. Putting data access first is a legitimate product call; take the split so
it costs weeks rather than months.

## 3. Timeline

| Train | W1 | W2 | W3 | W4 | W5 | W6 | W7 | W8 | W9 | W10 | W11 | W12 | W13 | W14 | W15 | W16 | W17 | W18 | W19 | W20 | W21 | W22 |
| --- |:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| **R1a** platform truth | # | # | # | # | # | # | # | # | | | | | | | | | | | | | | |
| **R1b** entitled access | | | | | | | # | # | # | # | # | # | # | # | | | | | | | | |
| **R2** compute | | | | | | | | | # | # | # | # | # | # | # | # | | | | | | |
| **R3** support content | # | # | # | # | # | # | # | # | # | # | # | # | # | # | # | # | # | # | | | | |
| **SEC** hardening | | | | | | | | | | | | # | # | # | # | | | | | | | |
| **R4** remaining | | | | | | | | | | | | | | | # | # | # | # | # | # | # | # |

**W8 — internal pilot.** **W16 — go-live to all 300, after the security gate.**

No phase precedes the first line of feature work. External requests (section 6) are in flight from
day one and are waited on, not worked on.

## 4. The trains

### R1a — Platform truth · W1–W8 · first user exposure

Every fact that is the same for all users. Nothing here waits on Ping IAM.

- Morning ingestion status; source freshness per upstream feed
- CDP, Hive, Trino and YARN health, replacing the hardcoded system cards
- The DSP health indicator driven by real checks
- The Prometheus adapter with cache and recording-rule contract — reused by R2
- Per-section `asOf` and `source`

Two security items ride here rather than waiting for the hardening sprint, because a live
vulnerability and a secret on disk are not hardening:

- **Assert `InResponseTo` is present** (S-05). Roughly ten lines. Without it an unsolicited
  assertion is accepted, letting an attacker sign a victim in as the attacker.
- **Move signing keys off local disk** into CyberArk and retire `.secrets/`.

*Exit gate — internal pilot only.* No screen shows a number from a literal. This gate does **not**
claim security sign-off: the pilot runs under written risk acceptance with a named owner and an
expiry at W16.

### R1b — Entitled data access · W7–W14 · gated on Ping IAM

- LDAP groups consumed from the assertion (requires the S-13 attribute contract fix)
- Entitlement tables and directory sync, or a narrower mapping
- Tables I can access; my team's YARN queues
- Kedro run history (requires the hooks package in the base image)

*Exit gate.* Two users in different teams see different table lists, and a direct API call for
someone else's table returns 403 — backend-enforced, not hidden in the UI.

### R2 — Compute · W9–W16 · rollout to all users

Technically the easiest train; the adapter is built in R1a. Its one hard dependency is other
people's container labels.

- VM inventory and detail from node_exporter
- Devspace inventory and detail from cAdvisor — requires `dsp.owner` and `dsp.tenant` OCI labels
- The reconciler and the resource-to-metric identity join
- My DSP becomes real; health computed from a versioned rule set

### R3 — Support and enablement · W1–W18 · parallel from week one

This parallelises because it is **content work, not integration work**. No shared code path, no
Ping change, no Prometheus, no schema. Different skill set, day one, full speed.

- Troubleshooting guides for the top ten failures users actually hit
- FAQ seeded from the existing support backlog; training videos; bootcamp schedule
- Support routing — roster, Teams deep links, Remedy queue mapping
- Onboarding journey and the per-role access matrix

*Exit gate.* Every guide has a named owner and a review date. Content quality is the risk here, not
delivery — a stale guide is worse than no guide.

### SEC — Security and hardening sprint · W12–W15 · gates the full rollout

Consolidated rather than smeared across the trains. Deferring it this far is defensible only if the
exposure before it is internal and volunteer, and the sprint is genuinely protected rather than the
first thing cut when R2 runs late.

- JWT key rotation — verification currently rejects any token not signed by the current key id, so
  a rotation signs every user out
- Rate limiting, with thresholds from observed pilot traffic — the one item genuinely better late
- Audit completeness — a failed exchange binding raises no event today
- Authentication time from the assertion rather than processing time
- Empty group lists audited rather than silently resolving everyone to read-only
- SIEM integration, dashboards, alerts; runbooks; on-call rota staffed
- Penetration test against a system carrying real data and real users
- Dead code removed

### R4 — Remaining · W15–W22 · on a live product

Global search; incidents from Remedy and the change calendar; Nexus and GitHub; failure diagnosis.
Prioritise from what pilot users asked for, not from this list.

## 5. Two gates

### W8 — internal pilot

| Criterion | Evidence |
| --- | --- |
| Users sign in with enterprise identity | Ping SAML working; local accounts restricted to break-glass and named |
| Every API authenticates and authorises server-side | No token → 401; wrong role → 403 |
| No screen shows invented data | Every figure traces to a live source or is labelled with `asOf` and `source` |
| An upstream outage degrades, never blanks | Prometheus and the scheduler stopped in a drill; the portal still renders |
| Unsolicited assertions rejected | Carried in R1a, not deferred — an exploit, not hardening |
| No private keys in the working tree | Keys from CyberArk; `.secrets/` retired |
| Risk acceptance signed | Open findings listed, owner named, expiry at W16 |
| A way back | Rollback rehearsed; users can still reach underlying systems directly |

### W16 — rollout to all 300

Everything above, plus the hardening sprint's output. These are people who did not volunteer and
cannot assess the risk themselves, which is what makes this the gate that does not move.

| Criterion | Evidence |
| --- | --- |
| Security sign-off | Penetration test passed against real data and users; findings closed or accepted in writing |
| Key rotation works | A signing key rotated without signing anyone out |
| Auth endpoints rate limited | Login, ACS and exchange shed load under a burst |
| An incident can be investigated | Audit events reach the SIEM, including a rejected exchange binding |
| Someone answers when it breaks | On-call rota staffed; runbooks rehearsed |
| Users know it exists | R3 content live; top ten guides published with owners |
| The pilot risk acceptance is closed | Every finding fixed or formally re-accepted, not silently extended |

## 6. Raise these before anything starts

All external, all gating, all indifferent to build order.

| # | Item | Owner |
| --- | --- | --- |
| 1 | Ping attribute contract — no groups, no immutable identifier today. Blocks R1b entirely | Ping IAM |
| 2 | OCI labels on devspace containers. Without them R2 has no per-user view | Devspace launcher |
| 3 | Kedro hooks in the base image | Platform + Nexus |
| 4 | Prometheus read credential and retention figure | Monitoring |
| 5 | Ingestion scheduler API access — the single dependency of R1a | Data engineering |
| 6 | Production PostgreSQL — before users, not before development | DBA |
| 7 | Penetration test slot — six to eight weeks of lead, booked W1, run W7 | Security |

## 7. Rollout

**W8** pilot: the platform team plus two volunteer teams, ~20 people who know they are on a system
with open findings. **W12** expand to five representative teams, ~80 users, chosen to differ from
each other rather than to be easy — the last step under risk acceptance. **W16** all 300, after the
hardening sprint clears.

The failure mode to watch is not the plan but what happens to it under pressure. A hardening sprint
scheduled after the feature work is the first thing raided when R2 slips, and a risk acceptance
signed at W8 quietly gets extended twice. **Make W16 depend on the sprint finishing, rather than the
sprint depend on W16.**

One thing to resist: making the portal mandatory. It earns traffic by being the fastest way to
answer a question. A front door that is enforced rather than chosen stops giving you the signal
that tells you whether it is any good.
