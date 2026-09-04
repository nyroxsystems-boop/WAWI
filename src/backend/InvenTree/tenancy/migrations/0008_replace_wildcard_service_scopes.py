"""Replace legacy bot wildcards and deactivate all other wildcard tokens."""

from django.db import migrations


BOT_SCOPES = [
    'bot.channel.resolve',
    'bot.contact.write',
    'bot.conversation.read',
    'bot.conversation.write',
    'bot.health.read',
    'bot.inventory.read',
    'bot.settings.read',
]


def replace_wildcards(apps, schema_editor):
    """Migrate known bot tokens and fail closed for unknown wildcards."""
    ServiceToken = apps.get_model('tenancy', 'ServiceToken')
    for token in ServiceToken.objects.all().iterator():
        scopes = token.scopes or []
        if not any('*' in scope for scope in scopes if isinstance(scope, str)):
            continue
        if scopes == ['bot:*'] and token.tenant_id:
            token.scopes = BOT_SCOPES
            token.save(update_fields=['scopes'])
        else:
            token.is_active = False
            token.save(update_fields=['is_active'])


class Migration(migrations.Migration):
    """Data migration for explicit machine capabilities."""

    dependencies = [('tenancy', '0007_domain')]

    operations = [migrations.RunPython(replace_wildcards, migrations.RunPython.noop)]
