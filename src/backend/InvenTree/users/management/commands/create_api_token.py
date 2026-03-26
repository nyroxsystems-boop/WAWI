"""Management command to create/reset an InvenTree ApiToken for a user."""

import datetime

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from users.models import ApiToken

User = get_user_model()


class Command(BaseCommand):
    help = 'Create or reset an InvenTree ApiToken (prints the raw key)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--username', type=str, default=None,
            help='Username to create token for (default: first superuser found)'
        )
        parser.add_argument(
            '--name', type=str, default='bot-service',
            help='Token name (default: bot-service)'
        )
        parser.add_argument(
            '--days', type=int, default=3650,
            help='Token validity in days (default: 3650 = ~10 years)'
        )

    def handle(self, *args, **options):
        username = options['username']
        name = options['name']
        days = options['days']

        # Find the target user
        if username:
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                self.stderr.write(f'User "{username}" does not exist')
                return
        else:
            # Auto-find: first superuser, or first staff, or first user
            user = (
                User.objects.filter(is_superuser=True).first()
                or User.objects.filter(is_staff=True).first()
                or User.objects.first()
            )
            if not user:
                self.stderr.write('No users found in database')
                return
            self.stdout.write(f'Auto-selected user: {user.username}')

        # Check for existing active token with same name
        existing = ApiToken.objects.filter(
            user=user, name=name, revoked=False
        ).first()

        if existing and not existing.expired:
            self.stdout.write(f'Active token already exists (expires {existing.expiry})')
            self.stdout.write(f'TOKEN={existing.key}')
            return

        # Revoke any existing tokens with the same name
        revoked = ApiToken.objects.filter(user=user, name=name).update(revoked=True)
        if revoked:
            self.stdout.write(f'Revoked {revoked} old token(s)')

        # Create new token with long expiry
        expiry = datetime.date.today() + datetime.timedelta(days=days)
        token = ApiToken.objects.create(
            user=user,
            name=name,
            expiry=expiry,
        )

        self.stdout.write(f'TOKEN={token.key}')
        self.stdout.write(f'Expiry: {expiry}')
        self.stdout.write(f'User: {user.username}')
