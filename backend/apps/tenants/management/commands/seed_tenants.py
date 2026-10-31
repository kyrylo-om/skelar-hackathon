from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.tenants.models import TenantCustomer

User = get_user_model()

MAPPINGS = [
    ("paid_plus", "cloudbox", "c-101"),
    ("active_pro", "cloudbox", "c-102"),
    ("refund_review", "cloudbox", "c-103"),
    ("shop_demo", "shopx", "s-201"),
]


class Command(BaseCommand):
    help = "Seed TenantCustomer mappings for demo and tests."

    @transaction.atomic
    def handle(self, *args, **options):
        for username, tenant, external_id in MAPPINGS:
            user, _ = User.objects.get_or_create(
                username=username,
                defaults={"is_staff": False},
            )
            mapping, created = TenantCustomer.objects.update_or_create(
                user=user,
                defaults={"tenant": tenant, "external_id": external_id},
            )
            verb = "created" if created else "updated"
            self.stdout.write(f"TenantCustomer {verb}: {username} -> {tenant} ({external_id})")
