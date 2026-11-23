# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
from types import SimpleNamespace
from unittest.mock import Mock, patch
import pytest
from plane.singularity.code_review_provider import remote_version
from plane.singularity.repository_transport import RepositoryError


def fixture(state):
    source, target, base = "a" * 40, "b" * 40, "c" * 40
    mr = dict(
        target_project_id=16,
        iid=1,
        state=state,
        sha=source,
        diff_refs={"head_sha": source},
        source_branch="feature",
        target_branch="main",
        web_url="https://gitlab.invalid/mr/1",
    )
    provider = Mock()
    provider.resolve.return_value = (None, None, target)
    link = SimpleNamespace(repository=SimpleNamespace(external_id="16"), mr_iid=1)
    return source, target, base, mr, provider, link


def test_first_link_to_merged_mr_uses_final_historical_baseline():
    source, target, base, mr, provider, link = fixture("merged")
    provider.http.get.side_effect = [
        mr,
        [
            {"head_commit_sha": "d" * 40, "start_commit_sha": "e" * 40, "base_commit_sha": "f" * 40},
            {"head_commit_sha": source, "start_commit_sha": target, "base_commit_sha": base},
        ],
    ]
    with patch("plane.singularity.code_review_provider.provider_for", return_value=provider):
        result = remote_version(link)
    assert (result["source_sha"], result["target_sha"], result["merge_base"]) == (source, target, base)
    provider.resolve.assert_not_called()


def test_open_mr_uses_live_target_commit_and_merge_base():
    source, target, base, mr, provider, link = fixture("opened")
    provider.http.get.side_effect = [mr, {"id": base}]
    with patch("plane.singularity.code_review_provider.provider_for", return_value=provider):
        result = remote_version(link)
    assert result["target_sha"] == target
    provider.http.get.assert_called_with("/projects/16/repository/merge_base", {"refs[]": [source, target]})


def test_pending_gitlab_diff_never_uses_old_head():
    _, _, _, mr, provider, link = fixture("opened")
    mr["sha"] = "d" * 40
    provider.http.get.return_value = mr
    with (
        patch("plane.singularity.code_review_provider.provider_for", return_value=provider),
        pytest.raises(RepositoryError) as failure,
    ):
        remote_version(link)
    assert failure.value.code == "review_diff_version_pending"
    assert failure.value.status == 503
