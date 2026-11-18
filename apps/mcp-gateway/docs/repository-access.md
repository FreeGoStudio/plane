# Repository access

## Required project repository bindings (2026-11-18)

Projects now have two explicit slots in `ProjectRepositoryBinding`:
`documentation_repository_id` (项目文档仓库) and `prototype_repository_id`
(Storybook 原型仓库). Each slot references an existing `ProjectRepository`, whose
stable identity is hosting instance plus upstream repository ID. URLs are access
metadata, not identity. Development/reference mappings remain plural.

The database enforces one binding row per project and distinct repositories for
the two slots. The service validates project ownership, purpose and availability.
Only a project administrator using a CSRF-protected session can configure slots;
AI/delegated callers cannot configure or create repositories. Changes use
`expected_revision`, serialize on the project row and append an immutable API-level
history snapshot with actor and time. Existing repository mappings are not deleted.
Changing the purpose of a bound mapping is refused. Disabling it blocks execution
instead of selecting another repository. Historical snapshots retain old identities.

Configuration: project settings → repositories → required repository bindings.
Register an existing repository with purpose `documentation` or `prototype`, then
explicitly assign it to its slot. Registration does not select a slot implicitly.
The settings API is `GET/PATCH .../repository-bindings/`; null cannot clear an
existing slot. A project may be incompletely configured, but operations requiring
an absent slot return `project_repository_binding_required` (409).

`resolve_project_repository` resolves a role without accepting a URL/repository ID.
`read_bound_project_repository` reads through that role with the caller's own
connection. Both require `repositories:read`, project membership and current
availability. Existing delegated reads by ID also refuse an unbound documentation
or prototype mapping. General development/reference browsing remains available.
Session preview of registered repositories is retained for administrator setup.

Migration `0134_project_repository_bindings` is additive and deliberately does not
guess bindings from names or select the first existing repository. Apply it before
deploying API/Web/Gateway, explicitly configure existing projects, then deploy the
workbench consumer. Text-only WBS operations do not acquire a new repository
prerequisite; freezing Git PRD/Storybook inputs into WBS is a separate design item.

The workbench source now resolves Plane bindings, rejects mismatched local IDs,
GitLab instances and Git origin/push URLs, and disables runtime repository creation
and fork/import creation paths. Its initialization reuses already-bound repositories.
Deploy with a project-scoped execution identity that cannot create repositories;
the operator must verify denied creation with that identity. Application checks do
not revoke unrelated GitLab credentials or constrain arbitrary external CLI use.
No live GitLab account permissions or existing project bindings were changed by
this source implementation.

Execution PAT bot identities may resolve/read bindings; they cannot configure them.

Validation: 22 API contracts (including permissions, stale revisions, history,
missing/disabled bindings and ID bypass), migration consistency, 24 Gateway tests,
Web type checking and targeted lint passed. An isolated Chrome component harness
with mocked API verified Chinese labels, slot submission, revision-conflict handling
and member read-only controls with zero page errors. This is not live deployment
acceptance. Repository locale keys are synchronized;
the full locale check still reports 886 pre-existing missing keys in most locales.
New/updated translations are `machine_translated`; native-language review remains
follow-up work. Deployment and real-project acceptance are separate from these
local checks.

## Project-native connections (2026-11-14)

The native route `/{workspace}/settings/projects/{project}/repositories/` owns
repository configuration, each member's connection and immutable file previews.
Old project configuration URLs redirect there. The profile sidebar no longer
promotes credential setup before a project is selected. Existing vaults, explicit
anonymous selections, upstream adapters and administrator repository APIs remain.
The legacy personal URL remains available for existing credential/host maintenance.

`list_project_repositories` and `read_project_repository` are read-only MCP tools.
They require `repositories:read`; existing OAuth grants are not silently expanded.
When a connection is absent, expired, revoked or rejected with upstream 401, reads
return `authorization_required` with a project/repository link. The user connects
in Plane and the client retries the original read. No callback can execute AI
instructions, and clients unable to resume automatically ask the user to continue.
403/404, network failures and rate limiting do not produce misleading login loops.
Project membership and upstream permission are checked separately on each read.

Only browser sessions can configure connections. OAuth uses a ten-minute signed
state, session/owner/repository binding, S256 PKCE and single-use callback state.
The callback verifies upstream identity and target repository visibility before
saving an encrypted personal credential and selection. Cancelling or failing does
not replace the old selection. The browser returns to the original native project
page; tokens never enter URLs or AI responses. Expired OAuth access tokens currently
require reconnecting; refresh tokens are not retained. Disconnecting a repository
removes that selection, not the upstream grant or selections in other projects.

Operator setup: register an OAuth application separately on each hosting instance,
with exact callback `{WEB_URL}/auth/singularity/repository-callback/`. Mount a private
JSON file only in the API and set `SINGULARITY_REPOSITORY_OAUTH_FILE` to its path.
It maps instance UUIDs to `client_id` and `client_secret`. Do not commit the file.
GitLab requests `read_api`; GitHub OAuth requests `repo` (upstream write capability
is disclosed in the UI, while Plane only exposes reads). Without a registered app,
the UI explains the missing setup and retains personal-token configuration.
For private GitLab API authorities, existing explicit CIDRs/TLS rules still apply.
Set Gateway `PLANE_PUBLIC_URL` to the canonical Plane browser origin so it can
validate authorization links independently of its internal `PLANE_URL` authority.

