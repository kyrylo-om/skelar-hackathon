import os
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.subscriptions.models import Payment, Plan, Subscription


class Command(BaseCommand):
    help = "Create local synthetic billing accounts without resetting existing demo state."

    @transaction.atomic
    def handle(self, *args, **options):
        password = os.environ.get("DEMO_PASSWORD")
        if not settings.DEBUG or not password or len(password) < 12:
            raise CommandError(
                "Use DEBUG=True and a local DEMO_PASSWORD of at least 12 characters."
            )
        plans = {}
        for name, price, quota in (
            ("Free", "0.00", 5),
            ("Plus", "99.00", 100),
            ("Pro", "199.00", 1000),
        ):
            plans[name], _ = Plan.objects.get_or_create(
                name=name, defaults={"price": price, "currency": "UAH", "storage_limit_gb": quota}
            )
        now = timezone.now()
        start, end = now - timedelta(days=1), now + timedelta(days=29)
        for username, plan_name, staff in (
            ("paid_plus", "Free", False),
            ("active_pro", "Pro", False),
            ("refund_review", "Plus", False),
            ("plus_manual", "Plus", False),
            ("free_user", "Free", False),
            ("pro_user", "Pro", False),
            ("operator", None, True),
        ):
            user, created = get_user_model().objects.get_or_create(
                username=username, defaults={"is_staff": staff}
            )
            if created:
                user.set_password(password)
                user.save()
            if staff:
                continue
            Subscription.objects.get_or_create(
                user=user,
                defaults={
                    "plan": plans[plan_name],
                    "auto_renew": plan_name != "Free",
                    "period_end": end if plan_name != "Free" else None,
                },
            )
            purchased = plans["Plus" if username == "paid_plus" else plan_name]
            Payment.objects.get_or_create(
                demo_reference=f"seed:{username}:purchase",
                defaults={
                    "user": user,
                    "plan": purchased,
                    "amount": purchased.price,
                    "currency": "UAH",
                    "status": "successful",
                    "period_start": start,
                    "period_end": end,
                    "applied_at": None if username == "paid_plus" else now,
                },
            )
        self.stdout.write(
            self.style.SUCCESS(
                "Synthetic users: paid_plus, active_pro, refund_review, plus_manual, free_user, pro_user, operator. Existing passwords/state preserved."
            )
        )
