# ruff: noqa: F811
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Automatic document access across repositories and bounded preparation failures."""

from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
from django.utils import timezone
from django.test import Client

from plane.db.models import DocumentRepositoryExecutor, ProjectRepository, ProjectRepositoryBinding
from plane.singularity import document_executor as executor
from plane.singularity.company import CompanyError
from plane.singularity.repository_transport import RepositoryError
from plane.singularity.requirement_merge_request import prepare_one, transport
from plane.singularity.requirement_review import capture, retry_run, adopt
from plane.singularity.vault import VaultError
from .test_requirement_review import review, ready  # noqa: F401
from .test_singularity import world, config  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


class GitLab:
    def __init__(self):
        self.tokens = {}
        self.lose_response = False
        self.fail_repository = None
        self.limit = 90

    def call(self, method, path, **kwargs):
        if path == "application/settings":
            return {"max_personal_access_token_lifetime": self.limit}
        parts = path.split("/")
        project = parts[1]
        if project == self.fail_repository:
            raise CompanyError("company_http_403")
        if method == "POST":
            pk = len(self.tokens) + 1
            token = dict(kwargs["json"], id=pk, user_id=pk + 100, token=f"secret-{pk}", active=True, revoked=False)
            self.tokens[pk] = (project, token)
            if self.lose_response:
                self.lose_response = False
                raise CompanyError("company_unreachable")
            return dict(token)
        if len(parts) == 3:
            return [dict(t) for p, t in self.tokens.values() if p == project]
        p, token = self.tokens[int(parts[3])]
        assert p == project
        if method == "DELETE":
            token.update(active=False, revoked=True)
            return None
        return dict(token)

    def transport(self, instance, secret):
        p, token = next((p, t) for p, t in self.tokens.values() if t["token"] == secret)
        http = Mock()
        http.get.side_effect = lambda path: {"id": token["user_id"]} if path == "/user" else {"id": int(p)}
        return http


@pytest.fixture
def repos(review, world, settings):
    repo = review[0].repository
    instance = repo.instance
    instance.company_primary = True
    instance.save()
    settings.SINGULARITY_MANAGED_REPOSITORY_TOKENS = True
    settings.SINGULARITY_COMPANY_ENABLED = True
    settings.SINGULARITY_COMPANY_URL = "https://git.example"
    second = ProjectRepository.objects.create(
        project=world[4], instance=instance, external_id="24", path="team/second", purpose="documentation"
    )
    ProjectRepositoryBinding.objects.create(project=world[4], documentation_repository=second)
    with patch.object(executor, "keyring", return_value=("v1", {"v1": b"k" * 32})):
        yield repo, second


def due(row):
    row.next_check_at = timezone.now() - timedelta(seconds=1)
    row.save(update_fields=["next_check_at"])


def provision(git):
    with patch.object(executor, "RepositoryTransport", side_effect=git.transport):
        executor.maintain_executors(git)


def test_all_bound_repositories_get_distinct_credentials_and_repeat_is_idempotent(repos):
    git = GitLab()
    provision(git)
    provision(git)
    rows = list(DocumentRepositoryExecutor.objects.order_by("repository__external_id"))
    assert len(rows) == len(git.tokens) == 2
    assert all(r.status == "ready" for r in rows)
    assert rows[0].actor_id != rows[1].actor_id
    for row in rows:
        raw = executor.unseal(row)
        assert raw not in row.encrypted_material
        with patch.object(executor, "RepositoryTransport") as http:
            executor.transport(row.repository)
            assert http.call_args.args[1] == raw
    rows[0].encrypted_material = rows[1].encrypted_material
    with pytest.raises(VaultError):
        executor.unseal(rows[0])


def test_new_binding_is_picked_up_on_next_maintenance(repos):
    repo, second = repos
    binding = ProjectRepositoryBinding.objects.get(documentation_repository=second)
    binding.documentation_repository = None
    binding.save()
    git = GitLab()
    provision(git)
    assert DocumentRepositoryExecutor.objects.count() == 1
    binding.documentation_repository = second
    binding.save()
    provision(git)
    assert DocumentRepositoryExecutor.objects.count() == 2


def test_one_failed_repository_does_not_prevent_other_repository(repos):
    git = GitLab()
    git.fail_repository = "22"
    provision(git)
    assert DocumentRepositoryExecutor.objects.get(repository=repos[0]).status == "error"
    assert DocumentRepositoryExecutor.objects.get(repository=repos[1]).status == "ready"


def test_response_loss_cleans_only_owned_orphan_before_retry(repos):
    git = GitLab()
    git.lose_response = True
    with patch.object(executor, "RepositoryTransport", side_effect=git.transport):
        executor.reconcile(repos[0], git)
        row = DocumentRepositoryExecutor.objects.get(repository=repos[0])
        assert row.status == "error" and row.issuance_name
        due(row)
        executor.reconcile(repos[0], git)
    row.refresh_from_db()
    assert row.status == "ready" and row.issuance_name == ""
    assert git.tokens[1][1]["revoked"]
    assert not git.tokens[row.token_id][1]["revoked"]


def test_expiry_renews_only_due_repository_and_respects_instance_limit(repos):
    git = GitLab()
    git.limit = 30
    provision(git)
    first = DocumentRepositoryExecutor.objects.get(repository=repos[0])
    old = first.token_id
    assert (first.expires_at - timezone.now().date()).days == 30
    git.tokens[old][1]["expires_at"] = (timezone.now().date() + timedelta(days=1)).isoformat()
    due(first)
    provision(git)
    first.refresh_from_db()
    assert first.token_id != old and git.tokens[old][1]["revoked"]
    assert len(git.tokens) == 3


def test_unmanaged_instance_and_unbound_repository_never_get_admin_credentials(repos):
    repo, second = repos
    repo.instance.company_primary = False
    repo.instance.save()
    git = GitLab()
    provision(git)
    assert not git.tokens
    second.refresh_from_db()
    with pytest.raises(RepositoryError, match="document_executor_instance_not_managed"):
        executor.transport(second)


def test_new_repository_never_falls_back_to_legacy_global_token(repos, review, monkeypatch):
    monkeypatch.setenv("DOCUMENT_ADOPTION_TOKEN_FILE", "/must-not-be-read")
    review[0].repository = repos[1]
    with pytest.raises(RepositoryError, match="document_executor_pending"):
        transport(review[0])


def test_executor_identity_is_repository_scoped(repos):
    git = GitLab()
    provision(git)
    first = DocumentRepositoryExecutor.objects.get(repository=repos[0])
    assert executor.actor_matches(repos[0].pk, first.actor_id)
    assert not executor.actor_matches(repos[1].pk, first.actor_id)


def test_platform_executor_does_not_depend_on_personal_pat_switch(repos, settings):
    settings.SINGULARITY_MANAGED_REPOSITORY_TOKENS = False
    git = GitLab()
    provision(git)
    assert DocumentRepositoryExecutor.objects.filter(status="ready").count() == 2


def test_short_instance_lifetime_does_not_rotate_on_every_check(repos):
    git = GitLab()
    git.limit = 7
    provision(git)
    for row in DocumentRepositoryExecutor.objects.all():
        due(row)
    provision(git)
    assert len(git.tokens) == 2


def test_legacy_repository_keeps_working_until_new_credential_is_validated(repos, review, monkeypatch, tmp_path):
    token = tmp_path / "legacy-token"
    token.write_text("legacy-project-22")
    monkeypatch.setenv("DOCUMENT_ADOPTION_TOKEN_FILE", str(token))
    DocumentRepositoryExecutor.objects.create(repository=repos[0], status="error")
    with patch("plane.singularity.requirement_merge_request.RepositoryTransport") as http:
        transport(review[0])
        assert http.call_args.args[1] == "legacy-project-22"


def test_gate_accepts_repository_executor_only_with_exact_running_grant(review, world, monkeypatch):
    row = ready(review)
    grant = adopt(world[0], row, {"target_sha": "b" * 40, "idempotency_key": "managed-gate-test"})
    DocumentRepositoryExecutor.objects.create(
        repository=row.config.repository,
        status="ready",
        actor_id="user-101",
        expires_at=timezone.now().date() + timedelta(days=30),
    )
    monkeypatch.setenv("DOCUMENT_REVIEW_GATE_SECRET", "test-gate")
    monkeypatch.setenv("DOCUMENT_REVIEW_EXECUTOR_GL_ID", "user-99")
    monkeypatch.delenv("DOCUMENT_REVIEW_GATED_REPOSITORIES")
    client = Client()
    payload = {
        "repository_id": str(row.config.repository_id),
        "ref": "refs/heads/POS-1",
        "old_sha": "b" * 40,
        "new_sha": "a" * 40,
        "actor": "user-101",
    }

    def gate(**changes):
        return client.post(
            "/api/singularity/v1/requirement-review/adoption-gate/",
            {**payload, **changes},
            content_type="application/json",
            HTTP_X_REVIEW_GATE_TOKEN="test-gate",
        )

    assert gate().status_code == 403
    grant.status = "running"
    grant.save()
    assert gate().json()["allowed"]
    assert gate(actor="user-99").status_code == 403
    assert gate(new_sha="c" * 40).status_code == 403


@pytest.mark.parametrize("code,status", [("upstream_resource_invisible", 404), ("upstream_access_denied", 403)])
def test_permanent_preparation_failure_ends_queue_and_can_retry(review, world, code, status):
    row = capture(review[0])
    with patch(
        "plane.singularity.requirement_merge_request.ensure_merge_request", side_effect=RepositoryError(code, status)
    ):
        prepare_one()
    row.refresh_from_db()
    assert row.status == "failed" and row.error == code and row.attempts == 0
    new = retry_run(world[0], row, "retry-preparation-1")
    assert new.status == "queued" and new.preparation_attempts == 0


def test_transient_preparation_is_bounded_and_does_not_consume_ai_attempts(review):
    row = capture(review[0])
    with patch(
        "plane.singularity.requirement_merge_request.ensure_merge_request",
        side_effect=RepositoryError("document_executor_pending", 503),
    ):
        for attempt in range(5):
            row.dispatch_at = None
            row.save(update_fields=["dispatch_at"])
            prepare_one()
            row.refresh_from_db()
            assert row.status == ("failed" if attempt == 4 else "queued")
    assert row.preparation_attempts == 5 and row.attempts == 0


def test_preparation_recovers_when_executor_becomes_ready(review):
    row = capture(review[0])
    with patch(
        "plane.singularity.requirement_merge_request.ensure_merge_request",
        side_effect=RepositoryError("document_executor_pending", 503),
    ):
        prepare_one()
    row.refresh_from_db()
    row.dispatch_at = None
    row.save(update_fields=["dispatch_at"])
    with patch("plane.singularity.requirement_merge_request.ensure_merge_request"):
        prepare_one()
    row.refresh_from_db()
    assert row.status == "queued" and row.error == "" and row.dispatch_at is None
