import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """
    Creates a superuser from DJANGO_SUPERUSER_USERNAME / DJANGO_SUPERUSER_EMAIL /
    DJANGO_SUPERUSER_PASSWORD environment variables, but only if a user with
    that username doesn't already exist. Safe to run on every deploy.

    This exists so you can get an admin login on Render's free instance type,
    which doesn't provide Shell access to run `createsuperuser` interactively.
    """

    help = "Create a superuser from env vars if one doesn't already exist."

    def handle(self, *args, **options):
        User = get_user_model()

        username = os.environ.get("DJANGO_SUPERUSER_USERNAME")
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")

        if not username or not password:
            self.stdout.write(
                self.style.WARNING(
                    "DJANGO_SUPERUSER_USERNAME / DJANGO_SUPERUSER_PASSWORD not "
                    "set - skipping automatic admin creation."
                )
            )
            return

        if User.objects.filter(username=username).exists():
            self.stdout.write(
                self.style.SUCCESS(f"Superuser '{username}' already exists - skipping.")
            )
            return

        User.objects.create_superuser(username=username, email=email, password=password)
        self.stdout.write(self.style.SUCCESS(f"Superuser '{username}' created."))
