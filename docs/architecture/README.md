# DSP Portal — architecture

Canonical home for DSP Portal architecture. The portal is two repositories
([backend](https://github.com/inder1991/dsp-hub-backend),
[frontend](https://github.com/inder1991/dsp-hub-frontend)) and one architecture; these documents
cover both. The frontend repository carries a pointer here rather than a copy.

## Reading order

| # | Document | For | Status |
| --- | --- | --- | --- |
| 1 | [platform.md](platform.md) | Anyone building a module. Start here | Draft for review |
| 2 | [phase-one.md](phase-one.md) | How VM, devspace and Kedro data reaches the screen | Draft for review |
| 3 | [data-model.md](data-model.md) · [data-model.dbml](data-model.dbml) | The logical model | Approved v1 |
| 4 | [data-model-review.md](data-model-review.md) | 16 findings against the model above | Open |
| 5 | [ping-sso-integration-plan.md](ping-sso-integration-plan.md) | Authentication and local-user design | v0.7, implementation in progress |
| 6 | [reviews/ping-sso-design-review.md](reviews/ping-sso-design-review.md) | Review of the plan above | S-01…S-13 closed · N-01…N-04 open |
| 7 | [go-live-plan.md](go-live-plan.md) | Release sequencing and gates | Draft for review |

If you are joining a module team and reading one thing, read `platform.md`.

## What lives where

| Concern | Location |
| --- | --- |
| Architecture documents | This directory, in the backend repository |
| Backend platform kernel | `app/platform/` (planned) |
| Backend modules | `app/modules/<name>/` (planned) |
| Authentication | `app/auth/` and `enterprise_auth/` |
| Database schema | `migrations/`, described in `data-model.dbml` |
| Frontend platform | `src/platform/` in the frontend repository (planned) |
| Frontend modules | `src/modules/<name>/` in the frontend repository (planned) |

## Conventions

- Diagrams are Mermaid so they render in GitHub and diff as text. Do not commit exported images.
- Superseded versions are kept alongside with a version suffix, as
  `ping-sso-integration-plan.v0.1.md`, rather than deleted. The history is in git; the file is for
  reviewers who cite section numbers from the version they read.
- Every document carries a status and a date in its header table. A document with neither is not
  something anyone should act on.
- Findings are numbered and stable (`S-01`, `F-03`, `I-07`). Cite the identifier, not the paragraph.

## Open decisions

Tracked in the documents that raise them, listed here so they are findable.

| Decision | Where | Owner |
| --- | --- | --- |
| Ping attribute contract — no groups, no immutable identifier today | `ping-sso-integration-plan.md` §8.2 | Ping IAM |
| IdP-initiated SSO disabled on the SP registration | `ping-sso-integration-plan.md` §8.1 | Ping IAM |
| Whether an SP private key is needed at all | `ping-sso-integration-plan.md` §11 | Ping IAM |
| OCI labels on devspace containers | `phase-one.md` | Devspace launcher team |
| Prometheus retention window | `phase-one.md` | Monitoring |
| Kedro hooks package in the base image | `phase-one.md` | Platform + Nexus |
