# Repository access

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
