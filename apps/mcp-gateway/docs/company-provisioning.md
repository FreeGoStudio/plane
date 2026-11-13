# Company GitLab provisioning

Company account provisioning is opt-in at deployment (`SINGULARITY_COMPANY_ENABLED=0`
by default), automatic for newly created human users after verification and activation,
and explicit for pre-existing users via `/auth/singularity/company-account/`.

The company URL is fixed by an operator. `CompanyAccount` pins each intent to that
instance, keeps the Plane UUID as OIDC external identity, and never changes project
membership. A dedicated `run_company_provisioner --secret-file /run/secrets/company-admin`
process receives the GitLab management credential. Do not mount this secret in the
API, normal workers or Gateway. `--once` supports controlled recovery and acceptance.

The provisioner checks provider/extern_uid before every create. It commits creation
intent before the API call and serializes each user with a PostgreSQL advisory lock.
Unknown responses are retried by identity reconciliation. Email/username collisions
require the user to prove an existing GitLab account with a personal token; the proof
token is used only for `/user`, never stored. The worker rechecks existing identities
before attaching a new one. Linked existing accounts remain unmanaged.

Pending, failed or conflicting association blocks OIDC code issuance and redemption
for the registered company client. GitLab automatic email linking and JIT creation
must be disabled. Keep emergency administrator login enabled. Do not set a default
project membership for newly provisioned users.

On Plane deactivation, delegated authorizations are revoked. The dedicated worker
blocks only platform-created company users and verifies the remote blocked state.
Existing accounts linked by their owner are disconnected rather than blocked.
Reactivation never automatically unblocks a GitLab account. GitLab's blocked-state
checks reject active sessions; physical removal of stored session records has no
supported endpoint in the inspected GitLab API and remains an operator verification
item, not an implemented API cleanup promise.

Failures store only a sanitized code and retry time, not upstream response bodies.
Unreachable GitLab never rolls back Plane registration or grants access. Pending
creation, status, retry and existing-account proof are visible in the personal UI.

Rollback disables company provisioning and OIDC, stops the dedicated worker and
restores the prior GitLab OmniAuth configuration. Keep identity mappings and created
accounts; do not delete accounts or restore business databases to roll back code.
