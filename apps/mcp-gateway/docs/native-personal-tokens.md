# Unified Plane personal tokens

Use **Profile settings → Personal access tokens** for API clients and MCP clients.
Create and delete tokens through the native Plane page. The secret appears once;
configure it in the client's authorization connection, never tool arguments.

- Native API: `X-Api-Key: <personal token>`.
- MCP HTTP: `Authorization: Bearer <personal token>`.
- Singularity extension API: either header is accepted for native tokens.
- OAuth remains supported with explicit consent, S256 PKCE, audience validation,
  refresh rotation, revocation and a distinct short-lived downstream credential.
- Native tokens have all supported MCP operation scopes; current Plane permissions
  still decide which resources and operations are available. Only the existing
  five tools are exposed. Native expiration choices, including no expiry, are
  preserved; MCP does not impose a separate shorter personal-token lifetime.

The native `APIToken` row is the source of truth. Both native authentication
middlewares and the delegation adapter use the same validity check. Deleting,
expiring or disabling a source invalidates already exchanged downstream tokens
on their next request. Account deactivation also invalidates native tokens,
OAuth grants and sessions, without resurrection after reactivation.

Newly created native secrets are digest-only in storage. Existing native token
values remain usable without copying or replacing them. Historical `sgp_` tokens
retain their original scopes, expiry and connection revocation; the dedicated
issuer no longer exists and its URL redirects to native settings. They are not
silently promoted to unrestricted native tokens.

Migration 0131 is additive. A stable nullable native-token UUID on `Delegation`
keeps discussion receipts and audit after source deletion. Concurrent exchanges
use the unique source UUID, so retries preserve connection identity and idempotency.

## Validation

Automated contracts cover new and existing tokens, actor identity, source expiry,
delete/disable/deactivation, downstream revocation, digest-as-token rejection,
secret readback, membership removal, cross-user deletion, shared decision replay,
cross-connection rejection, historical scoped tokens and OAuth regressions.

The trusted local Chrome flow logs in through Plane's native form, follows the
retired entry to native settings, creates a token in the UI, closes and refreshes,
uses that same token on native API, extension API and real MCP, then deletes it
in the UI and checks rejection from both API and MCP. No secret is saved in the
screenshots or evidence. Real OAuth PKCE/read/revoke and both GitLab SSO entry
paths are also checked. Peer machines and external clients remain separate
acceptance conditions; localhost success does not prove their connectivity.

## Deployment and rollback

Apply the additive migration before replacing API and worker processes. Keep
canonical HTTPS origins and existing OAuth client registration unchanged.
Back up database and configuration first. Candidate acceptance uses read-only
source mounts and restores saved routes before building the committed image.

To withdraw MCP, disable its entry and revoke its OAuth grants; retain the native
personal-token authentication adapter. A pre-change image cannot validate newly
hashed native tokens. Do not convert digests back to plaintext or restore an old
database over new work items to work around that incompatibility. Keep 0131,
receipts and audit when rolling back application features.
