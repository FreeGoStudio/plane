# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Queue account intents without network access or administrator credentials."""

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from plane.db.models import User, CompanyAccount, Delegation, Session, APIToken


@receiver(post_save, sender=User, dispatch_uid="singularity-company-account")
def company_user_changed(sender, instance, created, raw=False, **kwargs):
    if raw:
        return
    # Revocation is a Plane identity lifecycle rule, independent of provisioning.
    # Removing sessions and pending codes prevents resurrection after reactivation.
    if not instance.is_active:
        APIToken.objects.filter(user=instance).update(is_active=False)
        Session.objects.filter(user_id=str(instance.pk)).delete()
        Delegation.objects.filter(user=instance, revoked_at__isnull=True).update(revoked_at=timezone.now())
        from oauth2_provider.models import get_access_token_model, get_refresh_token_model, get_grant_model

        get_grant_model().objects.filter(user=instance).delete()
        get_refresh_token_model().objects.filter(user=instance).delete()
        get_access_token_model().objects.filter(user=instance).delete()
    if not settings.SINGULARITY_COMPANY_ENABLED or instance.is_bot:
        return
    if created:
        CompanyAccount.objects.get_or_create(
            user=instance,
            defaults={
                "instance_url": settings.SINGULARITY_COMPANY_URL.rstrip("/"),
                "status": "pending" if instance.is_active and instance.is_email_verified else "awaiting_activation",
            },
        )
    elif instance.is_active and instance.is_email_verified:
        CompanyAccount.objects.filter(user=instance, status="awaiting_activation").update(
            status="pending", next_attempt_at=timezone.now()
        )
    if not instance.is_active:
        CompanyAccount.objects.filter(user=instance).exclude(status="blocked").update(next_attempt_at=timezone.now())
