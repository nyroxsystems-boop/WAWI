
import os
import django
from django.conf import settings

# Setup Django Environment (Mocking what manage.py shell does if run directly)
# But typically this is run via: python manage.py shell < fix_domain.py
# So we assume environment is setup.

try:
    from tenancy.models import Tenant, Domain
except ImportError:
    import sys
    print("Error: Could not import tenancy models. Make sure you are running this via 'python manage.py shell < InvenTree/fix_domain.py'")
    sys.exit(1)

DOMAIN_NAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'wawi-new.onrender.com')
# Remove protocol if present
DOMAIN_NAME = DOMAIN_NAME.replace('https://', '').replace('http://', '').strip('/')

print(f"--- FIXING DOMAIN FOR: {DOMAIN_NAME} ---")

try:
    # 1. Get Public Tenant
    # The 'public' schema is the foundation for django-tenants routing
    public = Tenant.objects.get(schema_name='public')
    print(f"Found Public Tenant Account: {public}")

    # 2. Check/Update Domain
    # We use get_or_create to be safe
    domain_obj, created = Domain.objects.get_or_create(
        tenant=public,
        domain=DOMAIN_NAME,
        defaults={'is_primary': True}
    )
    
    if created:
        print(f"✅ Created NEW domain entry: {DOMAIN_NAME}")
    else:
        print(f"ℹ️  Domain entry already exists: {DOMAIN_NAME}")
        if not domain_obj.is_primary:
            domain_obj.is_primary = True
            domain_obj.save()
            print("✅ Updated to be PRIMARY domain.")
        else:
            print("✅ Already set as PRIMARY domain.")

    print("\n--- Current Domains Configuration ---")
    for d in Domain.objects.all().order_by('tenant__schema_name'):
        print(f"• Domain: {d.domain:<30} | Tenant: {d.tenant.schema_name:<15} | Primary: {d.is_primary}")

except Exception as e:
    print(f"❌ ERROR: {e}")
