# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Registered native operations; scope is additional consent, never business RBAC."""

from rest_framework.exceptions import PermissionDenied

OPERATIONS = {
    "UserEndpoint": {"GET": "profile:read"},
    "ProjectListCreateAPIEndpoint": {"GET": "projects:read"},
    "ProjectDetailAPIEndpoint": {"GET": "projects:read"},
    "ProjectSummaryAPIEndpoint": {"GET": "projects:read"},
    "IssueListCreateAPIEndpoint": {"GET": "workitems:read", "POST": "workitems:write"},
    "IssueDetailAPIEndpoint": {
        "GET": "workitems:read",
        "PATCH": "workitems:write",
        "DELETE": "workitems:delete",
    },
    "WorkspaceIssueAPIEndpoint": {"GET": "workitems:read"},
    "IssueSearchEndpoint": {"GET": "workitems:read"},
    "StateListCreateAPIEndpoint": {"GET": "workitems:read"},
    "LabelListCreateAPIEndpoint": {"GET": "workitems:read"},
    "ProjectMemberListCreateAPIEndpoint": {"GET": "workitems:read"},
}


def check_operation_scope(request, token):
    """A native personal token retains native rights; OAuth retains its consent."""
    if token.grant.source_api_token:
        return
    view = request.parser_context["view"]
    method = "GET" if request.method == "HEAD" else request.method
    scope = OPERATIONS.get(type(view).__name__, {}).get(method)
    if scope is None or scope not in token.scopes.split():
        raise PermissionDenied("Insufficient authorization scope for this operation")
