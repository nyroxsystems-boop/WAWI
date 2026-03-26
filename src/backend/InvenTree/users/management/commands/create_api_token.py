"""Management command to create/reset an InvenTree ApiToken for a user."""

import datetime

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from users.models import ApiToken

User = get_user_model()


class Command(BaseCommand):
    help = 'Create or reset an InvenTree ApiToken for a given user (prints the raw key)'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str, help='Username to create token for')
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

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            self.stderr.write(f'User "{username}" does not exist')
            return

        # Revoke any existing tokens with the same name
        existing = ApiToken.objects.filter(user=user, name=name, revoked=False)
        count = existing.update(revoked=True)
        if count:
            self.stdout.write(f'Revoked {count} existing token(s) named "{name}"')

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
