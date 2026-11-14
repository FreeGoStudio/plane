# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Optional retry protection shared by all callers of native work-item mutations."""

import hashlib
import json
from functools import partial, wraps

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from rest_framework.response import Response

from plane.db.models import APIMutationReceipt, Issue, ProjectMember


def after_commit(task, **kwargs):
    transaction.on_commit(partial(task.delay, **kwargs))


def idempotent_mutation(function):
    @wraps(function)
    def wrapped(self, request, *args, **kwargs):
        key = request.headers.get("Idempotency-Key")
        if key is None:
            return function(self, request, *args, **kwargs)
        if not key or len(key) > 200:
            return Response({"error": "Idempotency-Key must contain 1 to 200 characters"}, status=400)
        digest = hashlib.sha256(
            json.dumps(
                [request.method, type(self).__name__, kwargs, request.data, request.headers.get("If-Match")],
                sort_keys=True,
                cls=DjangoJSONEncoder,
            ).encode()
        ).hexdigest()
        with transaction.atomic():
            receipt, _ = APIMutationReceipt.objects.get_or_create(
                credential_id=request.plane_credential_id,
                key_digest=hashlib.sha256(key.encode()).hexdigest(),
                defaults={"payload_digest": digest},
            )
            receipt = APIMutationReceipt.objects.select_for_update().get(pk=receipt.pk)
            if receipt.payload_digest != digest:
                return Response({"error": "idempotency_conflict"}, status=409)
            if receipt.status:
                # Authentication, scope and current project membership were checked in initial().
                # Recheck the extra creator/admin rule even after the deleted row is gone.
                if (
                    request.method == "DELETE"
                    and receipt.creator_id != request.user.pk
                    and not ProjectMember.objects.filter(
                        project_id=kwargs["project_id"],
                        member=request.user,
                        role=20,
                        is_active=True,
                    ).exists()
                ):
                    return Response({"error": "Only admin or creator can delete the work item"}, status=403)
                if (
                    request.method != "DELETE"
                    and not Issue.objects.filter(
                        pk=receipt.result["id"],
                        project_id=kwargs["project_id"],
                    ).exists()
                ):
                    return Response({"error": "The requested resource does not exist."}, status=404)
                return Response(receipt.result, status=receipt.status)
            if request.method == "DELETE":
                receipt.creator_id = (
                    Issue.objects.filter(pk=kwargs["pk"], project_id=kwargs["project_id"])
                    .values_list(
                        "created_by_id",
                        flat=True,
                    )
                    .first()
                )
            response = function(self, request, *args, **kwargs)
            if 200 <= response.status_code < 300:
                receipt.result = json.loads(json.dumps(response.data, cls=DjangoJSONEncoder))
                receipt.status = response.status_code
                receipt.save()
            else:
                receipt.delete()
            return response

    return wrapped
