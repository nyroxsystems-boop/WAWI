"""Adapters for fetching inventory from external WWS connections."""

import logging
from typing import Any, Dict, List

import requests
from django.utils import timezone

from .models import WwsConnection

logger = logging.getLogger('inventree')


def normalize_offer(raw: dict, fallback_supplier: str) -> dict:
    """Normalize external offers into internal schema."""
    return {
        'supplier_name': raw.get('supplier') or fallback_supplier,
        'price': raw.get('price'),
        'currency': raw.get('currency') or 'EUR',
        'availability': raw.get('availability'),
        'delivery_days': raw.get('delivery_days'),
        'sku': raw.get('sku') or raw.get('id'),
        'meta': raw,
    }


def fetch_http_api(connection: WwsConnection, oem: str) -> List[dict]:
    """Call http api endpoint."""
    base = connection.base_url.rstrip('/')
    endpoint = connection.config_json.get('inventory_path') or '/inventory'
    url = f'{base}{endpoint}'
    params = {'oem': oem}
    headers = {}
    if token := connection.auth_config_json.get('token'):
        headers['Authorization'] = f'Bearer {token}'
    response = requests.get(url, params=params, headers=headers, timeout=10)
    response.raise_for_status()
    data = response.json()
    offers = data if isinstance(data, list) else data.get('offers', [])
    return [normalize_offer(o, connection.base_url) for o in offers]


def fetch_scraper(connection: WwsConnection, oem: str) -> List[dict]:
    """Stub scraper adapter."""
    return []


def fetch_demo(connection: WwsConnection, oem: str) -> List[dict]:
    """Return mock offers for demo connections."""
    now = timezone.now()
    base_price = connection.config_json.get('base_price', 100)
    return [
        {
            'supplier_name': connection.config_json.get('supplier_name', 'Demo WWS'),
            'price': base_price,
            'currency': 'EUR',
            'availability': 'in_stock',
            'delivery_days': 2,
            'sku': f'{oem}-DEMO',
            'meta': {'generated_at': now.isoformat()},
        }
    ]


ADAPTERS = {
    WwsConnection.ConnectionType.HTTP_API: fetch_http_api,
    WwsConnection.ConnectionType.SCRAPER: fetch_scraper,
    WwsConnection.ConnectionType.DEMO: fetch_demo,
}


def fetch_offers_for_connection(connection: WwsConnection, oem: str) -> Dict[str, Any]:
    """Fetch offers handling errors."""
    adapter = ADAPTERS.get(connection.type)
    if adapter is None:
        return {'offers': [], 'error': f'Unsupported type {connection.type}'}

    try:
        offers = adapter(connection, oem)
        return {'offers': offers, 'error': None}
    except Exception as exc:  # pragma: no cover - network errors
        logger.warning('Adapter failed for connection %s: %s', connection.id, exc)
        return {'offers': [], 'error': str(exc)}
