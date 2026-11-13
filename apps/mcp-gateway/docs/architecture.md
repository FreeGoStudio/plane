# Identity and authorization boundary

Plane owns users, account status, project visibility and work-item permissions.
The gateway is a separate Python MCP SDK process with a private SQLite vault;
it has no Plane database connection. There is no GitLab dependency.

Plane is also the OAuth issuer. A pre-registered public Codex client receives an
opaque token for the gateway resource after S256 consent. Plane stores only
SHA-256 digests of access, refresh and authorization codes; refresh rotates.
Client tokens have a 10-minute lifetime and seven-day refresh lifetime.

The gateway validates the token by authenticated inspection at Plane on every
MCP HTTP request and again on every tool invocation. The confidential private
`/auth/singularity/exchange/` endpoint accepts that token **only for delegation
exchange**, never as a work-item resource credential. It issues a distinct,
five-minute `plane` audience token with the same grant and scopes. Plane resource
endpoints reject gateway-audience tokens. Gateway-audience verification rejects
Plane tokens. The client never receives the downstream pair.

The exchange secret identifies the gateway, not a user: by itself it cannot
read or write any work item. Downstream tokens are encrypted with a separate
Fernet vault key. The issuer/resource are deployment configuration, not model
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
