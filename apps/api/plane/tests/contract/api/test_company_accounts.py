# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Durable company provisioning contracts with an API-only GitLab fixture."""

from unittest.mock import patch
import pytest
from django.test import Client
from plane.db.models import User, CompanyAccount
from plane.singularity.company import CompanyError, request_account, process_account
from plane.singularity.oidc import company_authorized

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def company_settings(settings):
    settings.SINGULARITY_COMPANY_ENABLED = True
    settings.SINGULARITY_COMPANY_URL = "https://gitlab.company.test"


def person(name="alice", verified=True):
    return User.objects.create(username=name, email=f"{name}@company.test", is_active=True, is_email_verified=verified)


class GitLab:
    base = "https://gitlab.company.test"

    def __init__(self):
        self.users, self.created, self.calls = {}, 0, []
        self.lose_response = False

    def identity_users(self, subject):
        return [u for u in self.users.values() if any(i["extern_uid"] == str(subject) for i in u["identities"])]

    def call(self, method, path, **kwargs):
        self.calls.append((method, path))
        if path == "users" and method == "GET":
            p = kwargs["params"]
            return [
                u
                for u in self.users.values()
                if u.get("email") == p.get("search") or u.get("username") == p.get("username")
            ]
        if path == "users" and method == "POST":
            self.created += 1
            data = kwargs["json"]
            assert not data["admin"] and data["projects_limit"] == 0
            self.users[self.created] = {
                "id": self.created,
                "email": data["email"],
                "username": data["username"],
                "state": "active",
                "identities": [{"provider": data["provider"], "extern_uid": data["extern_uid"]}],
            }
            if self.lose_response:
                self.lose_response = False
                raise CompanyError("company_unreachable")
            return self.users[self.created]
        uid = int(path.split("/")[1])
        if path.endswith("/block"):
            self.users[uid]["state"] = "blocked"
        elif method == "PUT":
            self.users[uid]["identities"] = [kwargs["json"]]
        return self.users[uid]


def test_new_user_activation_and_old_user_opt_in(settings):
    new = person(verified=False)
    assert CompanyAccount.objects.get(user=new).status == "awaiting_activation"
    new.is_email_verified = True
    new.save()
    assert CompanyAccount.objects.get(user=new).status == "pending"
    settings.SINGULARITY_COMPANY_ENABLED = False
    old = person("old")
    assert not CompanyAccount.objects.filter(user=old).exists()
    settings.SINGULARITY_COMPANY_ENABLED = True
    assert request_account(old).status == "pending"


def test_response_loss_reconciles_without_duplicate_and_blocks_only_managed():
    user = person()
    gitlab = GitLab()
    gitlab.lose_response = True
    process_account(user.pk, gitlab)
    assert CompanyAccount.objects.get(user=user).status == "retry"
    assert not company_authorized(user, "company-gitlab")
    process_account(user.pk, gitlab)
    row = CompanyAccount.objects.get(user=user)
    assert row.status == "linked" and row.managed
    assert gitlab.created == 1
    assert company_authorized(user, "company-gitlab")
    process_account(user.pk, gitlab)
    assert gitlab.created == 1
    user.is_active = False
    user.save()
    process_account(user.pk, gitlab)
    assert CompanyAccount.objects.get(user=user).status == "blocked"
    assert gitlab.users[row.external_id]["state"] == "blocked"


def test_same_email_requires_proof_then_links_without_taking_ownership():
    user = person()
    gitlab = GitLab()
    gitlab.users[99] = {"id": 99, "email": user.email, "username": "existing", "state": "active", "identities": []}
    process_account(user.pk, gitlab)
    row = CompanyAccount.objects.get(user=user)
    assert row.status == "conflict" and row.external_id is None
    client = Client()
    client.force_login(user)
    with patch("plane.singularity.company_views.GitLabCompanyClient") as adapter:
        adapter.return_value.call.return_value = gitlab.users[99]
        assert (
            client.post("/auth/singularity/company-account/", {"action": "link", "gitlab_token": "proof"}).status_code
            == 200
        )
    process_account(user.pk, gitlab)
    row.refresh_from_db()
    assert row.external_id == 99 and not row.managed and row.status == "linked"
    user.is_active = False
    user.save()
    process_account(user.pk, gitlab)
    assert gitlab.users[99]["state"] == "active"
    assert CompanyAccount.objects.get(user=user).status == "disconnected"


def test_company_proof_never_overwrites_existing_identity():
    user = person()
    gitlab = GitLab()
    gitlab.users[99] = {
        "id": 99,
        "email": user.email,
        "username": "existing",
        "state": "active",
        "identities": [{"provider": "openid_connect", "extern_uid": "someone-else"}],
    }
    CompanyAccount.objects.filter(user=user).update(proposed_external_id=99)
    process_account(user.pk, gitlab)
    assert CompanyAccount.objects.get(user=user).status == "conflict"
    assert ("PUT", "users/99") not in gitlab.calls


def test_no_bot_or_unverified_provisioning():
    bot = User.objects.create(username="bot", email="bot@company.test", is_bot=True, is_email_verified=True)
    assert not CompanyAccount.objects.filter(user=bot).exists()
    with pytest.raises(CompanyError):
        request_account(bot)
    user = person(verified=False)
    gitlab = GitLab()
    process_account(user.pk, gitlab)
    assert gitlab.created == 0


def test_instance_change_fails_closed(settings):
    user = person()
    gitlab = GitLab()
    gitlab.base = "https://other.company.test"
    process_account(user.pk, gitlab)
    assert CompanyAccount.objects.get(user=user).error_code == "company_instance_changed"
    assert gitlab.created == 0
