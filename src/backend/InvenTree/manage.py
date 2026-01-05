#!/usr/bin/env python
"""InvenTree / django management commands."""

import os

# Render setzt DJANGO_SETTINGS_MODULE hart auf InvenTree.settings.
# Wir überschreiben auf Render bewusst auf settings_render, damit .vite/manifest.json via collectstatic mitkommt.
def _is_render_env() -> bool:
    # Render setzt verschiedene RENDER_* Variablen bereits im Build/Predeploy
    return any(k.startswith("RENDER") for k in os.environ.keys()) or bool(os.environ.get("PORT"))

if _is_render_env() and os.environ.get("DJANGO_SETTINGS_MODULE") == "InvenTree.settings":
    os.environ["DJANGO_SETTINGS_MODULE"] = "InvenTree.settings_render"

import sys
from pathlib import Path

# Ensure project root is importable and prefer local 'events' app over plugin namespace
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
# No special sys.modules hacks required after renaming events -> outbox


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'InvenTree.settings')

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "INVE-E14: Could not import Django. Are you sure it's installed and "
            'available on your PYTHONPATH environment variable? Did you '
            'forget to activate a virtual environment?'
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
