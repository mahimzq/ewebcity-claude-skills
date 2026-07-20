# Security Review Checklist

Review every change against the items relevant to it before delivery. The goal is not to recite the list but to actively look for each class of flaw in the code you wrote or touched.

## Access control
- Authentication bypass — can any changed route or flow be reached unauthenticated?
- Broken authorisation / missing permission checks — is the *right* user allowed, not just *a* user?
- IDOR / insecure direct object access — are object IDs scoped to the current user or tenant?
- Mass assignment — are only whitelisted fields writable from request input?

## Injection and input
- SQL injection and NoSQL injection — parameterised queries / ORM only; no string-built queries.
- XSS — output encoding, no unsanitised HTML rendering, correct framework escaping.
- CSRF — state-changing requests protected per framework convention.
- SSRF — no user-controlled URLs fetched server-side without allow-listing.
- Weak input validation — validate type, length, format, and range on the server, regardless of client validation.
- Unsafe redirects — no user-controlled redirect targets without validation.

## Files and uploads
- Unsafe file uploads — validate type and size, store outside webroot or in object storage, never trust the client filename.

## Secrets and data
- Sensitive data exposure — no secrets, tokens, or PII in logs, responses, or client bundles.
- Secret leakage — no hard-coded credentials anywhere; environment variables only, with the example env file updated.
- Insecure token storage — follow the project's existing token strategy; prefer httpOnly cookies over localStorage for session tokens where the architecture allows.
- Internal error details — return generic error messages to end users; log the detail server-side.

## Integration surface
- Webhook verification — verify signatures on all inbound webhooks.
- CORS misconfiguration — no wildcard origins with credentials; match the project's existing policy.
- Rate-limit gaps — apply rate limiting to auth endpoints, expensive operations, and anything abusable.

## Reporting
Summarise in the final delivery: which protections were added or verified, and any remaining concerns the user should know about. Do not silently pass over a risk you noticed but did not fix.
