"""WSGI config for InvenTree project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/1.10/howto/deployment/wsgi/
"""

import os  # pragma: no cover

# Render setzt DJANGO_SETTINGS_MODULE hart auf InvenTree.settings.
# Wir überschreiben auf Render bewusst auf settings_render, damit das Frontend-Manifest gefunden wird.
def _is_render_env() -> bool:
    return any(k.startswith("RENDER") for k in os.environ.keys()) or bool(os.environ.get("PORT"))

if _is_render_env() and os.environ.get("DJANGO_SETTINGS_MODULE") == "InvenTree.settings":
    os.environ["DJANGO_SETTINGS_MODULE"] = "InvenTree.settings_render"


from django.core.wsgi import get_wsgi_application  # pragma: no cover

from opentelemetry.instrumentation.wsgi import OpenTelemetryMiddleware

os.environ.setdefault(
    'DJANGO_SETTINGS_MODULE',
    'InvenTree.settings_render' if os.environ.get('PORT') else 'InvenTree.settings'
)  # pragma: no cover

application = get_wsgi_application()  # pragma: no cover
application = OpenTelemetryMiddleware(application)
