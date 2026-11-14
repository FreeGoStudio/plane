# Identity and authorization boundary

Plane owns users, account status, project visibility and work-item permissions.
The gateway is a separate TypeScript official MCP SDK process with a private SQLite vault;
it has no Plane database connection. Work-item MCP has no GitLab dependency; the
separate company provisioner and repository adapters are described below.

Plane is also the OAuth issuer. Django OAuth Toolkit manages the MCP protocol
backend and explicit public Application registration, separately from confidential
OIDC clients. A pre-registered public Codex client receives an
opaque token for the gateway resource after S256 consent. Plane stores only
SHA-256 digests of access, refresh and authorization codes; refresh rotates.
OAuth access tokens have a 10-minute lifetime; refresh authorization is capped
at 30 days from the original grant. Personal credentials now use Plane's native
`APIToken` lifecycle and expiry settings, shared by native API and MCP. New tokens
created in the native settings page are stored as SHA-256 digests and displayed
once. Existing plaintext native tokens and already issued `sgp_` credentials remain
valid; legacy scoped grants retain their original limits and revocation page.
The old dedicated creation URL redirects to `/settings/profile/api-tokens/`.
Downstream expiry cannot exceed the originating credential. Native delegation
rows retain a stable source UUID after token deletion so receipts and audit remain;
every child request checks the source's current activity, expiry and user status.
Native tokens receive all supported tool scopes and existing Plane RBAC, without
adding new MCP tools. OAuth retains explicitly consented scopes.

The gateway validates the token by authenticated inspection at Plane on every
MCP HTTP request and again on every tool invocation. The confidential private
`/auth/singularity/exchange/` endpoint accepts that token **only for delegation
exchange**, never as a work-item resource credential. It issues a distinct,
five-minute `plane` audience token with the same grant and scopes. Plane resource
endpoints reject gateway-audience tokens. Gateway-audience verification rejects
Plane tokens. The client never receives the downstream pair.

The exchange secret identifies the gateway, not a user: by itself it cannot
read or write any work item. The TypeScript runtime exchanges a fresh downstream token for each business call
and does not persist it. Pending discussion material uses the separate Fernet
vault key; old encrypted token-cache rows remain only for Python rollback. The issuer/resource are deployment configuration, not model
parameters. A disabled account or revoked grant invalidates both audiences.

Work-item access is checked against current membership on every call. Public
projects retain Plane's listing semantics; work-item access requires the native
membership rules. Creator-conditioned update permissions reuse the native
permission decorator, not a role table in the gateway. No capability hint
authorizes a subsequent call.

Creation uses a database transaction containing the receipt and work item.
Duplicate decision IDs serialize and return the existing receipt only after
checking current visibility. Updates lock the work item before checking its
version; native app PATCH and public API PATCH take the same lock before reading.
Only explicit title/description fields change on update. Default assignment is
disabled for delegated creation. Activities are dispatched after commit.

Threats covered: forged user IDs, confused audiences, PKCE/code replay, revoked
membership, cross-connection decision IDs, duplicate writes after response loss,
HTML injection, model-provided URLs and secret-bearing logs. The gateway uses
fixed paths, registered scopes, bounded content and no arbitrary HTTP tool.

The authorization pages use Plane sessions and CSRF. They are intentionally
separate from the shared model account. HTTPS trust must be verified; local
certificate failure is not bypassed. Tokens and pending summaries must never be
included in diagnostic output or source control.

## Company identity and repositories

Django OAuth Toolkit supplies separate OIDC endpoints with stable Plane UUID
subjects and RS256 signatures. OIDC identity tokens cannot authorize MCP. Company
GitLab is a registered confidential OIDC client; provisioning must finish before
issuing its code/token. Only the dedicated provisioning process mounts the GitLab
management credential. Its durable identity key reconciles response loss; email
collisions require ownership proof and never bind automatically. Previously owned
accounts remain unmanaged; only platform-created company accounts are blocked
automatically after Plane deactivation.

Repository instances are registered by platform administrators. Project admins
attach multiple stable repository IDs; each user explicitly selects their own
HTTPS credential or anonymous access. Tokens use versioned AES-GCM with owner,
instance and credential ID as authenticated data. Only the API mounts the keyring,
separate from database backups. Upstream requests pin validated DNS addresses,
verify the original TLS hostname and reject redirects. Internal networks require
explicit per-instance exceptions. Current Plane visibility, credential ownership
and upstream permissions are checked on every read, without fallback credentials.
Branches resolve to commit SHAs before bounded directory/text reads.

As of bdde88a622 the Gateway uses the official TypeScript server SDK 2.4.0 and
Node adapter 2.1.2 on Node 24.15.0. Each HTTP request receives its own SDK instance
and captured bearer; no global user context is shared. Existing SQLite tables,
Fernet envelopes and Python-compatible canonical fingerprints allow bidirectional
code rollback without resetting decisions. The old Python image is a rollback
artifact, not the active runtime. MCP now uses DOT OAuthLibCore/OAuthLibMixin and
an OAuth2Validator storage adapter; DOT internally uses OAuthLib for protocol
processing. Existing Delegation/Code/Token digest records remain authoritative,
so grant IDs, revocation and cross-version receipt replay survive the cutover.
DOT bearer token/code tables are not used for MCP secrets. See [cutover acceptance](mcp-dot.md).
