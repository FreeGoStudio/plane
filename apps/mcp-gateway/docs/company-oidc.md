# Company SSO identity provider

Status: source implementation only. Company GitLab provisioning and deployment
remain separate acceptance units. Do not enable company SSO before the account
provisioning/association gate is implemented and verified; otherwise GitLab JIT
creation may race platform provisioning.

## Configuration

- Apply dependencies from `apps/api/uv.lock`, then `python manage.py migrate`.
  Django OAuth Toolkit owns its additive `oauth2_provider` migrations. No Plane
  business migration or existing OAuth token conversion is required.
- `SINGULARITY_ENABLED=1` enables the existing delegation service.
- `SINGULARITY_OIDC_ENABLED=0` is the default. Keep it disabled until rollout.
- `SINGULARITY_OIDC_RSA_PRIVATE_KEY` is a PEM RSA private key supplied from the
  deployment secret store. Never commit it, log it, or reuse the Plane application
  secret. Back it up separately from the database with restricted access.
- The stable SSO issuer is `${SINGULARITY_ISSUER}/auth/singularity/oidc`.
  Discovery is at that issuer plus `/.well-known/openid-configuration`.
  The key endpoint contains only public RSA parameters.

Register an exact company HTTPS callback using the operator command:

```sh
python manage.py register_company_oidc_client \
  --client-id company-gitlab \
  --redirect-uri https://gitlab.example/users/auth/openid_connect/callback \
  --secret-file /run/secrets/company-oidc-client
```

The command hashes the application secret through Django OAuth Toolkit, refuses
existing clients, and never prints secrets. There is no public registration UI
or dynamic registration endpoint. Configure GitLab to use authorization-code,
PKCE S256, `openid profile email`, and `sub` as the immutable external identity.
Do not bind by email and do not change GitLab emergency administrator login.

OIDC only identifies the user. Its tokens cannot be exchanged through the MCP
Gateway or used as work-item credentials. UserInfo and code redemption check
current account eligibility. SSO does not issue refresh tokens or repository
access tokens; signing out of Plane is not a promise of downstream single logout.

## Personal MCP tokens

`/auth/singularity/personal-tokens/` requires an active human Plane session and
CSRF protection. Select explicit scopes and 1–90 days (default 30). The response
shows the credential once; configure it as the MCP HTTP bearer credential, never
as a tool argument. `/auth/singularity/connections/` revokes an owner's grant and
all derived delegations. Revocation cannot affect another user's grant.

OAuth MCP access remains 10 minutes. Refresh grants end 30 days after original
consent, including rotations. Exchanged Plane access never exceeds the remaining
life of its source credential. Existing OAuthLib MCP grants are preserved;
Django OAuth Toolkit provides the new SSO protocol rather than silently migrating
live MCP authorizations.

## Verification and rollback

Run contract tests `test_singularity.py`, `test_singularity_personal_tokens.py`,
and `test_singularity_oidc.py` in the isolated Docker test stack. They use real
PostgreSQL and protocol exchanges, not a live company GitLab browser session.

Disable `SINGULARITY_OIDC_ENABLED` to remove every new SSO endpoint. Keep the
additive protocol tables, account associations and keys for recovery. Do not
restore business data just to roll back code. Actual company SSO, account
provisioning, key rotation and browser acceptance are still pending.
