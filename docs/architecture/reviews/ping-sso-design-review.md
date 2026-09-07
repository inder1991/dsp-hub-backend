# Review — Ping SSO integration plan

| Field | Value |
| --- | --- |
| Reviewing | [../ping-sso-integration-plan.md](../ping-sso-integration-plan.md) |
| Disposition | Approve the security architecture; close S-02 to S-05 and S-13 before Stage 2 |
| Status | S-01 closed. 12 open |
| Last updated | 2026-09-07 |

## Verdict

A stronger document than most first SSO designs. The author understands the threat model: the
backend is the service provider, React never touches an assertion, the exchange code is opaque,
single-use and hashed at rest, tokens stay out of web storage, and everything fails closed.

What remains is silence rather than error. Three of the four high findings are places where the
design does not say something — and silence gets resolved under delivery pressure, badly, if it is
not resolved on paper first.

## Findings

| ID | Severity | Finding | Fix |
| --- | --- | --- | --- |
| S-01 | **Closed** | SAML vs OIDC was filed as a review question while the plan assumed SAML | **Answered: OIDC unavailable, SAML 2.0 confirmed.** Library pinned to `python3-saml`, base image Debian slim, SP private key needed only if the profile mandates it |
| S-02 | High | Nothing binds `/auth/exchange` to the browser that began the login. Whoever holds the `token_id` gets the session, and it travels through a URL | `__Host-` nonce cookie at `/auth/login`, hash carried into the code record, required at exchange. Mandate the fragment, not the query string. PKCE would have supplied this; SAML does not |
| S-03 | High | The refresh session transport is never specified. The access token is described carefully; the longer-lived, more valuable credential is not | Name it: `__Host-` prefixed, `HttpOnly`, `Secure`, `SameSite=Strict`, `Path=/auth`, with CSRF protection on refresh and logout |
| S-04 | High | Stage 3 is one bullet and is the largest workstream in the plan. It needs eight tables and a directory sync that Phase 1 defers | Split authorization into Tier 1 (admin group claim plus owner-scoped resources, no new tables) and Tier 2 (the team and entitlement model). `require_resource_access` keeps its signature |
| S-05 | High | Validation checks are qualified with "all *applicable*". An IdP-initiated assertion has no `InResponseTo`, so under a literal reading the ACS accepts an unsolicited assertion — standard SAML login CSRF | Reject absent or unmatched `InResponseTo` unconditionally. Disable IdP-initiated SSO at the Ping SP registration. Add both to the acceptance gates |
| S-13 | High | The Ping attribute contract fulfils all seven assertion attributes from `subject`. As drafted the assertion delivers the same string seven times — no groups, no email, no display name, no immutable identifier | Attach an LDAP datastore to the adapter mapping on the SP connection. Request `objectGUID`, `memberOf` filtered and multi-valued, `mail`, `givenName`, `sn` |
| S-12 | High | Promoted from Low. S-13 shows there is currently no durable identifier on offer — `subject` is a single mutable string | Anchor on `objectGUID` into `principal_identity.external_object_id`. Agree the encoding in writing and freeze it |
| S-06 | Medium | Redis is a hard fail-closed dependency with no stated topology, making it a single point of failure for a portal whose job is telling people whether things are up | Require an HA topology, and state that JWT validation is stateless with no Redis read on the request path |
| S-07 | Medium | A dev-only in-memory state store is a second implementation of a security-critical store that production forbids | Delete it. Run Redis in the dev compose file. Keep the protocol interface as the extraction seam |
| S-08 | Medium | The SAML library was referred to only as "the chosen implementation" | Now urgent since SAML is confirmed. `python3-saml`, pinned, named, with an owner for its advisory feed |
| S-09 | Medium | No rate limiting on `/auth/login`, `/auth/saml/acs` or `/auth/exchange`. Signed-XML validation is an expensive denial-of-service target | Per-IP and per-session limits on all three. Mandate at least 256 bits of entropy for `token_id` |
| S-10 | Medium | The policy table covers Hive metadata and YARN queues; neither system is in portal Phase 1 | Mark them later-phase so they stop inflating the Stage 3 estimate |
| S-11 | Low | Clock skew of 120 seconds is generous given the plan already mandates synchronised time | 60 seconds |

## What must survive review

Each of these will come under pressure once dates are real, and each is cheap to concede in a
meeting and expensive to recover afterwards.

- **The backend is the service provider.** React never receives, parses or holds an assertion.
- **No tokens in web storage.** Expect pushback the first time someone notices the reload
  behaviour; answer it with the session cookie in S-03, not by relaxing this.
- **UI hiding is not a security control.** A direct API call must still return 403.
- **Fail closed, everywhere.** No "degrade to anonymous" path for any dependency.
- **Remove the dummy user; disable preview data.** Both as acceptance gates rather than intentions.
- **Single origin behind ingress.** Deletes a category of CORS and cookie problems, and is what
  makes the `__Host-` prefix available.
- **Extraction deferred until a second consumer exists.** Keep the rule that the generic package
  must not import the application.
