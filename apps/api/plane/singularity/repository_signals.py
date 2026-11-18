# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from plane.db.models import Project, RepositoryProvisioning


@receiver(post_save, sender=Project, dispatch_uid="project_repository_initialization")
def project_created(sender, instance, created, raw=False, **kwargs):
    # Persist with the project transaction. No network/broker call in project creation.
    if created and not raw and settings.SINGULARITY_REPOSITORY_PROVISIONING_ENABLED:
        RepositoryProvisioning.objects.get_or_create(
            project=instance, defaults={"requested_by_id": instance.created_by_id}
        )