Protocol references: [GitLab OAuth](https://docs.gitlab.com/api/oauth2/),
[GitHub OAuth flow](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps).
External GitLab/GitHub instances still require their operator-provided app setup
and real-account acceptance; local contracts do not substitute for those checks.

## Credential storage foundation

Repository instances, project mappings, external identities, owner credentials,
explicit credential selections and metadata-only access audit are separate from
Plane login accounts. A project can contain the same repository ID/path from
different instances. Only one registered instance can be the company primary.

`SINGULARITY_REPOSITORIES_ENABLED` defaults off. `SINGULARITY_REPOSITORY_KEY_FILE`
points to an independently mounted JSON file with a `current` version string and
a `keys` object mapping versions to base64-encoded random 32-byte AES keys. Create
keys with the deployment secret manager; do not use examples or Plane SECRET_KEY.
Restrict file permissions and back up the key file separately from the database.

AES-256-GCM uses a random 12-byte nonce and authenticated context binding the
credential UUID, owner, instance and kind. Ciphertext cannot be moved to another
user or host. Neither ciphertext nor plaintext belongs in API read serializers.
Repository selection requires the current user's project visibility and credential
ownership. Expired/revoked credentials and disabled users, repositories or hosts
are refused; anonymous access is an explicit selection, never an error fallback.

For rotation, atomically install a key file containing the old and new keys with
the new `current`, then run `python manage.py rotate_repository_credentials`.
The command locks and re-encrypts live rows in one transaction. Retain prior key
versions for as long as any database backup or live row can reference them. The
backup restoration contract test decrypts an old database ciphertext using its
corresponding retained key, and fails closed when that key is missing. A real
deployment backup/recovery drill is still required.

This foundation is not yet the complete repository feature: upstream connectors,
personal/project configuration APIs and UI, and live multi-instance file-content
verification are subsequent P3 units. No repository MCP tool is added.

## Read adapters

GitHub and GitLab adapters resolve refs to commit SHA before reading trees/files.
Directory pages have 100 entries. GitHub uses nonrecursive Git trees; truncated
upstream trees return an explicit limit error. Files are limited to 1 MiB UTF-8;
LFS pointers, symlinks and submodules are not followed. GitLab parent lookup is
bounded at 100 pages and reports its limit explicitly. File content stays text;
consumers must render via textContent rather than HTML.

Transport permits only registered API authorities, resolves and validates every
DNS result, pins one allowed IP while verifying the original TLS hostname, rejects
redirects, bounds response bytes and has no credential/anonymous fallback. Private
ranges require explicit operator configuration per instance. HTTPS is default;
HTTP is only an operator-enabled internal exception. Error bodies are not retained.

Validation: 27 provider/transport contracts passed. A real anonymous read of public
GitHub makeplane/plane resolved commit 290383d7f92fa8995ea2adbd12442220b3b9b525,
listed 35 root entries, read the 7,740-byte README.md and independently recomputed
its Git blob SHA matching the API result. This does not replace private-repository,
two-user or multi-GitLab live acceptance.

API contracts follow [GitHub contents](https://docs.github.com/en/rest/repos/contents),
[GitLab repositories](https://docs.gitlab.com/api/repositories/) and
[GitLab files](https://docs.gitlab.com/api/repository_files/); pinned-IP TLS follows
[urllib3 custom SNI](https://urllib3.readthedocs.io/en/stable/advanced-usage.html).

## Session API

Under /api/singularity/v1/: `repository-hosts/` lists registered instances and
allows native InstanceAdmin registration; `repository-credentials/` and its UUID
child support owner-only creation/replacement/list/revocation. Project paths under
`workspaces/{slug}/projects/{id}/repositories/` support admin configuration and
member listing; `/{repo}/access/` selects the current user's credential or explicit
anonymous mode; `/{repo}/tree/` and `/{repo}/file/` read pinned content.

The `repository-hosts` route intentionally avoids the legacy session middleware's
substring-based `instances` admin-cookie switch. No global middleware change is
made. Browser session writes require CSRF. Unknown fields (including spoofed owner
IDs) are rejected. Responses contain safe metadata only; existing Singularity
logging exclusions prevent credential bodies/headers from being persisted. Each
request creates a metadata-only trace with the Plane actor and selected external
identity. Identity validation via /user is not a promise of repository write rights.

Six session API contracts passed, including owner isolation, project admin/member
separation, spoofed owner rejection, revocation, deactivation, CSRF and secret-free
responses/audit. Configuration pages and multi-instance live API acceptance remain
pending for this unit.

## Configuration UI

Personal `/auth/singularity/repository-access/` supports create/replace/revoke,
external actor labels and project navigation. Project pages provide admin repository
configuration, each member's explicit credential selection, paged trees and text
previews pinned to commit SHA. File bodies use textContent, not HTML. Server-side
session and project checks protect page access. Plane profile/project sidebars show
links only when the repository feature endpoint is available.

Validation: 7 API/page tests passed (including escaped malicious project names),
JavaScript syntax, targeted OxLint and web TypeScript checks passed. Both new label
keys exist in all 22 locales; the full i18n sync reports the pre-existing 886 missing
keys in non-English/non-Simplified-Chinese locales. Comparison against HEAD confirms
this change adds no new missing keys. Local documentation comments checked; no PR
exists, so remote documentation-coverage checks remain pending. Dynamic browser
create/replace/revoke/read and deployment verification are still pending here.
