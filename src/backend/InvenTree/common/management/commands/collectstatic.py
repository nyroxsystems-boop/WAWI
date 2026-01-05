from pathlib import Path
from django.conf import settings
from django.contrib.staticfiles.management.commands.collectstatic import Command as BaseCommand


class Command(BaseCommand):
    """
    Fix for InvenTree Vite manifest on platforms where Django collectstatic ignores dot-folders (e.g. .vite).
    Ensures web/.vite/manifest.json ends up inside STATIC_ROOT/web/.vite/manifest.json.
    """

    def handle(self, **options):
        # Remove dot-folder ignore (" .* ") if present
        if hasattr(self, "default_ignore_patterns"):
            self.default_ignore_patterns = [
                p for p in self.default_ignore_patterns if p != ".*"
            ]

        result = super().handle(**options)

        static_root = Path(getattr(settings, "STATIC_ROOT", "") or "")
        if not static_root:
            self.stderr.write("STATIC_ROOT not set - cannot verify/copy Vite manifest")
            return result

        # Where the Vite build writes the manifest (in your repo)
        source = Path(settings.BASE_DIR) / "InvenTree" / "web" / "static" / "web" / ".vite" / "manifest.json"

        # Where InvenTree expects it after collectstatic
        target = static_root / "web" / ".vite" / "manifest.json"

        if not target.exists() and source.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
            self.stdout.write(f"Copied Vite manifest -> {target}")

        # If still missing, print helpful debug
        if not target.exists():
            self.stderr.write(f"Vite manifest STILL missing: {target}")
            self.stderr.write(f"Source exists: {source.exists()} ({source})")

        return result
