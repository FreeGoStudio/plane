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
