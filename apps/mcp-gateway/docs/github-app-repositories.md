# GitHub App repository connections

## Requirement and delivery boundary

Source: the user's 2026-11-24 request to replace GitHub repository OAuth App
connections with GitHub App authorization for selected repositories and necessary
permissions, followed by “改进” authorizing implementation.

Acceptance unit: selected GitHub repositories, Contents/Metadata read-only,
the member's own GitHub access, refresh/revocation handling, and no legacy-token
bypass. GitLab repository authorization and GitHub login are separate and unchanged.
This is a source implementation, not a production deployment or live GitHub acceptance.

## Configure and connect

1. In GitHub Developer settings, create a **GitHub App**. Choose a descriptive
   name such as `Plane Repository Reader`.
2. Homepage URL is the Plane browser origin (`WEB_URL`). Callback URL is the exact
   value shown in Plane: `{WEB_URL}/auth/singularity/repository-callback/`.
3. Set repository **Contents: Read-only** and **Metadata: Read-only**. Leave all
   other repository, organization and account permissions disabled. Enable
   expiring user access tokens. Leave Device Flow and Webhooks disabled. This
   implementation checks installation status synchronously, without a webhook.
4. A Plane platform administrator saves Client ID, Client Secret, and app slug
   (the final part of `https://github.com/apps/<slug>`) in repository authorization
   setup. Plane verifies the registered app's ID, client ID and permission set.
   No private key or installation token is required for this user-authorized flow.
5. Open **Install GitHub App / select repositories**. An authorized repository or
   organization administrator installs it using **Only select repositories** and
   selects the repositories to connect. Organization approval may be required.
   The link opens a separate tab; return to the original Plane project afterward.
6. Each member clicks **Connect GitHub** and authorizes their account. Installation
   by an administrator does not grant another member access to a private repository.

Saving configuration is not a successful connection. A missing installation,
pending approval, missing repository, `All repositories` installation, suspension,
or extra permission prevents connection/reading and gives an actionable message.

## Access boundary

The encrypted parent credential is a GitHub App **user** token. Its GitHub access
is the intersection of the app's installations and the user's permissions; it is
not itself guaranteed to be restricted to one repository. Plane stores separate
connection records per user, GitHub account, client ID and repository ID, including
the verified installation ID and both token expirations.

Before each authenticated read, Plane checks project membership and the explicit
connection, refreshes the parent token if needed, and checks GitHub's current
`/user/installations` and `/user/installations/{id}/repositories` results. The
installation must still select repositories and grant exactly Contents/Metadata
read access. Plane then calls `/applications/{client_id}/token/scoped` with that
repository ID and read permissions. Content adapters receive this scoped user
token, not a shared installation token or the parent credential. Tokens never
enter frontend responses or MCP results. No cached installation snapshot authorizes
reads. Permission lists are paginated with an explicit failure limit.

The scoped-token endpoint must be supported by the hosting GitHub version. There
is no fallback to a broader token if it is unavailable. Public anonymous reads
remain an explicit separate choice; they do not use any private authorization.

Removing a selected repository, suspending/uninstalling the app, or removing the
member's upstream access blocks the next read. Revoked user tokens are rejected by
GitHub. Local disconnect removes only this member's project selection, not the
app installation or connections in other projects. To revoke the upstream grant,
use GitHub Settings → Applications → Authorized GitHub Apps; installation owners
manage selected repositories in Installed GitHub Apps.

## Migration and rollout

Apply generated migration `0143_github_app_repository_connections` before deploying
the API and web changes together. It adds metadata; it does not relabel old tokens
or change existing project repository IDs/bindings. GitHub's old OAuth configuration
file fallback is no longer used. Configure the App and have users reconnect.

Old GitHub OAuth/PAT credentials are retained for audit/explicit cleanup but cannot
be created, edited, selected for access, or used for authenticated repository reads.
Existing GitLab paths retain their behavior. Old grants still present in GitHub
must be revoked there after migration; changing Plane storage does not revoke them.
Rollback to old code would restore its old permission behavior and is not a secure
way to retain this authorization guarantee.

## Verification

Automated contracts cover connection/state replay, selected installation validation,
read-only permission enforcement, removed repository, suspension, app mismatch,
owner/repository isolation, scoped-token request contents, refresh persistence,
refresh expiry, legacy-token bypass, and encrypted storage. Existing GitLab
connection/refresh/add contracts are retained. UI tests check the installation link,
matching repository credentials and absence of GitHub PAT entry. Run the repository
contract suite in the isolated Docker test stack; use a dedicated test database
when models changed because the default suite reuses its schema without migrations.

Live acceptance still requires a registered GitHub App and two accounts/private
repositories: read selected A, reject unselected B and writes, remove A and reject
the next read, remove a member's GitHub access, refresh real tokens, and verify
organization installation approval. Mock contracts are not evidence that these
external operations have completed.

Local results (2026-11-24): repository-related Docker contracts passed (140 tests);
the GitHub App and connection subset passed after the final refresh-error change
(27 tests, including 19 GitHub App contracts). A separate fresh test database ran
the actual migration graph and the then-current 18 GitHub App contracts successfully.
`makemigrations --check --dry-run` reported no changes and a matching lockfile.
Web component tests (15), TypeScript, targeted Ruff and OxLint passed. Repository
namespace keys match across all 22 locales. Global translation checks still report
1,277 pre-existing missing keys in other namespaces for most locales; comparison
with HEAD found no newly missing keys. New guidance is Chinese/English, with English
fallback text for other locales. Storybook is not installed in the web package;
component tests were used, not a Storybook/browser or live-account acceptance run.

Protocol: [user tokens](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-user-access-token-for-a-github-app),
[installation visibility](https://docs.github.com/en/rest/apps/installations),
[scoped user tokens](https://docs.github.com/en/rest/apps/apps#create-a-scoped-access-token).
