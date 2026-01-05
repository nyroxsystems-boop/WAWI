
import os
import django
from decimal import Decimal
from django.utils import timezone

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'InvenTree.settings')
django.setup()

from tenancy.models import Tenant, TenantUser
from django.contrib.auth import get_user_model
from wws.models import Order, Offer, Supplier
from billing.models import Invoice
from channels.models import Contact

User = get_user_model()

def create_demo_data():
    # 1. Create Test Tenant
    tenant_name = "Test Autoteile GmbH"
    tenant_slug = "test-autoteile"
    tenant, created = Tenant.objects.get_or_create(
        slug=tenant_slug,
        defaults={'name': tenant_name, 'is_active': True}
    )
    
    # Clean up existing data for this tenant
    Order.objects.filter(tenant=tenant).delete()
    Invoice.objects.filter(tenant=tenant).delete()
    Supplier.objects.filter(tenant=tenant).delete()
    Contact.objects.filter(tenant=tenant).delete()
    
    if created:
        print(f"Tenant '{tenant_name}' created.")
    else:
        print(f"Tenant '{tenant_name}' already exists.")

    # 2. Create Tenant Admin User
    username = "testadmin"
    email = "test@autoteile.de"
    password = "password123"
    
    user, created = User.objects.get_or_create(
        username=username,
        defaults={'email': email, 'is_staff': True}
    )
    if created:
        user.set_password(password)
        user.save()
        print(f"User '{username}' created.")
    
    # Associate user with tenant
    TenantUser.objects.get_or_create(
        user=user,
        tenant=tenant,
        defaults={'role': TenantUser.Role.OWNER_ADMIN}
    )

    # 3. Create Demo Supplier
    supplier, _ = Supplier.objects.get_or_create(
        tenant=tenant,
        name="AutoPart Pro",
        defaults={'rating': Decimal('4.8'), 'api_type': 'rest'}
    )

    # 4. Create Demo Contact (Customer)
    contact, _ = Contact.objects.get_or_create(
        tenant=tenant,
        wa_id='491701234567',
        defaults={'name': 'Max Mustermann', 'type': Contact.ContactType.CUSTOMER}
    )
    print(f"Contact '{contact.name}' created.")

    # 5. Create Demo Order (WhatsApp Flow Start)
    order = Order.objects.create(
        tenant=tenant,
        contact=contact,
        oem="06L103483A",
        notes="Dichtung für Ventildeckel Audi A4",
        status="new",
        total_price=Decimal('25.50'),
        currency="EUR"
    )
    print(f"Order created for {contact.name}")

    # 6. Create Demo Offer
    Offer.objects.create(
        tenant=tenant,
        order=order,
        supplier=supplier,
        price=Decimal('22.90'),
        currency="EUR",
        availability="In Stock",
        delivery_days=2,
        product_name="Ventildeckeldichtung ELRING",
        brand="Elring",
        status="published"
    )
    print("Offer created and published.")

if __name__ == "__main__":
    create_demo_data()
