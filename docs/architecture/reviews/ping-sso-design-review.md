# Review — Ping SSO and local-user authentication plan

| Field | Value |
| --- | --- |
| Reviewing | [../ping-sso-integration-plan.md](../ping-sso-integration-plan.md) v0.7 |
| Previous pass | Against v0.2. All 13 original findings are now resolved or superseded |
| Disposition | Design approved. Four new findings, two of them documentation defects |
| Status | S-01…S-13 closed · N-01…N-04 open · 2 implementation divergences |
| Last updated | 2026-09-07 |

## Verdict

v0.7 closes every finding from the v0.2 review, and the implementation has largely caught up with
it. The browser binding, the session and CSRF cookie contract, the unconditional `InResponseTo`
check, the two-tier authorization split, the pinned SAML library, rate limiting and the attribute
contract are all specified, and most are shipped.

What remains is smaller and different in kind. One documentation defect contradicts the design in a
way that changes a security property. One deliberate reversal of earlier advice deserves recording
with its consequence rather than re-arguing. Two implementation details have not caught up with the
plan.

## Original findings — all closed

| ID | Closed by |
| --- | --- |
| S-01 SAML vs OIDC | Decision 13. OIDC unavailable; `python3-saml` pinned; Debian slim fixed in §12 |
| S-02 Exchange not bound to the browser | Decision 14; `__Host-dsp_login` nonce in §7 at both ends; fragment mandated; §13, §14, §15, §17 |
| S-03 Refresh transport unspecified | Decision 15; §7, §9. `__Host-dsp_session` plus `__Host-dsp_csrf`, matching header and exact `Origin` |
| S-04 Authorization scope | Decision 17; §10.1–10.3. Tier 1 needs no new tables |
| S-05 `InResponseTo` conditional | Decision 18; §8.1 — "a check that cannot be performed is a rejection, not an exemption" |
| S-06 Shared state availability | Superseded — see below |
| S-07 Dev-only in-memory store | §5.1. One implementation, PostgreSQL; the protocol retained as the extraction seam |
| S-08 SAML library unnamed | Decision 13; §12, with a named owner for its advisory feed |
| S-09 Rate limiting and entropy | §7 preamble; §9 sets ≥256 bits for both code and nonce; §11 adds the limits |
| S-10 Hive and YARN in scope | §10.3 marks both later-phase |
| S-11 Clock skew | §11 — 60 seconds |
| S-12 Durable identifier | §5.2, §8.2 — `objectGUID` into `principal_identity.external_object_id` |
| S-13 Attribute contract | §8.2 in full, with the three written confirmations and the sync fallback |

S-12 and S-13 are closed **as design**. Both still depend on a Ping IAM change that has not landed;
they are tracked in the README's open-decisions table, not here.

## S-06 — a deliberate reversal, recorded

The v0.2 review argued for stateless access-token validation so a state-store outage would stop new
logins without signing out users who already held a token. **Decision 16 chooses the opposite**, and
does so explicitly: every protected request re-reads the principal, `authorization_version` and
refresh-session record from PostgreSQL, so logout, disablement and role changes take effect
immediately. Redis is gone entirely (S-14); PostgreSQL is the only state store.

That is a defensible trade and arguably the right one for a bank, where immediate revocation
matters more than graceful degradation of a read-only portal. It is recorded here so the reasoning
survives, not reopened. Its consequence is N-02.

## New findings against v0.7

| ID | Severity | Finding | Fix |
| --- | --- | --- | --- |
| N-01 | High | **§6 contradicts decision 16, §9 and §15.** The `auth.refresh_session` row in the §6 table says it is "read only on refresh and logout, never to validate an access JWT". Decision 16, §9 and the §15 test list all say the refresh-session record is verified on every protected request — and `app/auth/dependencies.py` does exactly that. §6 is a leftover from the pre-v0.7 stateless design, and an implementer following it would drop the check that makes revocation immediate | Correct the §6 row to match. The security property depends on which sentence is believed |
| N-02 | Medium | **PostgreSQL is now on the hot path for every protected request.** §13 states the consequence honestly — the portal fails closed and readiness reports unavailable. But the portal's own product requirement is that it degrades rather than blanks during an upstream incident, and this makes a database blip a total outage of a status page. It is also a database round trip per request at 300 users | Accept knowingly, or soften without losing the property: cache the principal and `authorization_version` lookup for a few seconds, so revocation is effective within seconds rather than instantly and a brief outage does not blank the portal. Whichever is chosen, state it against the go-live "degrades, never blanks" gate so the two documents do not disagree |
| N-03 | Low | **`SameSite=Strict` on `__Host-dsp_session` costs a visible login flash on inbound links.** Strict cookies are withheld on a cross-site navigation, so a portal link pasted into Teams or an email lands the user unauthenticated until the SPA's first `/auth/refresh` — which is same-site and does carry the cookie. It works; it just looks broken for a moment, on a portal whose links will be pasted into support channels constantly | Accept and note it in the UI (restore silently, do not flash the login page), or use `SameSite=Lax` on the session cookie — still safe given the CSRF token, matching header and exact `Origin` check |
| N-04 | Low | **`__Host-dsp_session` uses `Path=/`** (§7, §9), so it is sent on every `/api/*` request although only `/auth/refresh` and `/auth/logout` read it. The access JWT already carries `sid`, so nothing else needs it | `Path=/auth`. Narrows exposure at no functional cost |

## Implementation divergence

The design is now ahead of the code in two places. Both are code findings, not plan defects.

| ID | Severity | State |
| --- | --- | --- |
| I-04 | Medium | **Open.** `enterprise_auth/tokens.py:79` rejects any token whose `kid` differs from the current key id, so a rotation invalidates every live token at once. §9 requires a documented overlap procedure, which this makes impossible. Accept a map of key id to verification key |
| I-08 | Medium | **Open.** `app/auth/repository.py:237` resolves an empty group list silently to `READ_ONLY`. Given S-13 — Ping sends no groups today — every user will land `READ_ONLY` with no signal. An *absent* groups attribute is a contract failure and should be audited; an *empty* one is a legitimate answer |
| I-01 | Closed | `/auth/local/password-action` is implemented; the bootstrap account no longer claims a change it cannot enforce |
| I-03 | Closed | Decision 22 — providers coexist and there is no enable/disable flag. Incomplete Ping configuration degrades only Ping |
| I-05 | Closed | `enterprise_auth/saml.py` parses `AuthnInstant` from the validated assertion |
| I-06 | Closed | The router now audits the rejected exchange binding |
| I-07 | Closed | `enterprise_auth/saml.py:74` asserts `InResponseTo` explicitly rather than relying on library configuration. This was the login-CSRF hole |
| I-10 | Closed | The CSRF cookie is `__Host-dsp_csrf` |

## What must survive review

Each of these will come under pressure once dates are real, and each is cheap to concede in a
meeting and expensive to recover afterwards.

- **The backend is the service provider.** React never receives, parses or holds an assertion, and
  enterprise credentials reach only Ping.
- **No tokens in web storage.** Expect pushback the first time someone notices the reload
  behaviour; answer it with the session cookie, not by relaxing this.
- **UI hiding is not a security control.** A direct API call must still return 403.
- **Fail closed, everywhere.** No "degrade to anonymous" path for any dependency.
- **`InResponseTo` is unconditional.** The word "applicable" must not return to §8.1.
- **Local accounts stay governed.** No self-registration, Argon2id only, final-admin protection,
  and every mutation audited.
- **Single origin behind ingress.** What makes the `__Host-` prefix available.
- **Extraction deferred until a second consumer exists.** The generic package must not import the
  application.
