import os
import django

# Setup Django first
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'InvenTree.settings')
django.setup()

from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

from tenancy.models import Tenant, TenantUser
from wws.models import Order, Offer
from billing.models import Invoice

User = get_user_model()

def run_verification():
    client = APIClient()
    tenant = Tenant.objects.get(slug='test-autoteile')
    user = User.objects.get(username='testadmin')
    
    # Authenticate manually (mocking tenant middleware)
    # We can't easily use the middleware in a simple script without a full request cycle,
    # but we can check the models directly or use the client with a mock tenant attribute.
    
    print("--- Verifying Search Flow ---")
    order = Order.objects.filter(tenant=tenant, oem="06L103483A").first()
    if order:
        print(f"SUCCESS: Found order by OEM: {order.oem}")
    else:
        print("FAILED: Order not found by OEM")

    print("\n--- Verifying Invoice Creation Flow ---")
    # Simulate the create_invoice logic from wws/api.py
    # (Since we are testing the backend implementation directly)
    from wws.api import OrderViewSet
    from unittest.mock import MagicMock
    
    request = MagicMock()
    request.tenant = tenant
    request.user = user
    
    viewset = OrderViewSet()
    viewset.request = request
    viewset.get_object = MagicMock(return_value=order)
    
    response = viewset.create_invoice(request, pk=order.id)
    if response.status_code == 201:
        invoice_id = response.data['id']
        invoice = Invoice.objects.get(id=invoice_id)
        invoice.issue() # Transition to ISSUED so it shows in revenue
        print(f"SUCCESS: Invoice created and issued. ID: {invoice_id}, Total: {invoice.total} {invoice.currency}")
    else:
        print(f"FAILED: Invoice creation failed. Status: {response.status_code}, Data: {response.data}")

    print("\n--- Verifying Dashboard Summary ---")
    from wws.api import DashboardSummaryView
    summary_view = DashboardSummaryView()
    summary_request = MagicMock()
    summary_request.tenant = tenant
    summary_view.request = summary_request
    
    summary_resp = summary_view.get(summary_request)
    if summary_resp.status_code == 200:
        data = summary_resp.data
        print(f"SUCCESS: Summary retrieved. New Orders: {data['ordersNew']}, Revenue Today: {data['revenueToday']}")
    else:
        print(f"FAILED: Summary retrieval failed. Status: {summary_resp.status_code}")

if __name__ == "__main__":
    run_verification()
