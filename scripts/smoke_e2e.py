"""
Lightweight E2E smoke check using requests.

Usage:
  export API_BASE=http://localhost:8000
  export USER=email@example.com
  export PASSWORD=secret
  export TENANT_SLUG=demo-haendler
  python scripts/smoke_e2e.py
"""

import os
import sys
from typing import Any, Dict

import requests

API_BASE = os.environ.get('API_BASE', 'http://localhost:8000')
USER = os.environ.get('USER')
PASSWORD = os.environ.get('PASSWORD')
TENANT_SLUG = os.environ.get('TENANT_SLUG')


def log(title: str, data: Any = None):
    print(f'=== {title}')
    if data is not None:
        print(data)


def auth() -> str:
    payload = {'email': USER, 'password': PASSWORD}
    if TENANT_SLUG:
        payload['tenant'] = TENANT_SLUG
    res = requests.post(f'{API_BASE}/api/auth/login', json=payload, timeout=10)
    res.raise_for_status()
    token = res.json()['access']
    log('login ok', res.json())
    return token


def api_get(path: str, token: str):
    res = requests.get(f'{API_BASE}{path}', headers={'Authorization': f'Bearer {token}'}, timeout=10)
    res.raise_for_status()
    return res


def api_post(path: str, token: str, body: Dict[str, Any]):
    res = requests.post(
        f'{API_BASE}{path}', json=body, headers={'Authorization': f'Bearer {token}'}, timeout=10
    )
    res.raise_for_status()
    return res


def main():
    if not USER or not PASSWORD:
        print('Please set USER and PASSWORD env vars', file=sys.stderr)
        sys.exit(1)

    token = auth()

    # Health
    log('health', api_get('/api/health', token).json())

    # Orders list
    orders = api_get('/api/orders', token).json()
    log('orders', orders)

    # Create order
    order = api_post('/api/orders', token, {'status': 'new', 'oem': 'DEMO-OEM'}).json()
    order_id = order['id']
    log('order created', order)

    # Inventory by OEM
    inv = api_get(f'/api/bot/inventory/by-oem/{order.get("oem") or "DEMO-OEM"}', token).json()
    log('inventory', inv)

    # Create invoice from order
    inv_resp = api_post(f'/api/orders/{order_id}/create-invoice', token, {}).json()
    inv_id = inv_resp['id']
    log('invoice draft', inv_resp)

    # Issue invoice
    issued = api_post(f'/api/invoices/{inv_id}/issue', token, {}).json()
    log('invoice issued', issued)

    # PDF download (head only)
    pdf = requests.get(
        f'{API_BASE}/api/invoices/{inv_id}/pdf', headers={'Authorization': f'Bearer {token}'}, timeout=10
    )
    log('pdf status', pdf.status_code)
    pdf.raise_for_status()

    print('SMOKE OK')


if __name__ == '__main__':
    main()
