# Deployed Plane capability matrix

Observed 2026-11-13, local instance `http://localhost:8088`, source `D:/plane-source`.
Source package version: 1.5.0; repository license: AGPL-3.0-only.

| Capability                | Baseline evidence                                           | Implementation                                                             |
| ------------------------- | ----------------------------------------------------------- | -------------------------------------------------------------------------- |
| Official API v2 schema    | `/api/v2/schema/` HTTP 404                                  | Not emulated                                                               |
| Official v2 user identity | `/api/v2/users/me/` HTTP 404                                | Custom delegated identity endpoint                                         |
| Public API v1             | Registered in `plane.urls`; anonymous identity HTTP 401     | Existing API-key behavior retained                                         |
| User-delegated OAuth      | No provider/issuer routes in baseline                       | DOT authorization-code + S256 with digest storage, rotation and revocation |
| Third-party GitLab login  | Existing inbound login provider                             | Unchanged; not a user-delegation provider                                  |
| Permission prediction v2  | Not registered                                              | Custom hints call Plane's existing permission logic                        |
| Work-item create/update   | Existing serializers, permissions and activity tasks        | Narrow delegated adapter reuses them                                       |
| Atomic conditional update | Baseline PATCH reads then saves                             | Row lock before native/delegated read plus expected version                |
| External-key upsert       | Baseline checks without a shared transaction receipt        | Delegated UUID receipt + unique primary key, atomic write                  |
| Types                     | Not an MVP dependency                                       | Existing configured labels only                                            |
| States                    | Existing per-project State objects                          | Existing 待整理 or explicit configuration                                  |
| ChatGPT writes            | Not verified, shared account unsuitable for personal grants | Out of scope                                                               |

OAuth and A01–A14 contracts are tested against an isolated PostgreSQL instance.
Deployment and actual Codex acceptance evidence must be recorded separately;
unit/contract success does not establish real-client acceptance.
