#!/usr/bin/env python
"""InvenTree / django management commands."""

import os
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
