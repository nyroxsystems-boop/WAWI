"""Management command to create/reset an InvenTree ApiToken for a user."""

import datetime
import os
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from users.models import ApiToken

User = get_user_model()


class Command(BaseCommand):
    help = 'Create a short-lived InvenTree ApiToken and write it to a private file'

    def add_arguments(self, parser):
        parser.add_argument(
            '--username', type=str, required=True,
            help='Exact username to create the token for'
        )
        parser.add_argument(
            '--name', type=str, default='bot-service',
            help='Token name (default: bot-service)'
        )
        parser.add_argument(
            '--days', type=int, default=30,
            help='Token validity in days (maximum: 90)'
        )
        parser.add_argument(
            '--output-file', type=str, required=True,
            help='New file which receives the raw token with mode 0600'
        )

    def handle(self, *args, **options):
        username = options['username']
        name = options['name']
        days = options['days']

        if days < 1 or days > 90:
            self.stderr.write('Token validity must be between 1 and 90 days')
            return

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            self.stderr.write(f'User "{username}" does not exist')
            return

        # Check for existing active token with same name
        existing = ApiToken.objects.filter(
            user=user, name=name, revoked=False
        ).first()

        if existing and not existing.expired:
            self.stderr.write(
                'An active token with this name already exists; revoke it explicitly first'
            )
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

        output_path = Path(options['output_file']).expanduser().resolve()
        file_descriptor = os.open(
            output_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        with os.fdopen(file_descriptor, 'w', encoding='utf-8') as output_file:
            output_file.write(token.key + '\n')

        self.stdout.write(f'Token written to {output_path} with mode 0600')
        self.stdout.write(f'Expiry: {expiry}')
        self.stdout.write(f'User: {user.username}')
