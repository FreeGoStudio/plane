# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
# ruff: noqa: F811
"""Code review authority, immutable evidence and completion contracts."""

from unittest.mock import patch
import pytest
from django.test import Client
from rest_framework.exceptions import ValidationError
from plane.db.models import Issue, ProjectRepository, RepositoryInstance
from .test_singularity import world, config  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def review(world):
    user, _, workspace, project, _ = world
    issue = Issue.objects.create(name="Review", project=project, workspace=workspace)
    instance = RepositoryInstance.objects.create(
        name="GitLab", provider="gitlab", api_url="https://git.example/api/v4", web_url="https://git.example"
    )
    repo = ProjectRepository.objects.create(
        project=project, instance=instance, external_id="22", path="team/code", purpose="development"
    )
    version = dict(
        source_sha="a" * 40,
        target_sha="b" * 40,
        merge_base="c" * 40,
        target_branch="main",
        source_branch="feature",
        state="opened",
        draft=False,
        web_url="https://git.example/team/code/-/merge_requests/7",
    )
    with patch("plane.singularity.code_review.remote_version", return_value=version):
        yield user, issue, repo, version


def associate(review):
    from plane.singularity.code_review import add_link

    user, issue, repo, _ = review
    return add_link(user, issue, {"repository_id": str(repo.pk), "mr_iid": 7, "expected_revision": 0})


def test_association_is_explicit_and_duplicate_is_rejected(review):
    from plane.db.models import CodeReviewRun
    from plane.singularity.code_review import add_link, revision, ReviewConflict

    link = associate(review)
    assert link.repository == review[2]
    assert CodeReviewRun.objects.filter(link=link, status="queued").count() == 1
    with pytest.raises(ReviewConflict):
        add_link(
            review[0],
            review[1],
            {"repository_id": str(review[2].pk), "mr_iid": 7, "expected_revision": revision(review[1])},
        )


def test_cross_project_and_non_development_repository_rejected(review, world):
    from plane.singularity.code_review import add_link

    repo = review[2]
    for field, value in [("project", world[4]), ("purpose", "documentation")]:
        original = getattr(repo, field)
        setattr(repo, field, value)
        repo.save()
        with pytest.raises(ValidationError):
            add_link(review[0], review[1], {"repository_id": str(repo.pk), "mr_iid": 7, "expected_revision": 0})
        setattr(repo, field, original)


def test_remove_requires_reason_and_preserves_history(review):
    from plane.db.models import CodeReviewEvent, CodeReviewRun
    from plane.singularity.code_review import remove_link, revision

    link = associate(review)
    with pytest.raises(ValidationError):
        remove_link(review[0], link, {"reason": "", "expected_revision": revision(review[1])})
    remove_link(review[0], link, {"reason": "关联错误", "expected_revision": revision(review[1])})
    link.refresh_from_db()
    assert not link.active
    assert CodeReviewRun.objects.filter(link=link).exists()
    assert CodeReviewEvent.objects.filter(issue=review[1], kind="unlinked", payload__reason="关联错误").exists()


def test_api_lists_only_scoped_links_and_runs(review):
    link = associate(review)
    client = Client()
    client.force_login(review[0])
    issue = review[1]
    url = (
        f"/api/singularity/v1/workspaces/{issue.workspace.slug}/projects/{issue.project_id}/"
        f"work-items/{issue.pk}/code-review/"
    )
    response = client.get(url)
    assert response.status_code == 200, response.content
    assert response.json()["links"][0]["id"] == str(link.pk)
    assert response.json()["runs"][0]["source_sha"] == "a" * 40
